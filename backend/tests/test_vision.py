"""Tests für die VisionEngine (Alpha 1.4): Fehler-Heuristik, SecurityGate-
Integration (jede Bildschirmaufnahme MUSS bestätigt werden) und die drei
Aktionen (describe/ocr/find_error) über injizierte Screenshot-/OCR-Funktionen.

Läuft bewusst ohne ``ANTHROPIC_API_KEY`` (wie test_alpha11.py für Planning/
Reasoning) – testet damit die vollständig offline nutzbaren Pfade (OCR-
Fallback statt Claude-Vision-Interpretation), ohne die Anthropic-SDK-
Streaming-Schnittstelle mocken zu müssen. Screenshot/OCR selbst brauchen eine
echte Anzeige bzw. eine Tesseract-Installation – hier per Monkeypatch der
Modul-Funktionen ``_grab_screenshot_png``/``_extract_text`` ersetzt, analog zu
``os.startfile`` in test_automation.py und den injizierten Fake-Modellen in
test_voice.py.
"""

from __future__ import annotations

from aphelios.core.config import Config
from aphelios.core.event_bus import Event, EventBus
from aphelios.core.security import SecurityGate
from aphelios.engines import vision_engine as vision_module
from aphelios.engines.vision_engine import VisionEngine, _ERROR_PATTERN


def _engine(bus: EventBus) -> VisionEngine:
    return VisionEngine(bus, Config(), SecurityGate(bus))


def _auto_approve(bus: EventBus) -> None:
    async def approve(event: Event) -> None:
        await bus.publish(Event("confirmation.approve", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", approve)


def _auto_deny(bus: EventBus) -> None:
    async def deny(event: Event) -> None:
        await bus.publish(Event("confirmation.deny", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", deny)


async def _run(engine: VisionEngine, action: str, **data) -> str:
    await engine.start()
    responses: list[dict] = []
    engine.bus.subscribe("chat.response", lambda e: responses.append(e.data))
    await engine.handle(Event("vision.request", {"id": "t1", "action": action, **data}))
    return responses[-1]["text"]


# -- Fehler-Heuristik ----------------------------------------------------------
def test_error_pattern_matches_common_error_phrases():
    assert _ERROR_PATTERN.search("Ein Fehler ist aufgetreten")
    assert _ERROR_PATTERN.search("An unexpected error occurred")
    assert _ERROR_PATTERN.search("Traceback (most recent call last):")
    assert _ERROR_PATTERN.search("Die Anwendung reagiert nicht mehr")
    assert _ERROR_PATTERN.search("Zugriff verweigert")


def test_error_pattern_does_not_match_normal_text():
    assert not _ERROR_PATTERN.search("Willkommen bei APHELIOS, Sir.")


# -- Unbekannte Aktion -----------------------------------------------------------
async def test_unknown_action_reports_clear_error():
    bus = EventBus()
    engine = _engine(bus)
    text = await _run(engine, "does_not_exist")
    assert "Unbekannte Vision-Aktion" in text


# -- SecurityGate: jede Aktion MUSS bestätigt werden ----------------------------
async def test_describe_denied_never_captures_screen(monkeypatch):
    called = False

    def fake_capture():
        nonlocal called
        called = True
        return b"PNG"

    monkeypatch.setattr(vision_module, "_grab_screenshot_png", fake_capture)
    bus = EventBus()
    _auto_deny(bus)
    engine = _engine(bus)

    text = await _run(engine, "describe", question="")

    assert "abgelehnt" in text.lower()
    assert called is False


async def test_ocr_denied_never_captures_screen(monkeypatch):
    called = False

    def fake_capture():
        nonlocal called
        called = True
        return b"PNG"

    monkeypatch.setattr(vision_module, "_grab_screenshot_png", fake_capture)
    bus = EventBus()
    _auto_deny(bus)
    engine = _engine(bus)

    text = await _run(engine, "ocr")

    assert "abgelehnt" in text.lower()
    assert called is False


async def test_find_error_denied_never_captures_screen(monkeypatch):
    called = False

    def fake_capture():
        nonlocal called
        called = True
        return b"PNG"

    monkeypatch.setattr(vision_module, "_grab_screenshot_png", fake_capture)
    bus = EventBus()
    _auto_deny(bus)
    engine = _engine(bus)

    text = await _run(engine, "find_error")

    assert "abgelehnt" in text.lower()
    assert called is False


async def test_describe_confirmation_names_the_real_action(monkeypatch):
    # Transparenz-Prinzip (docs/security.md): der Bestätigungsdialog muss
    # erkennen lassen, dass hier der Bildschirm aufgenommen wird.
    monkeypatch.setattr(vision_module, "_grab_screenshot_png", lambda: b"PNG")
    monkeypatch.setattr(vision_module, "_extract_text", lambda png, lang: "")
    bus = EventBus()
    confirmations: list[dict] = []

    async def approve_and_capture(event: Event) -> None:
        confirmations.append(event.data)
        await bus.publish(Event("confirmation.approve", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", approve_and_capture)
    engine = _engine(bus)

    await _run(engine, "describe", question="")

    assert confirmations[0]["action"] == "Bildschirm aufnehmen"


# -- /sieh (describe), ohne API-Key -> OCR-Fallback -----------------------------
async def test_describe_without_api_key_falls_back_to_ocr_text(monkeypatch):
    monkeypatch.setattr(vision_module, "_grab_screenshot_png", lambda: b"PNG")
    monkeypatch.setattr(vision_module, "_extract_text", lambda png, lang: "Hallo Welt")
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, "describe", question="Was steht da?")

    assert "kein" in text.lower() and "api" in text.lower()
    assert "Hallo Welt" in text


async def test_describe_without_api_key_and_no_text_reports_that_clearly(monkeypatch):
    monkeypatch.setattr(vision_module, "_grab_screenshot_png", lambda: b"PNG")
    monkeypatch.setattr(vision_module, "_extract_text", lambda png, lang: "")
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, "describe", question="")

    assert "kein text" in text.lower()
    assert "api" in text.lower()


async def test_describe_reports_screenshot_failure(monkeypatch):
    def fail():
        raise RuntimeError("no display")

    monkeypatch.setattr(vision_module, "_grab_screenshot_png", fail)
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, "describe", question="")

    assert "Bildschirmaufnahme fehlgeschlagen" in text
    assert "no display" in text


async def test_describe_reports_missing_ocr_dependencies(monkeypatch):
    monkeypatch.setattr(vision_module, "_grab_screenshot_png", lambda: b"PNG")

    def fail(png, lang):
        raise ImportError("no module named pytesseract")

    monkeypatch.setattr(vision_module, "_extract_text", fail)
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, "describe", question="")

    assert "pytesseract" in text.lower() or "pillow" in text.lower()
    assert "nicht installiert" in text.lower()


async def test_describe_reports_tesseract_not_found(monkeypatch):
    monkeypatch.setattr(vision_module, "_grab_screenshot_png", lambda: b"PNG")

    def fail(png, lang):
        raise Exception("tesseract is not installed or it's not in your PATH")

    monkeypatch.setattr(vision_module, "_extract_text", fail)
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, "describe", question="")

    assert "OCR fehlgeschlagen" in text
    assert "PATH" in text


# -- /lies (ocr) -----------------------------------------------------------------
async def test_ocr_returns_extracted_text(monkeypatch):
    monkeypatch.setattr(vision_module, "_grab_screenshot_png", lambda: b"PNG")
    monkeypatch.setattr(vision_module, "_extract_text", lambda png, lang: "Erkannter Text hier")
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, "ocr")

    assert text == "Erkannter Text hier"


