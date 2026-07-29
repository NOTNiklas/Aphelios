"""ConversationEngine – Dialog über die Claude API (mit Fallback).

Abonniert ``chat.request`` und antwortet mit gestreamten ``chat.token``-Events,
gefolgt von einem abschließenden ``chat.response``. Der Systemprompt definiert
die APHELIOS-Persönlichkeit (ruhig, präzise, deutsch, dezenter Humor).

Ohne ``ANTHROPIC_API_KEY`` läuft die Engine im **Fallback-Modus** mit lokalen
Standardantworten, damit das System jederzeit lauffähig bleibt.

**Persistenter Konversationskontext (Alpha 1.1):** Die letzten Turns werden
nicht mehr pro Anfrage vergessen, sondern als Gesprächsverlauf mitgeführt und
über ``memory.kv.set``/``memory.kv.get`` (MemoryEngine) persistiert – ein
Backend-Neustart „vergisst" das Gespräch also nicht mehr. Zusätzlich fragt die
Engine vor jeder Antwort per ``memory.search`` thematisch passende
Obsidian-Notizen ab und gibt sie als kurzen Kontext-Hinweis mit in den
System-Prompt – der Vault wird damit zur echten zweiten Gehirnhälfte, nicht
nur zum Ablageort.

Erweiterung: OpenAI- und Ollama-Fallback sind als Hooks vorgesehen (Roadmap).

**Werkzeug-Nutzung (Alpha 1.6):** Zusätzlich zum Slash-Befehl-Schnellweg
(``/wissen``, ``/oeffne`` etc., serverseitig per Text-Präfix geroutet, siehe
``server.py``) kann Claude selbst über die offizielle Tool-Use-API
entscheiden, ob eine normale Chat-Nachricht ein Werkzeug braucht – "öffne
Spotify" löst dieselbe ``automation.request`` aus wie ``/oeffne Spotify``,
ganz ohne dass der Nutzer den Befehl kennen muss. Siehe ``_TOOLS`` und
``_tool_call_to_event`` unten.
"""

from __future__ import annotations

import asyncio
import uuid

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event, request

#: Wie viele Nachrichten (User+Aphelios zusammen) im Verlauf mitgeführt werden.
#: Begrenzt Kontextgröße/-kosten; ~10 Austausche reichen für die meisten
#: zusammenhängenden Gespräche.
MAX_HISTORY_MESSAGES = 20

#: Bus-Key, unter dem der Verlauf in der MemoryEngine-KV-Tabelle liegt.
HISTORY_KV_KEY = "conversation_history"

APHELIOS_PERSONA = """\
Du bist APHELIOS – ein hochentwickelter Desktop-AI-Assistent im Stil von \
J.A.R.V.I.S. aus Iron Man. Du bist KEIN gewöhnlicher Chatbot, sondern das \
zweite Gehirn und Betriebssystem-Assistent deines Nutzers.

Sprich ruhig, intelligent, präzise und lösungsorientiert. Nutze dezenten, \
trockenen Humor, wenn er passt – niemals aufdringlich, niemals übertrieben. \
Antworte auf Deutsch, kurz und klar. Du kennst die Projekte des Nutzers, \
merkst dir seine Arbeitsweise und schlägst proaktiv Optimierungen vor.

Du hast Zugriff auf Werkzeuge, mit denen du tatsächlich etwas auf dem PC \
des Nutzers tun kannst (Vault durchsuchen, Aufgabe planen, Code schreiben, \
Programm öffnen/schließen, Datei löschen, PowerShell-Befehl ausführen, \
Bildschirm ansehen/lesen, Webseite öffnen, Office-Dokument/PDF lesen, Mail \
senden, Termin anlegen). Nutze ein Werkzeug NUR, wenn die Anfrage \
eindeutig danach verlangt ("was hab ich mir zu X notiert" → Vault \
durchsuchen, "öffne Spotify" → Programm öffnen) – bei normalem Geplauder \
oder allgemeinen Fragen antwortest du direkt, ohne Werkzeug. Rufst du ein \
Werkzeug auf, tu das OHNE einleitenden Text ("klar, moment...", "ich schau \
mal nach...") – das System zeigt dem Nutzer bei riskanten Aktionen \
selbstständig eine Bestätigung an und antwortet danach in seinem eigenen \
Namen; du musst weder um Erlaubnis bitten noch das Ergebnis ankündigen.
"""

