"""Tests für die OfficeEngine (Alpha 1.6): Pfad-Erkennung, SecurityGate-
Integration (jeder Datei-Zugriff MUSS bestätigt werden) und die Offline-
testbaren Pfade (kein ANTHROPIC_API_KEY -> roher Text) über eine injizierte
``_extract_document_text``-Funktion.

Läuft bewusst ohne ``ANTHROPIC_API_KEY`` (wie test_vision.py/test_browser.py)
– testet damit die vollständig offline nutzbaren Pfade, ohne die
Anthropic-SDK-Streaming-Schnittstelle mocken zu müssen. Die echte
Text-Extraktion (python-docx/openpyxl/python-pptx/pypdf) wurde manuell gegen
echte, real erzeugte .docx/.xlsx/.pptx-Dateien verifiziert (siehe
docs/office.md) – hier per Monkeypatch von ``_extract_document_text``
ersetzt, analog zu ``_grab_screenshot_png`` in test_vision.py und
``_fetch_page`` in test_browser.py.
"""

from __future__ import annotations

from aphelios.core.config import Config
from aphelios.core.event_bus import Event, EventBus
from aphelios.core.security import SecurityGate
from aphelios.engines import office_engine as office_module
from aphelios.engines.office_engine import OfficeEngine, _parse_document_request


def _engine(bus: EventBus) -> OfficeEngine:
    return OfficeEngine(bus, Config(), SecurityGate(bus))


def _auto_approve(bus: EventBus) -> None:
    async def approve(event: Event) -> None:
        await bus.publish(Event("confirmation.approve", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", approve)


def _auto_deny(bus: EventBus) -> None:
    async def deny(event: Event) -> None:
        await bus.publish(Event("confirmation.deny", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", deny)


async def _run(engine: OfficeEngine, text: str) -> str:
    await engine.start()
    responses: list[dict] = []
    engine.bus.subscribe("chat.response", lambda e: responses.append(e.data))
    await engine.handle(Event("office.request", {"id": "t1", "text": text}))
    return responses[-1]["text"]


# -- Pfad-/Fragen-Erkennung -----------------------------------------------------
def test_parse_recognizes_docx_without_question():
    assert _parse_document_request("bericht.docx") == ("bericht.docx", "")


def test_parse_splits_path_and_question():
    assert _parse_document_request("bericht.docx Was ist das Fazit?") == (
        "bericht.docx",
        "Was ist das Fazit?",
    )


def test_parse_handles_windows_path_with_spaces():
    # Regression: ein simples Leerzeichen-Split würde einen Pfad wie
    # "C:\Users\User\Meine Dokumente\Bericht.docx" an der falschen Stelle
    # abschneiden - die Endung ist der zuverlässigere Trenner.
    assert _parse_document_request(
        "C:\\Users\\User\\Meine Dokumente\\Bericht.docx Was steht drin?"
    ) == ("C:\\Users\\User\\Meine Dokumente\\Bericht.docx", "Was steht drin?")


def test_parse_recognizes_all_supported_extensions():
    for ext in ("docx", "xlsx", "pptx", "pdf"):
        assert _parse_document_request(f"datei.{ext}") == (f"datei.{ext}", "")


def test_parse_rejects_unsupported_extension():
    assert _parse_document_request("datei.txt") is None


def test_parse_rejects_text_without_any_path():
    assert _parse_document_request("was ist die hauptstadt von frankreich") is None


def test_parse_rejects_empty_text():
    assert _parse_document_request("") is None
    assert _parse_document_request("   ") is None


# -- Fehlende/ungültige Anfrage --------------------------------------------------
async def test_missing_path_reports_clear_error():
    bus = EventBus()
    engine = _engine(bus)
    text = await _run(engine, "")
    assert "Pfad" in text


# -- SecurityGate: jede Anfrage MUSS bestätigt werden ----------------------------
async def test_denied_never_reads_file(monkeypatch, tmp_path):
    called = False
    existing = tmp_path / "bericht.docx"
    existing.write_text("x")

    def fake_extract(path):
        nonlocal called
        called = True
        return "Text"

    monkeypatch.setattr(office_module, "_extract_document_text", fake_extract)
    bus = EventBus()
    _auto_deny(bus)
    engine = _engine(bus)

    text = await _run(engine, str(existing))

    assert "abgelehnt" in text.lower()
    assert called is False


async def test_confirmation_names_the_real_action_and_path(monkeypatch, tmp_path):
    existing = tmp_path / "bericht.docx"
    existing.write_text("x")
    monkeypatch.setattr(office_module, "_extract_document_text", lambda path: "Text")
    bus = EventBus()
    confirmations: list[dict] = []

    async def approve_and_capture(event: Event) -> None:
        confirmations.append(event.data)
        await bus.publish(Event("confirmation.approve", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", approve_and_capture)
    engine = _engine(bus)

    await _run(engine, str(existing))

    assert confirmations[0]["action"] == "Dokument lesen"
    assert confirmations[0]["target"] == str(existing)


# -- Datei nicht gefunden ---------------------------------------------------------
async def test_missing_file_reports_clear_error(monkeypatch, tmp_path):
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, str(tmp_path / "existiert-nicht.docx"))

    assert "nicht gefunden" in text.lower()


# -- Ohne API-Key: roher Dokumenttext ---------------------------------------------
async def test_without_api_key_returns_raw_document_text(monkeypatch, tmp_path):
    existing = tmp_path / "bericht.docx"
    existing.write_text("x")
    monkeypatch.setattr(office_module, "_extract_document_text", lambda path: "Umsatz stieg um 10%.")
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, f"{existing} Wie hoch war der Umsatz?")

    assert "kein" in text.lower() and "api" in text.lower()
    assert "bericht.docx" in text
    assert "Umsatz stieg um 10%." in text


async def test_empty_extracted_text_reports_that_clearly(monkeypatch, tmp_path):
    existing = tmp_path / "leer.pdf"
    existing.write_text("x")
    monkeypatch.setattr(office_module, "_extract_document_text", lambda path: "   ")
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, str(existing))

    assert "kein Text gefunden" in text
    assert "leer.pdf" in text


# -- Fehlerfälle beim Lesen ---------------------------------------------------------
async def test_reports_missing_dependency(monkeypatch, tmp_path):
    existing = tmp_path / "bericht.xlsx"
    existing.write_text("x")

    def fail(path):
        raise ImportError("No module named 'openpyxl'")

    monkeypatch.setattr(office_module, "_extract_document_text", fail)
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, str(existing))

    assert "openpyxl" in text.lower() or "zusätzliches paket" in text.lower()
    assert 'pip install -e ".[office]"' in text


async def test_reports_extraction_failure(monkeypatch, tmp_path):
    existing = tmp_path / "kaputt.pptx"
    existing.write_text("x")

    def fail(path):
        raise Exception("Datei ist beschädigt oder kein gültiges PPTX")

    monkeypatch.setattr(office_module, "_extract_document_text", fail)
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, str(existing))

    assert "konnte nicht gelesen werden" in text
    assert "beschädigt" in text
