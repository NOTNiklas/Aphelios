"""Tests für die Claude-Tool-Use-Integration in der ConversationEngine
(Alpha 1.6): Claude kann selbst entscheiden, ob eine normale Chat-Nachricht
ein Werkzeug braucht ("öffne Spotify" → dieselbe automation.request wie
"/oeffne Spotify"), statt dass der Nutzer den Slash-Befehl kennen muss.

Testet die reine Mapping-Logik (``_tool_call_to_event``, ``_first_tool_use``)
ohne SDK, sowie den vollen Kontrollfluss über eine injizierte Fake-
Streaming-Antwort (``engine._client``, derselbe Dependency-Injection-Trick
wie ``engine._piper_voice``/``engine._chroma_collection`` in den anderen
Test-Dateien) – damit kein echter Claude-API-Aufruf nötig ist.
"""

from __future__ import annotations

from aphelios.core.config import Config
from aphelios.core.event_bus import Event, EventBus
from aphelios.core.security import SecurityGate
from aphelios.engines.conversation_engine import (
    _TOOLS,
    ConversationEngine,
    _first_tool_use,
    _tool_call_to_event,
)
from aphelios.engines.memory_engine import MemoryEngine


# -- Reine Mapping-Logik (kein SDK nötig) -------------------------------------
def test_every_declared_tool_has_a_mapping():
    # Jedes in _TOOLS deklarierte Werkzeug MUSS von _tool_call_to_event
    # erkannt werden – sonst würde Claude ein Werkzeug wählen können, das
    # der Server dann stillschweigend ignoriert.
    for tool in _TOOLS:
        assert _tool_call_to_event(tool["name"], {}) is not None, tool["name"]


def test_search_vault_maps_to_knowledge_request():
    assert _tool_call_to_event("search_vault", {"query": "Docker"}) == (
        "knowledge.request",
        {"text": "Docker"},
    )


def test_create_plan_maps_to_plan_request():
    assert _tool_call_to_event("create_plan", {"task": "Küche putzen"}) == (
        "plan.request",
        {"task": "Küche putzen"},
    )


def test_write_code_maps_to_coding_request():
    assert _tool_call_to_event("write_code", {"request": "Fibonacci-Funktion"}) == (
        "coding.request",
        {"text": "Fibonacci-Funktion"},
    )


def test_save_code_to_file_wraps_path_in_quotes():
    # Der Pfad wird immer gequotet, unabhaengig von Leerzeichen - so erkennt
    # _parse_code_file_request() ihn zuverlaessig als EINEN Pfad (siehe
    # test_coding.py: test_parse_code_file_request_quoted_path_with_spaces).
    assert _tool_call_to_event(
        "save_code_to_file", {"path": "hello.py", "request": "Begrüßungsfunktion"}
    ) == ("coding.request", {"action": "write_file", "text": '"hello.py" Begrüßungsfunktion'})


def test_open_app_maps_to_automation_request():
    assert _tool_call_to_event("open_app", {"name": "Spotify"}) == (
        "automation.request",
        {"action": "open_app", "name": "Spotify"},
    )


def test_run_powershell_maps_to_automation_request():
    assert _tool_call_to_event("run_powershell", {"command": "Get-Process"}) == (
        "automation.request",
        {"action": "run_powershell", "command": "Get-Process"},
    )


def test_delete_path_maps_to_automation_request():
    assert _tool_call_to_event("delete_path", {"path": "C:\\temp\\x.txt"}) == (
        "automation.request",
        {"action": "delete_path", "path": "C:\\temp\\x.txt"},
    )


def test_list_downloads_maps_to_automation_request_without_extra_fields():
    assert _tool_call_to_event("list_downloads", {}) == ("automation.request", {"action": "downloads"})


def test_analyze_screen_maps_to_vision_describe():
    assert _tool_call_to_event("analyze_screen", {"question": "Was steht da?"}) == (
        "vision.request",
        {"action": "describe", "question": "Was steht da?"},
    )


def test_read_screen_text_maps_to_vision_ocr():
    assert _tool_call_to_event("read_screen_text", {}) == ("vision.request", {"action": "ocr"})


def test_browse_page_combines_url_and_question():
    assert _tool_call_to_event("browse_page", {"url": "example.com", "question": "Titel?"}) == (
        "browser.request",
        {"text": "example.com Titel?"},
    )


