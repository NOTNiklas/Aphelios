"""Tests für den API-Server: WebSocket-State-Replay und Chat-Nachrichten-Routing."""

from __future__ import annotations

from aphelios.api.server import ConnectionManager, _handle_client_message
from aphelios.core.event_bus import Event, EventBus


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


# -- Chat-Nachrichten-Routing (Alpha 1.1: /plan, /denke Slash-Befehle) -------
async def test_plain_chat_message_routes_to_chat_request():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("chat.request", lambda e: received.append(e))

    await _handle_client_message(bus, {"type": "chat", "id": "x1", "text": "Hallo Aphelios"})

    assert len(received) == 1
    assert received[0].data["text"] == "Hallo Aphelios"


async def test_plan_slash_command_routes_to_plan_request_not_chat():
    bus = EventBus()
    plan_events: list[Event] = []
    chat_events: list[Event] = []
    bus.subscribe("plan.request", lambda e: plan_events.append(e))
    bus.subscribe("chat.request", lambda e: chat_events.append(e))

    await _handle_client_message(
        bus, {"type": "chat", "id": "x2", "text": "/plan Küche putzen und einkaufen"}
    )

    assert len(plan_events) == 1
    assert plan_events[0].data["task"] == "Küche putzen und einkaufen"
    assert chat_events == []


async def test_denke_slash_command_routes_to_reasoning_request():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("reasoning.request", lambda e: received.append(e))

    await _handle_client_message(bus, {"type": "chat", "id": "x3", "text": "/denke Warum ist der Himmel blau?"})

    assert len(received) == 1
    assert received[0].data["text"] == "Warum ist der Himmel blau?"


async def test_plan_step_complete_message_routes_correctly():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("plan.step.complete", lambda e: received.append(e))

    await _handle_client_message(bus, {"type": "plan.step.complete", "index": 2})

    assert received[0].data["index"] == 2


# -- Chat-Nachrichten-Routing (Alpha 1.2: Automatisierungs-Slash-Befehle) -----
async def test_run_slash_command_routes_to_automation_with_action():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("automation.request", lambda e: received.append(e))

    await _handle_client_message(bus, {"type": "chat", "id": "a1", "text": "/run Get-Process"})

    assert len(received) == 1
    assert received[0].data["action"] == "run_powershell"
    assert received[0].data["command"] == "Get-Process"


async def test_oeffne_slash_command_routes_to_automation_open_app():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("automation.request", lambda e: received.append(e))

    await _handle_client_message(bus, {"type": "chat", "id": "a2", "text": "/oeffne notepad"})

    assert received[0].data == {"action": "open_app", "name": "notepad", "id": "a2"}


async def test_schliesse_slash_command_routes_to_automation_close_app():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("automation.request", lambda e: received.append(e))

    await _handle_client_message(bus, {"type": "chat", "id": "a3", "text": "/schliesse spotify"})

    assert received[0].data == {"action": "close_app", "name": "spotify", "id": "a3"}


async def test_loesche_slash_command_routes_to_automation_delete_path():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("automation.request", lambda e: received.append(e))

    await _handle_client_message(bus, {"type": "chat", "id": "a4", "text": "/loesche C:\\temp\\alt.txt"})

    assert received[0].data == {"action": "delete_path", "path": "C:\\temp\\alt.txt", "id": "a4"}


async def test_downloads_noarg_slash_command_routes_to_automation():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("automation.request", lambda e: received.append(e))

    await _handle_client_message(bus, {"type": "chat", "id": "a5", "text": "/downloads"})

    assert received[0].data == {"action": "downloads", "id": "a5"}


async def test_downloads_command_is_case_insensitive():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("automation.request", lambda e: received.append(e))

    await _handle_client_message(bus, {"type": "chat", "id": "a6", "text": "/Downloads"})

    assert len(received) == 1


# -- Chat-Nachrichten-Routing (Alpha 1.3: Sprache) ----------------------------
async def test_voice_speak_message_routes_correctly():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("voice.speak", lambda e: received.append(e))

    await _handle_client_message(bus, {"type": "voice.speak", "id": "v1", "text": "Hallo Sir."})

    assert received[0].data == {"id": "v1", "text": "Hallo Sir."}


async def test_voice_transcribe_message_routes_correctly():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("voice.transcribe", lambda e: received.append(e))

    await _handle_client_message(bus, {"type": "voice.transcribe", "id": "v2", "audio_base64": "AAAA"})

    assert received[0].data == {"id": "v2", "audio_base64": "AAAA"}
