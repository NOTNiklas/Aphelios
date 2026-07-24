"""Ereignis-Bus – das Herzstück der Kommunikation in APHELIOS.

Ein asynchrones Publish/Subscribe-System. Engines und der API-Server tauschen
ausschließlich über den Bus Nachrichten aus; niemand ruft eine andere Engine
direkt auf. Das entkoppelt alle Module vollständig.

Beispiel::

    bus = EventBus()
    bus.subscribe("system.*", on_system_event)
    await bus.publish(Event("system.stats", {"cpu": 12.0}, source="system"))
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("aphelios.event_bus")

# Ein Handler bekommt ein Event und darf synchron oder asynchron sein.
Handler = Callable[["Event"], Awaitable[None] | None]


@dataclass(slots=True)
class Event:
    """Eine einzelne Nachricht auf dem Bus.

    Attributes:
        topic: Punkt-getrennter Bezeichner, z. B. ``system.stats`` oder
            ``chat.request``. Wird für das Routing verwendet.
        data: Beliebige Nutzdaten (JSON-serialisierbar halten).
        source: Name der Engine/Komponente, die das Event ausgelöst hat.
        timestamp: Unix-Zeit der Erzeugung.
    """

    topic: str
    data: dict[str, Any] = field(default_factory=dict)
    source: str = "system"
    timestamp: float = field(default_factory=time.time)


def _topic_matches(pattern: str, topic: str) -> bool:
    """Prüft, ob ``topic`` auf ``pattern`` passt.

    Unterstützt:
      * ``"*"``            – passt auf alles
      * ``"system.*"``     – passt auf jedes Topic mit Präfix ``system.``
      * ``"system.stats"`` – exakte Übereinstimmung
    """
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        return topic == pattern[:-2] or topic.startswith(pattern[:-1])
    return pattern == topic


class EventBus:
    """Async Publish/Subscribe-Bus mit Wildcard-Topics."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Handler]] = {}

    def subscribe(self, pattern: str, handler: Handler) -> None:
        """Registriert ``handler`` für alle Events, die auf ``pattern`` passen."""
        self._subscribers.setdefault(pattern, []).append(handler)
        logger.debug("subscribed handler to %r", pattern)

    def unsubscribe(self, pattern: str, handler: Handler) -> None:
        """Entfernt eine zuvor registrierte Subscription (leise, falls fehlend)."""
        handlers = self._subscribers.get(pattern)
        if handlers and handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        """Verteilt ``event`` an alle passenden Subscriber.

        Async-Handler werden nebenläufig ausgeführt; sync-Handler direkt.
        Fehler einzelner Handler werden protokolliert, brechen aber nicht den
        gesamten Zustellvorgang ab.
        """
        coros: list[Awaitable[None]] = []
        for pattern, handlers in list(self._subscribers.items()):
            if not _topic_matches(pattern, event.topic):
                continue
            for handler in list(handlers):
                try:
                    result = handler(event)
                    if asyncio.iscoroutine(result):
                        coros.append(result)
                except Exception:  # noqa: BLE001 – ein Handler darf den Bus nicht kippen
                    logger.exception("sync handler for %r failed", event.topic)

        if coros:
            results = await asyncio.gather(*coros, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.error("async handler for %r failed: %r", event.topic, result)