def test_browse_page_without_question_has_no_trailing_space():
    assert _tool_call_to_event("browse_page", {"url": "example.com"}) == (
        "browser.request",
        {"text": "example.com"},
    )


def test_read_document_combines_path_and_question():
    assert _tool_call_to_event("read_document", {"path": "bericht.docx", "question": "Fazit?"}) == (
        "office.request",
        {"text": "bericht.docx Fazit?"},
    )


def test_read_document_without_question_has_no_trailing_space():
    assert _tool_call_to_event("read_document", {"path": "bericht.docx"}) == (
        "office.request",
        {"text": "bericht.docx"},
    )


def test_send_email_maps_to_mail_send_request():
    assert _tool_call_to_event(
        "send_email", {"to": "max@example.com", "subject": "Update", "body": "Alles erledigt."}
    ) == ("mail.send.request", {"text": "max@example.com | Update | Alles erledigt."})


def test_create_calendar_event_maps_to_calendar_create_request():
    assert _tool_call_to_event(
        "create_calendar_event",
        {"title": "Team-Meeting", "start": "2026-08-01 15:00", "duration_minutes": 60},
    ) == ("calendar.create.request", {"text": "Team-Meeting | 2026-08-01 15:00 | 60"})


def test_unknown_tool_name_returns_none():
    assert _tool_call_to_event("does_not_exist", {}) is None


def test_first_tool_use_finds_tool_block_among_text_blocks():
    class _Text:
        type = "text"

    class _Tool:
        type = "tool_use"
        name = "open_app"
        input = {"name": "Notepad"}

    assert _first_tool_use([_Text(), _Tool()]) == ("open_app", {"name": "Notepad"})


def test_first_tool_use_returns_none_without_tool_block():
    class _Text:
        type = "text"

    assert _first_tool_use([_Text()]) is None


# -- Voller Kontrollfluss über eine injizierte Fake-Claude-Antwort -----------
class _FakeToolUseBlock:
    def __init__(self, name: str, input: dict) -> None:  # noqa: A002
        self.type = "tool_use"
        self.id = "toolu_1"
        self.name = name
        self.input = input


class _FakeFinalMessage:
    def __init__(self, stop_reason: str, content: list) -> None:
        self.stop_reason = stop_reason
        self.content = content


class _FakeStream:
    """Steht für den Async-Context-Manager von ``client.messages.stream()``
    ein – liefert vorgegebene Text-Chunks über ``text_stream`` und eine
    vorgegebene ``final_message`` über ``get_final_message()``."""

    def __init__(self, text_chunks: list[str], final_message: _FakeFinalMessage) -> None:
        self._text_chunks = text_chunks
        self._final_message = final_message

    async def __aenter__(self) -> "_FakeStream":
        return self

    async def __aexit__(self, *exc) -> bool:  # noqa: ANN002
        return False

    async def _gen(self):
        for chunk in self._text_chunks:
            yield chunk

    @property
    def text_stream(self):
        return self._gen()

    async def get_final_message(self) -> _FakeFinalMessage:
        return self._final_message


class _FakeMessagesApi:
    def __init__(self, stream: _FakeStream) -> None:
        self._stream = stream
        self.last_kwargs: dict | None = None

    def stream(self, **kwargs):  # noqa: ANN003
        self.last_kwargs = kwargs
        return self._stream


class _FakeClaudeClient:
    def __init__(self, stream: _FakeStream) -> None:
        self.messages = _FakeMessagesApi(stream)


async def _engine_with_memory(bus: EventBus, tmp_path) -> ConversationEngine:
    """Baut eine ConversationEngine mit echter, angeschlossener MemoryEngine
    (statt einer leeren Bus) – ohne sie würde jedes ``engine.handle()`` bis
    zu 2s auf eine nie kommende ``memory.kv.get``/``memory.search``-Antwort
    warten (Timeout in ``request()``), was die Tests unnötig verlangsamt."""
    config = Config(vault_path=tmp_path / "vault", db_path=tmp_path / "db.sqlite")
    memory = MemoryEngine(bus, config, SecurityGate(bus))
    await memory.start()
    engine = ConversationEngine(bus, config, SecurityGate(bus))
    return engine


