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
from aphelios.core.event_bus import Event, EventBus
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
]


class ConnectionManager:
    """Hält aktive WebSocket-Verbindungen und broadcastet Events."""

    def __init__(self) -> None:
        self._active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._active.discard(ws)

    async def broadcast(self, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._active):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 – Verbindung vermutlich tot
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

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

    connections = ConnectionManager()

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

    app = FastAPI(title="APHELIOS API", version="1.0.0a1", lifespan=lifespan)
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
            "version": "1.0.0a1",
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
        # Begrüßungs-Snapshot: aktueller Engine-Status.
        await ws.send_json(
            {"topic": "engine.status", "data": manager.status(), "source": "api"}
        )
        try:
            while True:
                message = await ws.receive_json()
                await _handle_client_message(bus, message)
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


async def _handle_client_message(bus: EventBus, message: dict) -> None:
    """Verarbeitet eine vom HUD gesendete WebSocket-Nachricht."""
    msg_type = message.get("type")
    if msg_type == "chat":
        await bus.publish(
            Event(
                "chat.request",
                {"id": message.get("id", uuid.uuid4().hex), "text": message.get("text", "")},
                source="hud",
            )
        )
    elif msg_type in ("confirmation.approve", "confirmation.deny"):
        await bus.publish(Event(msg_type, {"id": message.get("id")}, source="hud"))
    elif msg_type == "memory.note":
        await bus.publish(Event("memory.note", message.get("data", {}), source="hud"))
    else:
        logger.debug("Unbekannte HUD-Nachricht: %r", msg_type)


async def _request_chat(bus: EventBus, text: str, timeout: float = 60.0) -> str:
    """Sendet eine Chat-Anfrage und wartet auf die vollständige Antwort."""
    request_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    future: asyncio.Future[str] = loop.create_future()

    def _on_response(event: Event) -> None:
        if event.data.get("id") == request_id and not future.done():
            future.set_result(event.data.get("text", ""))

    bus.subscribe("chat.response", _on_response)
    try:
        await bus.publish(Event("chat.request", {"id": request_id, "text": text}, source="api"))
        return await asyncio.wait_for(future, timeout)
    except asyncio.TimeoutError:
        return ""
    finally:
        bus.unsubscribe("chat.response", _on_response)
