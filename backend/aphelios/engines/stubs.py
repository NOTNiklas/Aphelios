"""Schnittstellen-Stubs für die noch nicht implementierten Engines.

Jede Klasse erbt von ``BaseEngine`` und definiert bereits die vorgesehene
Bus-Schnittstelle plus ``TODO``-Hinweise, sodass die spätere Implementierung
„drop-in" möglich ist. Der Umfang jeder Engine ist in ``ROADMAP.md`` beschrieben.

Diese Engines melden sich beim Start als ``online``, führen aber (noch) keine
Aktionen aus – sie halten lediglich ihren Platz in der Architektur.
"""

from __future__ import annotations

from aphelios.core.engine import BaseEngine


class _StubEngine(BaseEngine):
    """Basis für alle Platzhalter-Engines: abonniert ein Topic und loggt Aufrufe."""

    #: Topic, das diese Engine später bedienen wird.
    topic: str = ""

    async def start(self) -> None:
        self._running = True
        if self.topic:
            self.bus.subscribe(self.topic, self.handle)

    async def handle(self, event) -> None:  # noqa: ANN001 – Event
        self.log.info("[stub] %s empfing %r (noch nicht implementiert)", self.name, event.topic)


class AgentEngine(_StubEngine):
    """Orchestriert mehrere parallele AI-Agenten. TODO: Roadmap Beta."""

    name = "agent"
    topic = "agent.request"