#: Werkzeuge, die Claude über die Tool-Use-API selbst aufrufen kann (Alpha
#: 1.6) – dieselben Fähigkeiten wie die Slash-Befehle (siehe server.py:
#: ``_SLASH_COMMANDS``/``_COMMAND_HELP``), nur durch eine normale, natürlich
#: formulierte Chat-Nachricht ausgelöst statt durch einen expliziten Präfix.
#: Bewusst NICHT als Werkzeug: ``/denke`` (ReasoningEngine) – dessen ganzer
#: Sinn ist die für den Nutzer SICHTBARE, explizit angeforderte Analyse mit
#: Zwischenschritten; als von Claude selbst gewähltes Werkzeug delegiert es
#: nur an ein zweites Modell und würde die Zwischenschritte nicht anzeigen.
_TOOLS: list[dict] = [
    {
        "name": "search_vault",
        "description": (
            "Durchsucht das Obsidian-Vault des Nutzers (Notizen, Projekte, "
            "Wissen) und beantwortet die Frage ausschließlich auf Basis "
            "gefundener Notizen, mit Quellenangabe. Nutzen, wenn der Nutzer "
            "nach etwas fragt, das er sich selbst gemerkt/notiert haben "
            "könnte, z. B. 'was habe ich zu X notiert' oder 'was war "
            "nochmal mein Plan'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Die Suchfrage."}},
            "required": ["query"],
        },
    },
    {
        "name": "create_plan",
        "description": "Zerlegt eine Aufgabe in konkrete Schritte, sichtbar im Aufgaben-Panel.",
        "input_schema": {
            "type": "object",
            "properties": {"task": {"type": "string", "description": "Die zu planende Aufgabe."}},
            "required": ["task"],
        },
    },
    {
        "name": "write_code",
        "description": (
            "Schreibt, erklärt oder überarbeitet Code (nur als Antwort im Chat, "
            "kein Datei-Zugriff). Nutzen bei konkreten Programmier-Anfragen, z. B. "
            "'schreib mir ein Python-Skript, das X macht' oder 'wie fixe ich diesen "
            "Fehler', NICHT für allgemeine technische Fragen ohne Code-Bezug."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"request": {"type": "string", "description": "Die Programmier-Anfrage."}},
            "required": ["request"],
        },
    },
    {
        "name": "save_code_to_file",
        "description": (
            "Schreibt Code UND speichert ihn in einer Datei auf dem PC des Nutzers "
            "(z. B. zum direkten Öffnen in VS Code danach). Nur nutzen, wenn der "
            "Nutzer explizit sagt, dass etwas gespeichert/in eine Datei geschrieben "
            "werden soll – sonst write_code (nur im Chat, kein Datei-Zugriff) nutzen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Zielpfad der Datei."},
                "request": {"type": "string", "description": "Die Programmier-Anfrage."},
            },
            "required": ["path", "request"],
        },
    },
    {
        "name": "run_powershell",
        "description": "Führt einen PowerShell-Befehl auf dem PC des Nutzers aus.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "open_app",
        "description": 'Startet ein Programm auf dem PC des Nutzers (z. B. "Spotify", "Notepad").',
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "close_app",
        "description": "Beendet ein laufendes Programm auf dem PC des Nutzers.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "delete_path",
        "description": "Löscht eine Datei oder einen Ordner auf dem PC des Nutzers.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "list_downloads",
        "description": "Listet die Dateien im Downloads-Ordner des Nutzers (rein lesend).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "analyze_screen",
        "description": (
            "Nimmt einen Screenshot auf und beschreibt ihn bzw. beantwortet "
            "eine Frage dazu, z. B. 'was siehst du gerade' oder 'wo ist der "
            "Speichern-Button'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string", "description": "Optionale konkrete Frage."}},
        },
    },
    {
        "name": "read_screen_text",
        "description": "Liest den aktuell sichtbaren Bildschirmtext per lokalem OCR aus.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "find_screen_error",
        "description": "Sucht eine sichtbare Fehlermeldung auf dem Bildschirm und erklärt sie.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "browse_page",
        "description": "Öffnet eine Webseite in einem echten Browser und beantwortet eine Frage zu ihrem Inhalt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Die zu öffnende URL."},
                "question": {"type": "string", "description": "Optionale Frage zur Seite."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "read_document",
        "description": (
            "Liest ein Word- (.docx), Excel- (.xlsx), PowerPoint- (.pptx) oder "
            "PDF-Dokument von der Platte des Nutzers und beantwortet eine Frage zu "
            "seinem Inhalt bzw. fasst es zusammen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Voller Pfad zur Datei."},
                "question": {"type": "string", "description": "Optionale Frage zum Dokument."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "send_email",
        "description": (
            "Sendet eine E-Mail über Gmail. Nur nutzen, wenn der Nutzer An, Betreff "
            "und Inhalt (oder genug, um sie eindeutig zu formulieren) explizit "
            "vorgibt – nie eine Mail mit erfundenem Inhalt senden."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Empfänger-Adresse."},
                "subject": {"type": "string", "description": "Betreff."},
                "body": {"type": "string", "description": "Mailtext."},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "create_calendar_event",
        "description": (
            "Legt einen Termin im Google-Kalender des Nutzers an. Start-Zeitpunkt "
            "muss als 'JJJJ-MM-TT HH:MM' angegeben werden (lokale Zeit)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titel des Termins."},
                "start": {"type": "string", "description": "Start als 'JJJJ-MM-TT HH:MM'."},
                "duration_minutes": {"type": "integer", "description": "Dauer in Minuten."},
            },
            "required": ["title", "start", "duration_minutes"],
        },
    },
]


