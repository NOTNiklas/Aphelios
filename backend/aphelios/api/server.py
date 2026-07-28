"""API-Server – verbindet das HUD-Frontend mit dem APHELIOS-Kern.

Stellt bereit:
    * ``GET  /health``  – Health-Check + Engine-Status
    * ``WS   /ws``      – Live-Stream von ``system.stats`` & Engine-Events an das HUD;
                          empfängt Chat-Nachrichten und Bestätigungen vom HUD
    * ``POST /chat``    – einzelne Chat-Anfrage → vollständige Antwort (nicht streamend)

Der Server abonniert ausgewählte Bus-Topics und leitet sie an alle verbundenen
WebSocket-Clients weiter (Broadcast).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from aphelios.core.config import Config
from aphelios.core.event_bus import Event, EventBus, request
from aphelios.core.manager import EngineManager
from aphelios.core.security import SecurityGate
from aphelios.engines import ALL_ENGINES

logger = logging.getLogger("aphelios.api")

#: Bus-Topics, die live an alle HUD-Clients weitergereicht werden.
BROADCAST_TOPICS = [
    "system.stats",
    "chat.token",
    "chat.response",
    "confirmation.request",
    "memory.saved",
    "memory.result",
    "weather.update",
    "mail.update",
    "calendar.update",
    "plan.update",
    "voice.audio",
    "voice.transcript",
    "voice.error",
]

#: Teilmenge von BROADCAST_TOPICS, die "aktuellen Zustand" statt einmaliger
#: Ereignisse darstellt. Für diese Topics wird der letzte Stand zwischen-
#: gespeichert und neu verbundenen Clients sofort nachgereicht – sonst verpasst
#: ein HUD, das *nach* dem periodischen Abruf verbindet, den Wert bis zum
#: nächsten Intervall (bei Wetter/Mail/Kalender u. U. mehrere Minuten lang,
#: was wie ein Defekt aussieht, obwohl die Engine korrekt lief).
REPLAYABLE_TOPICS = [
    "system.stats",
    "weather.update",
    "mail.update",
    "calendar.update",
    "plan.update",
]


class ConnectionManager:
    """Hält aktive WebSocket-Verbindungen, broadcastet Events und merkt sich
    den letzten Stand "zustandsartiger" Topics (siehe ``REPLAYABLE_TOPICS``)
    für neu verbundene Clients.
    """

    def __init__(self, replayable_topics: list[str] | None = None) -> None:
        self._active: set[WebSocket] = set()
        self._replayable = set(replayable_topics or [])
        self._last_state: dict[str, dict] = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._active.discard(ws)

    async def broadcast(self, message: dict) -> None:
        topic = message.get("topic")
        if topic in self._replayable:
            self._last_state[topic] = message
        dead: list[WebSocket] = []
        for ws in list(self._active):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 – Verbindung vermutlich tot
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def replay_last_state(self, ws: WebSocket) -> None:
        """Schickt einem frisch verbundenen Client den zuletzt bekannten Stand
        jedes zustandsartigen Topics nach.

        Ohne das würde ein HUD, das erst *nach* dem periodischen Abruf einer
        Engine verbindet, auf das nächste Intervall warten müssen – bei
        Wetter/Mail/Kalender potenziell mehrere Minuten, was wie ein Defekt
        wirkt, obwohl die Engine korrekt gelaufen ist.
        """
        for message in self._last_state.values():
            await ws.send_json(message)

    @property
    def count(self) -> int:
        return len(self._active)


def create_app(config: Config | None = None) -> FastAPI:
    """Baut die komplette FastAPI-App inklusive Kern und Engines."""
    config = config or Config.from_env()

    bus = EventBus()
    security = SecurityGate(bus)
    manager = EngineManager()
    for engine_cls in ALL_ENGINES:
        manager.register(engine_cls(bus, config, security))

    connections = ConnectionManager(replayable_topics=REPLAYABLE_TOPICS)

    async def _broadcast(event: Event) -> None:
        await connections.broadcast(
            {"topic": event.topic, "data": event.data, "source": event.source}
        )

    for topic in BROADCAST_TOPICS:
        bus.subscribe(topic, _broadcast)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await manager.start_all()
        logger.info("APHELIOS online – %d Engine(s) aktiv", len(manager.engines))
        try:
            yield
        finally:
            await manager.stop_all()
            logger.info("APHELIOS heruntergefahren")

    app = FastAPI(title="APHELIOS API", version="1.3.0a1", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[config.cors_origin, "http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- HTTP -----------------------------------------------------------------
    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "online",
            "version": "1.3.0a1",
            "engines": manager.status(),
            "clients": connections.count,
            "ai": "claude" if config.has_anthropic else "fallback",
        }

    @app.post("/chat")
    async def chat(payload: dict) -> dict:
        text = (payload or {}).get("text", "")
        reply = await _request_chat(bus, text)
        return {"text": reply}

    # -- WebSocket ------------------------------------------------------------
    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await connections.connect(ws)
        # Begrüßungs-Snapshot: aktueller Engine-Status …
        await ws.send_json(
            {"topic": "engine.status", "data": manager.status(), "source": "api"}
        )
        # … plus der letzte bekannte Stand je "Zustands"-Topic.
        await connections.replay_last_state(ws)
        try:
            while True:
                message = await ws.receive_json()
                # Als Task einplanen statt zu awaiten: bus.publish() wartet
                # intern, bis alle Subscriber (inkl. Engine-Handler) fertig
                # sind – und ein Handler kann über das SecurityGate auf genau
                # die NÄCHSTE Nachricht auf dieser selben Verbindung warten
                # (die Bestätigung des Nutzers). Würde die Schleife hier
                # blockieren, käme diese Bestätigung nie an → Deadlock.
                # Reproduziert & regressionsgetestet in test_ws_automation.py.
                asyncio.create_task(_handle_client_message_safe(bus, message))
        except WebSocketDisconnect:
            connections.disconnect(ws)
        except Exception:  # noqa: BLE001
            logger.exception("WebSocket-Fehler")
            connections.disconnect(ws)

    # Für Tests/Introspektion zugänglich machen.
    app.state.bus = bus
    app.state.manager = manager
    app.state.config = config
    return app


#: Slash-Befehle mit Argument im Chat-Eingabefeld – werden serverseitig
#: erkannt und an die passende Engine geroutet, statt an die normale
#: ConversationEngine. Kein Frontend-Änderung nötig: das bestehende
#: Eingabefeld bleibt die einzige Interaktionsfläche (siehe
#: ``docs/engines.md``). Format: prefix -> (topic, feld_für_das_argument,
#: feste_zusatzfelder).
_SLASH_COMMANDS: dict[str, tuple[str, str, dict]] = {
    "/plan ": ("plan.request", "task", {}),
    "/denke ": ("reasoning.request", "text", {}),
    "/run ": ("automation.request", "command", {"action": "run_powershell"}),
    "/oeffne ": ("automation.request", "name", {"action": "open_app"}),
    "/schliesse ": ("automation.request", "name", {"action": "close_app"}),
    "/loesche ": ("automation.request", "path", {"action": "delete_path"}),
}

#: Slash-Befehle ganz ohne Argument.
_NOARG_SLASH_COMMANDS: dict[str, tuple[str, dict]] = {
    "/downloads": ("automation.request", {"action": "downloads"}),
}


async def _handle_client_message(bus: EventBus, message: dict) -> None:
    """Verarbeitet eine vom HUD gesendete WebSocket-Nachricht."""
    msg_type = message.get("type")
    if msg_type == "chat":
        text = message.get("text", "")
        request_id = message.get("id", uuid.uuid4().hex)
        lowered = text.strip().lower()

        if lowered in _NOARG_SLASH_COMMANDS:
            topic, payload = _NOARG_SLASH_COMMANDS[lowered]
            await bus.publish(Event(topic, {**payload, "id": request_id}, source="hud"))
            return

        for prefix, (topic, field, payload) in _SLASH_COMMANDS.items():
            if lowered.startswith(prefix):
                arg = text.strip()[len(prefix):].strip()
                await bus.publish(Event(topic, {**payload, field: arg, "id": request_id}, source="hud"))
                return

        await bus.publish(Event("chat.request", {"id": request_id, "text": text}, source="hud"))
    elif msg_type in ("confirmation.approve", "confirmation.deny"):
        await bus.publish(Event(msg_type, {"id": message.get("id")}, source="hud"))
    elif msg_type == "memory.note":
        await bus.publish(Event("memory.note", message.get("data", {}), source="hud"))
    elif msg_type == "plan.step.complete":
        await bus.publish(Event("plan.step.complete", {"index": message.get("index")}, source="hud"))
    elif msg_type == "voice.speak":
        request_id = message.get("id", uuid.uuid4().hex)
        await bus.publish(
            Event("voice.speak", {"id": request_id, "text": message.get("text", "")}, source="hud")
        )
    elif msg_type == "voice.transcribe":
        request_id = message.get("id", uuid.uuid4().hex)
        await bus.publish(
            Event(
                "voice.transcribe",
                {"id": request_id, "audio_base64": message.get("audio_base64", "")},
                source="hud",
            )
        )
    else:
        logger.debug("Unbekannte HUD-Nachricht: %r", msg_type)


async def _handle_client_message_safe(bus: EventBus, message: dict) -> None:
    """Wie ``_handle_client_message``, aber fängt Fehler ab und protokolliert
    sie, statt sie zu propagieren – läuft als eigenständiger Task (siehe
    ``ws_endpoint``), es gibt also keinen umschließenden try/except mehr."""
    try:
        await _handle_client_message(bus, message)
    except Exception:  # noqa: BLE001
        logger.exception("Fehler bei der Verarbeitung einer HUD-Nachricht: %r", message)


async def _request_chat(bus: EventBus, text: str, timeout: float = 60.0) -> str:
    """Sendet eine Chat-Anfrage und wartet auf die vollständige Antwort."""
    result = await request(bus, "chat.request", "chat.response", {"text": text}, timeout)
    return (result or {}).get("text", "")
