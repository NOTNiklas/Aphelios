"""Tests für die CodingEngine (Alpha 1.6): läuft bewusst ohne
``ANTHROPIC_API_KEY`` (wie test_vision.py/test_browser.py) – testet damit den
vollständig offline testbaren Pfad (ehrliche Absage ohne Key), ohne die
Anthropic-SDK-Streaming-Schnittstelle mocken zu müssen. Anders als bei
PlanningEngine/VisionEngine gibt es hier bewusst KEINEN Fallback-Ratepfad –
Code-Generierung ohne Claude ergibt keinen sinnvollen Ersatz.
"""

from __future__ import annotations

from aphelios.core.config import Config
from aphelios.core.event_bus import Event, EventBus
from aphelios.core.security import SecurityGate
from aphelios.engines.coding_engine import CodingEngine


def _engine(bus: EventBus) -> CodingEngine:
    return CodingEngine(bus, Config(), SecurityGate(bus))


async def _run(engine: CodingEngine, text: str) -> str:
    await engine.start()
    responses: list[dict] = []
    engine.bus.subscribe("chat.response", lambda e: responses.append(e.data))
    await engine.handle(Event("coding.request", {"id": "t1", "text": text}))
    return responses[-1]["text"]


async def test_empty_text_does_nothing():
    bus = EventBus()
    engine = _engine(bus)
    await engine.start()
    responses: list[Event] = []
    bus.subscribe("chat.response", lambda e: responses.append(e))

    await engine.handle(Event("coding.request", {"id": "t1", "text": ""}))

    assert responses == []


async def test_without_api_key_reports_honest_message_not_a_guess():
    bus = EventBus()
    engine = _engine(bus)

    text = await _run(engine, "Schreib mir ein Python-Skript, das Primzahlen findet.")

    assert "ANTHROPIC_API_KEY" in text
    assert "claude" in text.lower()


async def test_streams_tokens_before_final_response(monkeypatch):
    # Ohne Client (Standardfall in diesem Test) laeuft _reply(), das Wort fuer
    # Wort streamt - Regression: die Wort-Verkettung darf nicht vom finalen
    # Text abweichen (siehe aehnlicher Test in test_api.py fuer /help).
    bus = EventBus()
    engine = _engine(bus)
    await engine.start()
    tokens: list[str] = []
    responses: list[dict] = []
    bus.subscribe("chat.token", lambda e: tokens.append(e.data["text"]))
    bus.subscribe("chat.response", lambda e: responses.append(e.data))

    await engine.handle(Event("coding.request", {"id": "t2", "text": "hallo"}))

    full_text = "".join(tokens)
    assert full_text.strip() == responses[0]["text"]