def _tool_call_to_event(name: str, tool_input: dict) -> tuple[str, dict] | None:
    """Übersetzt einen von Claude gewählten Tool-Aufruf in (Topic, Event-Daten)
    – dieselbe Ziel-Engine und dasselbe Datenformat, das auch der passende
    Slash-Befehl erzeugen würde (siehe ``server.py``: ``_SLASH_COMMANDS``).
    ``None``, wenn ``name`` keinem bekannten Werkzeug entspricht (sollte bei
    einem über ``_TOOLS`` deklarierten Aufruf nicht vorkommen – die
    Anthropic-API validiert Tool-Aufrufe gegen die deklarierten Namen –, aber
    defensiv behandelt statt eine KeyError zu riskieren)."""
    if name == "search_vault":
        return "knowledge.request", {"text": tool_input.get("query", "")}
    if name == "create_plan":
        return "plan.request", {"task": tool_input.get("task", "")}
    if name == "write_code":
        return "coding.request", {"text": tool_input.get("request", "")}
    if name == "save_code_to_file":
        path = tool_input.get("path", "")
        request_text = tool_input.get("request", "")
        # Pfad IMMER in Anführungszeichen einbetten, unabhängig davon, ob er
        # Leerzeichen enthält – _parse_code_file_request() erkennt einen
        # gequoteten Pfad zuverlässig, ein ungequoteter würde am ersten
        # Leerzeichen (falls vorhanden) fälschlich abgeschnitten.
        return "coding.request", {"action": "write_file", "text": f'"{path}" {request_text}'.strip()}
    if name == "run_powershell":
        return "automation.request", {"action": "run_powershell", "command": tool_input.get("command", "")}
    if name == "open_app":
        return "automation.request", {"action": "open_app", "name": tool_input.get("name", "")}
    if name == "close_app":
        return "automation.request", {"action": "close_app", "name": tool_input.get("name", "")}
    if name == "delete_path":
        return "automation.request", {"action": "delete_path", "path": tool_input.get("path", "")}
    if name == "list_downloads":
        return "automation.request", {"action": "downloads"}
    if name == "analyze_screen":
        return "vision.request", {"action": "describe", "question": tool_input.get("question", "")}
    if name == "read_screen_text":
        return "vision.request", {"action": "ocr"}
    if name == "find_screen_error":
        return "vision.request", {"action": "find_error"}
    if name == "browse_page":
        url = tool_input.get("url", "")
        question = tool_input.get("question", "")
        return "browser.request", {"text": f"{url} {question}".strip()}
    if name == "read_document":
        path = tool_input.get("path", "")
        question = tool_input.get("question", "")
        return "office.request", {"text": f"{path} {question}".strip()}
    if name == "send_email":
        to = tool_input.get("to", "")
        subject = tool_input.get("subject", "")
        body = tool_input.get("body", "")
        return "mail.send.request", {"text": f"{to} | {subject} | {body}"}
    if name == "create_calendar_event":
        title = tool_input.get("title", "")
        start = tool_input.get("start", "")
        duration = tool_input.get("duration_minutes", "")
        return "calendar.create.request", {"text": f"{title} | {start} | {duration}"}
    return None


def _first_tool_use(content) -> tuple[str, dict] | None:  # noqa: ANN001
    """Findet den ersten ``tool_use``-Block in einer Claude-Antwort (mehrere
    parallele Tool-Aufrufe in einer Antwort werden in dieser ersten
    Ausbaustufe bewusst nicht unterstützt – ein Werkzeug pro Nachricht deckt
    den beschriebenen Anwendungsfall ab und hält Bestätigungsdialoge
    überschaubar)."""
    for block in content:
        if getattr(block, "type", None) == "tool_use":
            return block.name, block.input or {}
    return None


