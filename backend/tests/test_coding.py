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
from aphelios.engines.coding_engine import (
    CodingEngine,
    _first_code_block,
    _parse_code_file_request,
)


def _engine(bus: EventBus) -> CodingEngine:
    return CodingEngine(bus, Config(), SecurityGate(bus))


def _auto_approve(bus: EventBus) -> None:
    async def approve(event: Event) -> None:
        await bus.publish(Event("confirmation.approve", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", approve)


def _auto_deny(bus: EventBus) -> None:
    async def deny(event: Event) -> None:
        await bus.publish(Event("confirmation.deny", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", deny)


class _FakeStream:
    """Minimaler Ersatz für ``client.messages.stream()`` – _generate_code()
    liest nur ``text_stream``, kein ``get_final_message()`` nötig (anders als
    der Tool-Use-Kontrollfluss in test_tool_use.py)."""

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    async def __aenter__(self) -> "_FakeStream":
        return self

    async def __aexit__(self, *exc) -> bool:  # noqa: ANN002
        return False

    async def _gen(self):
        for chunk in self._chunks:
            yield chunk

    @property
    def text_stream(self):
        return self._gen()


class _FakeMessagesApi:
    def __init__(self, stream: _FakeStream) -> None:
        self._stream = stream

    def stream(self, **kwargs):  # noqa: ANN003
        return self._stream


class _FakeClaudeClient:
    def __init__(self, chunks: list[str]) -> None:
        self.messages = _FakeMessagesApi(_FakeStream(chunks))


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


# -- Pure Parsing/Extraktions-Helfer (kein SDK nötig) -------------------------
def test_parse_code_file_request_unquoted_path():
    assert _parse_code_file_request("hello.py Schreibe eine Begrüßungsfunktion") == (
        "hello.py",
        "Schreibe eine Begrüßungsfunktion",
    )


def test_parse_code_file_request_quoted_path_with_spaces():
    assert _parse_code_file_request('"C:\\Mein Ordner\\a.py" Schreibe X') == (
        "C:\\Mein Ordner\\a.py",
        "Schreibe X",
    )


def test_parse_code_file_request_empty_text():
    assert _parse_code_file_request("") is None
    assert _parse_code_file_request("   ") is None


def test_parse_code_file_request_unterminated_quote():
    assert _parse_code_file_request('"C:\\ohne Ende') is None


def test_first_code_block_extracts_first_fenced_block():
    markdown = "Hier ist der Code:\n\n```python\nprint('hi')\n```\n\nErklärung."
    assert _first_code_block(markdown) == "print('hi')"


def test_first_code_block_ignores_later_blocks():
    markdown = "```python\nA\n```\nText\n```python\nB\n```"
    assert _first_code_block(markdown) == "A"


def test_first_code_block_returns_none_without_any_block():
    assert _first_code_block("Nur Text, kein Code.") is None


# -- /code-datei: Fehlerfälle vor jedem Datei-Zugriff -------------------------
async def test_write_file_without_request_reports_clear_error():
    bus = EventBus()
    engine = _engine(bus)
    await engine.start()
    responses: list[dict] = []
    bus.subscribe("chat.response", lambda e: responses.append(e.data))

    await engine.handle(Event("coding.request", {"id": "w1", "action": "write_file", "text": "hello.py"}))

    assert "beschreiben" in responses[0]["text"].lower()


async def test_write_file_without_api_key_reports_honest_message(tmp_path):
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)
    await engine.start()
    responses: list[dict] = []
    bus.subscribe("chat.response", lambda e: responses.append(e.data))

    path = tmp_path / "hello.py"
    await engine.handle(
        Event("coding.request", {"id": "w2", "action": "write_file", "text": f"{path} Begrüßungsfunktion"})
    )

    assert "ANTHROPIC_API_KEY" in responses[0]["text"]
    assert not path.exists()


# -- /code-datei: SecurityGate ------------------------------------------------
async def test_write_file_denied_never_writes(tmp_path):
    bus = EventBus()
    _auto_deny(bus)
    engine = _engine(bus)
    await engine.start()
    engine._client = _FakeClaudeClient(["```python\nprint('hi')\n```"])
    responses: list[dict] = []
    bus.subscribe("chat.response", lambda e: responses.append(e.data))

    path = tmp_path / "hello.py"
    await engine.handle(
        Event("coding.request", {"id": "w3", "action": "write_file", "text": f"{path} Begrüßung"})
    )

    assert "abgelehnt" in responses[0]["text"].lower()
    assert not path.exists()


async def test_write_file_confirmation_distinguishes_create_and_overwrite(tmp_path):
    bus = EventBus()
    confirmations: list[dict] = []

    async def approve_and_capture(event: Event) -> None:
        confirmations.append(event.data)
        await bus.publish(Event("confirmation.approve", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", approve_and_capture)
    engine = _engine(bus)
    await engine.start()
    engine._client = _FakeClaudeClient(["```python\nprint('hi')\n```"])

    existing = tmp_path / "existiert-schon.py"
    existing.write_text("alt")
    new_path = tmp_path / "neu.py"

    await engine.handle(
        Event("coding.request", {"id": "w4", "action": "write_file", "text": f"{existing} X"})
    )
    await engine.handle(
        Event("coding.request", {"id": "w5", "action": "write_file", "text": f"{new_path} X"})
    )

    assert "überschreiben" in confirmations[0]["reason"]
    assert "anlegen" in confirmations[1]["reason"]


# -- /code-datei: Verzeichnis fehlt -------------------------------------------
async def test_write_file_missing_parent_directory_reports_clear_error(tmp_path):
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)
    await engine.start()
    engine._client = _FakeClaudeClient(["```python\nprint('hi')\n```"])
    responses: list[dict] = []
    bus.subscribe("chat.response", lambda e: responses.append(e.data))

    path = tmp_path / "existiert-nicht" / "hello.py"
    await engine.handle(
        Event("coding.request", {"id": "w6", "action": "write_file", "text": f"{path} X"})
    )

    assert "existiert nicht" in responses[0]["text"]
    assert not path.exists()


# -- /code-datei: Erfolgreiches Schreiben -------------------------------------
async def test_write_file_saves_first_code_block_to_disk(tmp_path):
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)
    await engine.start()
    engine._client = _FakeClaudeClient(
        ["```python\n", "def gruss():\n    return 'Hallo'\n", "```\n\nEine einfache Funktion."]
    )
    responses: list[dict] = []
    bus.subscribe("chat.response", lambda e: responses.append(e.data))

    path = tmp_path / "hello.py"
    await engine.handle(
        Event(
            "coding.request",
            {"id": "w7", "action": "write_file", "text": f"{path} Schreibe eine Begrüßungsfunktion"},
        )
    )

    assert path.read_text(encoding="utf-8") == "def gruss():\n    return 'Hallo'"
    # Zwei Antworten: die Code-Erklärung (id "w7") und die Speicher-
    # Bestätigung (eigene ID "w7-save", siehe Docstring zur Kollisionsvermeidung).
    assert len(responses) == 2
    assert responses[0]["text"].startswith("```python")
    assert "Gespeichert unter" in responses[1]["text"]
    assert "bereit für VS Code" in responses[1]["text"]


async def test_write_file_without_code_block_saves_nothing(tmp_path):
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)
    await engine.start()
    engine._client = _FakeClaudeClient(["Das kann ich so nicht beantworten, ohne Code."])
    responses: list[dict] = []
    bus.subscribe("chat.response", lambda e: responses.append(e.data))

    path = tmp_path / "hello.py"
    await engine.handle(
        Event("coding.request", {"id": "w8", "action": "write_file", "text": f"{path} irgendwas"})
    )

    assert not path.exists()
    assert "Kein Code-Block" in responses[1]["text"]
