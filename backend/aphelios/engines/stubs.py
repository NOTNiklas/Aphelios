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


class ReasoningEngine(_StubEngine):
    """Mehrstufiges Schlussfolgern und Werkzeug-Auswahl. TODO: Roadmap Alpha 1.1."""

    name = "reasoning"
    topic = "reasoning.request"


class PlanningEngine(_StubEngine):
    """Zerlegt Aufgaben in ausführbare Schritte. TODO: Roadmap Alpha 1.1."""

    name = "planning"
    topic = "planning.request"


class AutomationEngine(_StubEngine):
    """PowerShell / pywinauto / Playwright-Automatisierung. TODO: Roadmap Alpha 1.2.

    Alle Aktionen müssen später über ``self.security.request(...)`` laufen.
    """

    name = "automation"
    topic = "automation.request"


class CodingEngine(_StubEngine):
    """Code schreiben, refactoren, Git/GitHub, Docker, WSL. TODO: Roadmap Alpha 1.6."""

    name = "coding"
    topic = "coding.request"


class BrowserEngine(_StubEngine):
    """Browser-Steuerung via Playwright. TODO: Roadmap Alpha 1.6."""

    name = "browser"
    topic = "browser.request"


class KnowledgeEngine(_StubEngine):
    """Wissensabruf / RAG über den Vault. TODO: Roadmap Alpha 1.5."""

    name = "knowledge"
    topic = "knowledge.request"


class VisionEngine(_StubEngine):
    """Bildschirm-Verständnis: OCR, Fenster-/Button-Erkennung. TODO: Roadmap Alpha 1.4."""

    name = "vision"
    topic = "vision.request"


class VoiceEngine(_StubEngine):
    """Whisper-STT + hochwertige TTS. TODO: Roadmap Alpha 1.3.

    In Alpha 1.0 übernimmt das Frontend (Web Speech API) die Sprachaktivierung;
    diese Engine definiert die spätere Backend-Pipeline.

    Vorgesehene Bus-Schnittstelle:
        * ``voice.transcript`` (in)  – erkannter Text vom Frontend/STT
        * ``voice.speak`` (in)       – Text, der per TTS ausgegeben werden soll
    """

    name = "voice"
    topic = "voice.speak"


class AgentEngine(_StubEngine):
    """Orchestriert mehrere parallele AI-Agenten. TODO: Roadmap Beta."""

    name = "agent"
    topic = "agent.request"