async def test_ocr_reports_no_text_found(monkeypatch):
    monkeypatch.setattr(vision_module, "_grab_screenshot_png", lambda: b"PNG")
    monkeypatch.setattr(vision_module, "_extract_text", lambda png, lang: "   ")
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, "ocr")

    assert "Kein Text erkannt" in text


async def test_ocr_uses_configured_language(monkeypatch):
    seen_lang = []
    monkeypatch.setattr(vision_module, "_grab_screenshot_png", lambda: b"PNG")

    def fake_extract(png, lang):
        seen_lang.append(lang)
        return "x"

    monkeypatch.setattr(vision_module, "_extract_text", fake_extract)
    bus = EventBus()
    _auto_approve(bus)
    engine = VisionEngine(bus, Config(ocr_lang="eng"), SecurityGate(bus))

    await _run(engine, "ocr")

    assert seen_lang == ["eng"]


# -- /fehler (find_error) ---------------------------------------------------------
async def test_find_error_reports_none_found(monkeypatch):
    monkeypatch.setattr(vision_module, "_grab_screenshot_png", lambda: b"PNG")
    monkeypatch.setattr(vision_module, "_extract_text", lambda png, lang: "Alles läuft normal.")
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, "find_error")

    assert "Keine Fehlermeldung" in text


async def test_find_error_reports_detected_text_without_api_key(monkeypatch):
    monkeypatch.setattr(vision_module, "_grab_screenshot_png", lambda: b"PNG")
    monkeypatch.setattr(
        vision_module, "_extract_text", lambda png, lang: "Fatal Error: Datei nicht gefunden"
    )
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, "find_error")

    assert "Fatal Error" in text
    assert "api" in text.lower()
