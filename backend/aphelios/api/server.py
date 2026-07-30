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
import time
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
    "music.update",
    "stock.update",
    "dashboard.overview",
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
    "music.update",
    "stock.update",
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

    async def _dashboard_overview_loop() -> None:
        """Sendet alle 5s einen kompakten Überblick fürs Web-Dashboard
        (Dashboard.tsx) – Engine-Status ändert sich sonst nur beim initialen
        WS-Connect-Snapshot, ein offenes Dashboard sähe einen abgestürzten
        Engine also nie live."""
        while True:
            await asyncio.sleep(5.0)
            await bus.publish(
                Event(
                    "dashboard.overview",
                    {
                        "engines": manager.status(),
                        "clients": connections.count,
                        "ai": "claude" if config.has_anthropic else "fallback",
                        "updated_at": time.time(),
                    },
                    source="api",
                )
            )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await manager.start_all()
        logger.info("APHELIOS online – %d Engine(s) aktiv", len(manager.engines))
        overview_task = asyncio.create_task(_dashboard_overview_loop())
        try:
            yield
        finally:
            overview_task.cancel()
            await manager.stop_all()
            logger.info("APHELIOS heruntergefahren")

    app = FastAPI(title="APHELIOS API", version="1.6.0a1", lifespan=lifespan)
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
            "version": "1.6.0a1",
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
    "/wissen ": ("knowledge.request", "text", {}),
    "/code ": ("coding.request", "text", {}),
    "/code-datei ": ("coding.request", "text", {"action": "write_file"}),
    "/run ": ("automation.request", "command", {"action": "run_powershell"}),
    "/oeffne ": ("automation.request", "name", {"action": "open_app"}),
    "/schliesse ": ("automation.request", "name", {"action": "close_app"}),
    "/loesche ": ("automation.request", "path", {"action": "delete_path"}),
    "/sieh ": ("vision.request", "question", {"action": "describe"}),
    "/browse ": ("browser.request", "text", {}),
    "/dokument ": ("office.request", "text", {}),
    "/mail-senden ": ("mail.send.request", "text", {}),
    "/termin-anlegen ": ("calendar.create.request", "text", {}),
    "/aktie ": ("stock.quote.request", "symbol", {}),
    "/aktien-analyse ": ("research.committee.request", "symbol", {}),
    "/bildschirm ": ("screen.ask.request", "question", {}),
}

#: Slash-Befehle ganz ohne Argument.
_NOARG_SLASH_COMMANDS: dict[str, tuple[str, dict]] = {
    "/downloads": ("automation.request", {"action": "downloads"}),
    "/sieh": ("vision.request", {"action": "describe", "question": ""}),
    "/lies": ("vision.request", {"action": "ocr"}),
    "/fehler": ("vision.request", {"action": "find_error"}),
    "/browse": ("browser.request", {"text": ""}),
    "/dokument": ("office.request", {"text": ""}),
    "/code-datei": ("coding.request", {"action": "write_file", "text": ""}),
    "/mail-senden": ("mail.send.request", {"text": ""}),
    "/termin-anlegen": ("calendar.create.request", {"text": ""}),
}