async def test_tool_use_without_preamble_dispatches_with_same_id_and_no_chat_response(tmp_path):
    bus = EventBus()
    engine = await _engine_with_memory(bus, tmp_path)
    await engine.start()
    engine._client = _FakeClaudeClient(
        _FakeStream([], _FakeFinalMessage("tool_use", [_FakeToolUseBlock("open_app", {"name": "Spotify"})]))
    )

    automation_events: list[Event] = []
    responses: list[Event] = []
    bus.subscribe("automation.request", lambda e: automation_events.append(e))
    bus.subscribe("chat.response", lambda e: responses.append(e))

    await engine.handle(Event("chat.request", {"id": "c1", "text": "Öffne Spotify"}))

    assert len(automation_events) == 1
    assert automation_events[0].data == {"action": "open_app", "name": "Spotify", "id": "c1"}
    # Kein eigenes chat.response von der ConversationEngine - die Ziel-Engine
    # (hier: AutomationEngine, in diesem Test nicht angebunden) uebernimmt
    # die Antwort vollstaendig.
    assert responses == []


async def test_tool_use_passes_declared_tools_to_claude(tmp_path):
    bus = EventBus()
    engine = await _engine_with_memory(bus, tmp_path)
    await engine.start()
    fake_stream = _FakeStream([], _FakeFinalMessage("tool_use", [_FakeToolUseBlock("list_downloads", {})]))
    client = _FakeClaudeClient(fake_stream)
    engine._client = client

    await engine.handle(Event("chat.request", {"id": "c2", "text": "Was liegt in meinen Downloads?"}))

    assert client.messages.last_kwargs["tools"] == _TOOLS


async def test_tool_use_with_preamble_closes_original_message_and_dispatches_with_new_id(tmp_path):
    bus = EventBus()
    engine = await _engine_with_memory(bus, tmp_path)
    await engine.start()
    engine._client = _FakeClaudeClient(
        _FakeStream(
            ["Klar, ", "einen Moment. "],
            _FakeFinalMessage("tool_use", [_FakeToolUseBlock("open_app", {"name": "Notepad"})]),
        )
    )

    automation_events: list[Event] = []
    responses: list[Event] = []
    bus.subscribe("automation.request", lambda e: automation_events.append(e))
    bus.subscribe("chat.response", lambda e: responses.append(e))

    await engine.handle(Event("chat.request", {"id": "c3", "text": "Mach Notepad auf"}))

    # Die vor dem Werkzeug-Aufruf gestreamte Vorrede wird als eigene,
    # abgeschlossene Antwort auf die ORIGINAL-ID beendet ...
    assert len(responses) == 1
    assert responses[0].data == {"id": "c3", "text": "Klar, einen Moment. ", "final": True}
    # ... und der Werkzeug-Aufruf bekommt eine ANDERE ID, damit sein
    # chat.token/chat.response nicht an die bereits abgeschlossene
    # Sprechblase angehaengt wird (siehe frontend/src/store/hud.ts).
    assert len(automation_events) == 1
    assert automation_events[0].data["action"] == "open_app"
    assert automation_events[0].data["id"] != "c3"


async def test_normal_text_reply_without_tool_use_is_unaffected(tmp_path):
    bus = EventBus()
    engine = await _engine_with_memory(bus, tmp_path)
    await engine.start()
    engine._client = _FakeClaudeClient(
        _FakeStream(["Hallo ", "Sir."], _FakeFinalMessage("end_turn", []))
    )

    tokens: list[str] = []
    responses: list[Event] = []
    automation_events: list[Event] = []
    bus.subscribe("chat.token", lambda e: tokens.append(e.data["text"]))
    bus.subscribe("chat.response", lambda e: responses.append(e))
    bus.subscribe("automation.request", lambda e: automation_events.append(e))

    await engine.handle(Event("chat.request", {"id": "c4", "text": "Hallo"}))

    assert tokens == ["Hallo ", "Sir."]
    assert responses[0].data == {"id": "c4", "text": "Hallo Sir.", "final": True}
    assert automation_events == []
    assert engine._history[-2:] == [
        {"role": "user", "content": "Hallo"},
        {"role": "assistant", "content": "Hallo Sir."},
    ]
