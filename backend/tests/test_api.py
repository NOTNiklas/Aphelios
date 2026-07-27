"""Tests für den API-Server: WebSocket-State-Replay für neu verbundene Clients."""

from __future__ import annotations

from aphelios.api.server import ConnectionManager


class _FakeWebSocket:
    """Minimal-Stand-in für ``fastapi.WebSocket`` – zeichnet gesendete JSONs auf."""

    def __init__(self) -> None:
        self.accepted = False
        self.sent: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message: dict) -> None:
        self.sent.append(message)


async def test_replay_sends_last_state_to_late_joiner():
    # Regression: Ohne Replay verpasst ein HUD, das *nach* dem periodischen
    # Abruf einer Engine verbindet (z. B. Wetter alle 15 Minuten), den Wert
    # bis zum nächsten Intervall – wirkt wie ein Defekt, ist aber keiner.
    manager = ConnectionManager(replayable_topics=["weather.update", "system.stats"])

    # Ein Broadcast passiert, BEVOR irgendein Client verbunden ist.
    await manager.broadcast(
        {"topic": "weather.update", "data": {"city": "Berlin", "temperature": 21.0}, "source": "weather"}
    )
    await manager.broadcast(
        {"topic": "system.stats", "data": {"cpu": {"percent": 12.0}}, "source": "system"}
    )
    # Ein nicht-zustandsartiges Topic darf NICHT nachgereicht werden (z. B.
    # eine bereits abgelaufene Bestätigungsanfrage soll nicht wieder auftauchen).
    await manager.broadcast({"topic": "confirmation.request", "data": {"id": "x"}, "source": "security"})

    late_joiner = _FakeWebSocket()
    await manager.connect(late_joiner)
    await manager.replay_last_state(late_joiner)

    topics_sent = {m["topic"] for m in late_joiner.sent}
    assert topics_sent == {"weather.update", "system.stats"}
    weather_msg = next(m for m in late_joiner.sent if m["topic"] == "weather.update")
    assert weather_msg["data"]["city"] == "Berlin"


async def test_replay_uses_latest_value_not_first():
    manager = ConnectionManager(replayable_topics=["weather.update"])
    await manager.broadcast({"topic": "weather.update", "data": {"temperature": 10.0}, "source": "weather"})
    await manager.broadcast({"topic": "weather.update", "data": {"temperature": 15.0}, "source": "weather"})

    ws = _FakeWebSocket()
    await manager.replay_last_state(ws)

    assert len(ws.sent) == 1
    assert ws.sent[0]["data"]["temperature"] == 15.0


async def test_broadcast_reaches_already_connected_clients():
    manager = ConnectionManager(replayable_topics=["system.stats"])
    ws = _FakeWebSocket()
    await manager.connect(ws)

    await manager.broadcast({"topic": "system.stats", "data": {"cpu": 5}, "source": "system"})

    assert ws.sent == [{"topic": "system.stats", "data": {"cpu": 5}, "source": "system"}]
    assert manager.count == 1
