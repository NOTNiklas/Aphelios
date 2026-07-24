"""SecurityGate – Bestätigungspflicht für gefährliche Aktionen.

Grundsatz: **keine gefährliche Aktion ohne ausdrückliche Bestätigung.**
Details in ``docs/security.md``.

Ablauf:
    1. Eine Engine ruft ``await gate.request(...)``.
    2. ``SAFE`` → sofort erlaubt.
    3. ``CONFIRM`` / ``DANGEROUS`` → publiziert ``confirmation.request`` und
       wartet auf ``confirmation.approve`` / ``confirmation.deny`` mit passender ID.
    4. Ohne Antwort (Timeout) → **deny by default**.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from enum import IntEnum

from aphelios.core.event_bus import Event, EventBus

logger = logging.getLogger("aphelios.security")


class RiskLevel(IntEnum):
    """Risikostufe einer Aktion."""

    SAFE = 0  # z. B. Stats lesen, Notiz schreiben → sofort erlaubt
    CONFIRM = 1  # z. B. Datei löschen, Programm starten → Bestätigung nötig
    DANGEROUS = 2  # z. B. Registry, Systemdatei, Deinstallation → Bestätigung + Warnung


class SecurityGate:
    """Klassifiziert Aktionen und blockiert gefährliche bis zur Freigabe."""

    def __init__(self, bus: EventBus, default_timeout: float = 120.0) -> None:
        self.bus = bus
        self.default_timeout = default_timeout
        # Offene Bestätigungen: id -> Future[bool]
        self._pending: dict[str, asyncio.Future[bool]] = {}
        bus.subscribe("confirmation.approve", self._on_decision)
        bus.subscribe("confirmation.deny", self._on_decision)

    async def request(
        self,
        action: str,
        *,
        level: RiskLevel = RiskLevel.CONFIRM,
        target: str = "",
        reason: str = "",
        timeout: float | None = None,
    ) -> bool:
        """Fordert die Erlaubnis für eine Aktion an.

        Returns:
            ``True``, wenn die Aktion ausgeführt werden darf, sonst ``False``.
        """
        if level == RiskLevel.SAFE:
            return True

        request_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._pending[request_id] = future

        await self.bus.publish(
            Event(
                "confirmation.request",
                {
                    "id": request_id,
                    "action": action,
                    "level": int(level),
                    "level_name": level.name,
                    "target": target,
                    "reason": reason,
                },
                source="security",
            )
        )
        logger.info("confirmation requested: %s (%s) target=%s", action, level.name, target)

        try:
            return await asyncio.wait_for(future, timeout or self.default_timeout)
        except asyncio.TimeoutError:
            logger.warning("confirmation timed out for %s → denied", action)
            return False  # deny by default
        finally:
            self._pending.pop(request_id, None)

    def _on_decision(self, event: Event) -> None:
        """Handler für ``confirmation.approve`` / ``confirmation.deny``."""
        request_id = event.data.get("id")
        future = self._pending.get(request_id or "")
        if future and not future.done():
            future.set_result(event.topic == "confirmation.approve")