#: Einzige Quelle der Wahrheit für ``/help``/``/hilfe`` – bei jedem neuen
#: Slash-Befehl HIER mitpflegen (siehe auch README.md-Tabelle,
#: docs/engines.md), sonst veraltet die Übersicht sofort.
_COMMAND_HELP: list[tuple[str, str]] = [
    ("/plan <Aufgabe>", "Zerlegt eine Aufgabe in Schritte – echt im „Aufgaben\"-Panel, abhakbar"),
    ("/denke <Frage>", "Zeigt APHELIOS' Analyse sichtbar (Werkzeug-Wahl → Kontext → Antwort)"),
    ("/wissen <Frage>", "Beantwortet NUR auf Basis des Obsidian-Vaults (RAG, mit Quellenangabe)"),
    ("/code <Anfrage>", "Schreibt/erklärt Code (nur im Chat, kein Datei-Zugriff)"),
    ("/code-datei <Pfad> <Anfrage>", "Schreibt Code UND speichert ihn in der Datei – mit Bestätigung"),
    ("/run <PowerShell-Befehl>", "Führt einen Befehl aus – immer mit Bestätigungsdialog"),
    ("/oeffne <Programm>", "Startet ein Programm – mit Bestätigung"),
    ("/schliesse <Programm>", "Beendet ein Programm – mit Bestätigung"),
    ("/loesche <Pfad>", "Löscht eine Datei/einen Ordner – mit Bestätigung"),
    ("/downloads", "Listet den Downloads-Ordner (nur lesend)"),
    ("/sieh <Frage>", "Screenshot + Claude beschreibt/beantwortet – mit Bestätigung"),
    ("/lies", "Liest den sichtbaren Bildschirmtext (lokales OCR) – mit Bestätigung"),
    ("/fehler", "Sucht eine sichtbare Fehlermeldung und erklärt sie – mit Bestätigung"),
    ("/browse <URL> [Frage]", "Öffnet eine Seite (echter Browser) und beantwortet Fragen dazu – mit Bestätigung"),
    ("/dokument <Pfad> [Frage]", "Liest Word/Excel/PowerPoint/PDF und beantwortet Fragen dazu – mit Bestätigung"),
    ("/mail-senden <An> | <Betreff> | <Text>", "Sendet eine Gmail-Mail – mit Bestätigung"),
    ("/termin-anlegen <Titel> | <Start JJJJ-MM-TT HH:MM> | <Dauer in Min.>", "Legt einen Kalender-Termin an – mit Bestätigung"),
    ("/aktie <Symbol>", "Aktueller Kurs eines Börsensymbols, z. B. \"/aktie AAPL\" (kein Firmenname)"),
    ("/aktien-analyse <Symbol>", "Investment-Committee (Bulle/Bär/Risiko + Fazit) zu einem Symbol – keine Anlageberatung"),
    ("/bildschirm <Frage>", "Analysiert den aktuell geteilten Bildschirm (Screen-Sharing muss aktiv sein)"),
    ("/help oder /hilfe", "Zeigt diese Übersicht"),
]


def _help_text() -> str:
    lines = [f"{cmd} – {desc}" for cmd, desc in _COMMAND_HELP]
    return "Verfügbare Befehle:\n" + "\n".join(lines)


async def _handle_client_message(bus: EventBus, message: dict) -> None:
    """Verarbeitet eine vom HUD gesendete WebSocket-Nachricht."""
    msg_type = message.get("type")
    if msg_type == "chat":
        text = message.get("text", "")
        request_id = message.get("id", uuid.uuid4().hex)
        lowered = text.strip().lower()

        if lowered in ("/help", "/hilfe"):
            help_text = _help_text()
            for word in help_text.split(" "):
                await bus.publish(Event("chat.token", {"id": request_id, "text": word + " "}, source="hud"))
                await asyncio.sleep(0.01)
            await bus.publish(
                Event("chat.response", {"id": request_id, "text": help_text, "final": True}, source="hud")
            )
            return

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
    elif msg_type in (
        "music.play.request",
        "music.pause.request",
        "music.next.request",
        "music.previous.request",
    ):
        await bus.publish(Event(msg_type, {}, source="hud"))
    elif msg_type == "music.volume.request":
        await bus.publish(Event(msg_type, {"level": message.get("level")}, source="hud"))
    elif msg_type == "music.like.request":
        await bus.publish(Event(msg_type, {"liked": bool(message.get("liked"))}, source="hud"))
    elif msg_type == "memory.recent.request":
        await bus.publish(
            Event("memory.recent", {"id": message.get("id"), "limit": message.get("limit", 15)}, source="hud")
        )
    elif msg_type == "screen.frame":
        await bus.publish(Event("screen.frame", {"frame_base64": message.get("frame_base64", "")}, source="hud"))
    elif msg_type == "screen.share.stop":
        await bus.publish(Event("screen.share.stop", {}, source="hud"))
    elif msg_type == "screen.proactive.set":
        await bus.publish(Event("screen.proactive.set", {"enabled": bool(message.get("enabled"))}, source="hud"))
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
