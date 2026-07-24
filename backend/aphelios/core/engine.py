"""Basisklasse für alle APHELIOS-Engines.

Eine Engine ist ein unabhängiges Modul, das eine Fähigkeit bereitstellt
(System-Monitoring, Konversation, Gedächtnis, …). Alle Engines erben von
``BaseEngine`` und kommunizieren ausschließlich über den EventBus.

Neue Engine erstellen – siehe ``docs/engines.md``.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from aphelios.core.config import Config
from aphelios.core.event_bus import Event, EventBus
from aphelios.core.security import SecurityGate


class BaseEngine(ABC):
    """Abstrakte Basis für jede Engine.

    Unterklassen setzen ``name`` und implementieren mindestens ``start``.
    ``handle`` wird für abonnierte Topics aufgerufen, ``stop`` beim Herunterfahren.
    """

    #: Kurzer, eindeutiger Name (z. B. ``"system"``). Von Unterklassen zu setzen.
    name: str = "base"

    def __init__(self, bus: EventBus, config: Config, security: SecurityGate) -> None:
        self.bus = bus
        self.config = config
        self.security = security
        self.log = logging.getLogger(f"aphelios.engine.{self.name}")
        self._running = False

    # -- Lebenszyklus ---------------------------------------------------------
    @abstractmethod
    async def start(self) -> None:
        """Ressourcen aufbauen, Topics abonnieren, Hintergrund-Loops starten."""

    async def stop(self) -> None:
        """Sauber herunterfahren. Standard: no-op (überschreibbar)."""
        self._running = False

    async def handle(self, event: Event) -> None:
        """Ein abonniertes Event verarbeiten. Standard: no-op (überschreibbar)."""

    # -- Hilfen ---------------------------------------------------------------
    async def emit(self, topic: str, data: dict | None = None) -> None:
        """Bequemes Publizieren eines Events mit dieser Engine als Quelle."""
        await self.bus.publish(Event(topic, data or {}, source=self.name))

    @property
    def running(self) -> bool:
        return self._running

    @property
    def status(self) -> str:
        """Grober Status für die HUD-Anzeige: ``online`` / ``offline``."""
        return "online" if self._running else "offline"