# Kurze, thematisch passende Offline-Antworten für den Fallback-Modus.
_FALLBACK_REPLIES = {
    "greeting": "Systeme online. Ich bin bereit, Sir.",
    "no_key": (
        "Ich arbeite gerade im Offline-Modus – es ist kein AI-Schlüssel "
        "hinterlegt. Trage einen ANTHROPIC_API_KEY in die .env ein, und ich "
        "stehe dir mit voller Leistung zur Verfügung."
    ),
}


class ConversationEngine(BaseEngine):
    """Verarbeitet Chat-Anfragen und streamt Antworten zurück."""

    name = "conversation"

    async def start(self) -> None:
        self._running = True
        self._client = None
        self._init_error: str | None = None
        # Lazy geladen beim ersten chat.request (siehe _ensure_history_loaded) –
        # nicht schon hier, weil die MemoryEngine parallel startet und ihre
        # memory.kv.get-Subscription zu diesem Zeitpunkt noch fehlen könnte.
        self._history: list[dict[str, str]] | None = None
        if self.config.has_anthropic:
            try:
                import anthropic

                self._client = anthropic.AsyncAnthropic(api_key=self.config.anthropic_api_key)
                self.log.info("Claude API aktiv (%s)", self.config.anthropic_model)
            except Exception as exc:  # noqa: BLE001
                self.log.exception("Anthropic-Client konnte nicht initialisiert werden")
                self._init_error = str(exc)
        else:
            self.log.warning("Kein ANTHROPIC_API_KEY – ConversationEngine läuft im Fallback-Modus")

        self.bus.subscribe("chat.request", self.handle)

    async def handle(self, event: Event) -> None:
        text = (event.data.get("text") or "").strip()
        request_id = event.data.get("id", "")
        if not text:
            return
        await self._ensure_history_loaded()
        if self._client is None:
            await self._respond_fallback(text, request_id)
        else:
            await self._respond_claude(text, request_id)

    # -- Persistenter Kontext (Alpha 1.1) --------------------------------------
    async def _ensure_history_loaded(self) -> None:
        """Lädt den Gesprächsverlauf einmalig aus der MemoryEngine (falls vorhanden).

        Läuft erst beim ersten ``chat.request`` (nicht in ``start``): zu dem
        Zeitpunkt sind garantiert alle Engines vollständig gestartet (das
        FastAPI-Lifespan wartet auf ``manager.start_all()``, bevor der Server
        Anfragen annimmt), sodass die MemoryEngine sicher bereits auf
        ``memory.kv.get`` reagiert – anders als potenziell noch während
        ``EngineManager.start_all`` selbst.
        """
        if self._history is not None:
            return
        result = await request(self.bus, "memory.kv.get", "memory.kv.result", {"key": HISTORY_KV_KEY})
        value = (result or {}).get("value")
        self._history = value if isinstance(value, list) else []

    async def _remember_turn(self, user_text: str, reply: str) -> None:
        """Hängt einen Austausch an den Verlauf an und persistiert ihn."""
        assert self._history is not None
        self._history.append({"role": "user", "content": user_text})
        self._history.append({"role": "assistant", "content": reply})
        del self._history[:-MAX_HISTORY_MESSAGES]
        await self.emit("memory.kv.set", {"key": HISTORY_KV_KEY, "value": self._history})

    async def _memory_context(self, text: str) -> str:
        """Fragt thematisch passende Vault-Notizen ab (kurzer Kontext-Hinweis).

        Best-effort: Bei Timeout/keinem Treffer wird einfach kein Zusatzkontext
        angehängt – eine fehlende Vault-Antwort darf eine Chat-Antwort niemals
        verzögern oder blockieren.
        """
        result = await request(self.bus, "memory.search", "memory.result", {"query": text}, timeout=1.5)
        hits = (result or {}).get("results") or []
        if not hits:
            return ""
        lines = [f'- „{h["title"]}" ({h["category"]}, {h.get("age", "?")})' for h in hits[:3]]
        return (
            "\n\nMögliche relevante Notizen aus dem Obsidian-Vault des Nutzers "
            "(nutze sie nur, wenn sie wirklich zur Frage passen):\n" + "\n".join(lines)
        )

    # -- Claude ---------------------------------------------------------------
    async def _respond_claude(self, text: str, request_id: str) -> None:
        assert self._client is not None
        assert self._history is not None
        collected: list[str] = []
        system = APHELIOS_PERSONA + await self._memory_context(text)
        messages = [*self._history, {"role": "user", "content": text}]
        try:
            async with self._client.messages.stream(
                model=self.config.anthropic_model,
                max_tokens=1024,
                system=system,
                messages=messages,
                tools=_TOOLS,
            ) as stream:
                async for chunk in stream.text_stream:
                    collected.append(chunk)
                    await self.emit("chat.token", {"id": request_id, "text": chunk})
                final_message = await stream.get_final_message()
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Claude-Anfrage fehlgeschlagen – nutze Fallback")
            await self._respond_fallback(text, request_id, error=str(exc))
            return

        reply = "".join(collected)

        if final_message.stop_reason == "tool_use":
            tool_call = _first_tool_use(final_message.content)
            mapped = _tool_call_to_event(*tool_call) if tool_call else None
            if mapped is not None:
                await self._dispatch_tool_call(mapped, reply, request_id)
                # Werkzeug-Aufrufe landen bewusst NICHT im Gesprächsverlauf –
                # das tatsächliche Ergebnis entsteht asynchron in einer
                # anderen Engine und ist von hier aus nicht einfach
                # einzusammeln. Ein Folge-"und, hat's geklappt?" bekommt
                # dadurch keinen Kontext zur vorherigen Aktion – akzeptierter
                # Kompromiss für diese erste Ausbaustufe.
                return

        await self.emit("chat.response", {"id": request_id, "text": reply, "final": True})
        await self._remember_turn(text, reply)

    async def _dispatch_tool_call(
        self, mapped: tuple[str, dict], preamble: str, request_id: str
    ) -> None:
        """Reicht einen von Claude gewählten Tool-Aufruf an die zuständige
        Engine weiter – dieselbe Ziel-Engine, die auch der passende
        Slash-Befehl anspräche (siehe ``_tool_call_to_event``). Diese Engine
        übernimmt danach komplett: eigene SecurityGate-Bestätigung (falls
        nötig), eigenes Streaming, eigenes ``chat.response``.

        Ist bereits Text VOR dem Werkzeug-Aufruf gestreamt worden (Claude
        wurde trotz Anweisung nicht komplett wortlos), wird dieser als
        eigene, abgeschlossene Antwort behandelt und der Werkzeug-Aufruf
        bekommt eine NEUE Nachrichten-ID – sonst würde das spätere
        ``chat.token`` der Ziel-Engine an dieselbe, bereits per
        ``chat.response`` abgeschlossene Sprechblase angehängt (oder eine
        zweite Sprechblase mit kollidierender ID erzeugen), siehe
        ``frontend/src/store/hud.ts``."""
        topic, data = mapped
        if preamble:
            await self.emit("chat.response", {"id": request_id, "text": preamble, "final": True})
            dispatch_id = uuid.uuid4().hex
        else:
            dispatch_id = request_id
        await self.emit(topic, {**data, "id": dispatch_id})

    # -- Fallback -------------------------------------------------------------
    async def _respond_fallback(
        self, text: str, request_id: str, error: str | None = None
    ) -> None:
        lowered = text.lower()
        if error:
            # Ein Key ist vorhanden, aber die Anfrage ist trotzdem gescheitert –
            # das darf NICHT wie "kein Key hinterlegt" aussehen, sonst ist der
            # eigentliche Fehler für den Nutzer unsichtbar.
            reply = (
                "Die Verbindung zur Claude API ist gerade gestört, obwohl ein "
                f"API-Key hinterlegt ist. Fehlermeldung: {error[:200]}. Prüfe den "
                "Key in der .env auf zusätzliche Leerzeichen/Anführungszeichen, "
                "das Kontingent in der Anthropic Console und deine "
                "Internetverbindung."
            )
        elif self._init_error:
            reply = (
                "Der Claude-Client konnte nicht gestartet werden: "
                f"{self._init_error[:200]}"
            )
        elif any(word in lowered for word in ("hallo", "hi", "hey", "aphelios")):
            reply = _FALLBACK_REPLIES["greeting"]
        else:
            reply = _FALLBACK_REPLIES["no_key"]

        # Antwort zeichenweise streamen, damit sich das HUD echt anfühlt.
        for word in reply.split(" "):
            await self.emit("chat.token", {"id": request_id, "text": word + " "})
            await asyncio.sleep(0.03)
        await self.emit("chat.response", {"id": request_id, "text": reply, "final": True})
