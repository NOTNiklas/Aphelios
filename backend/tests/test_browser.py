"""Tests für die BrowserEngine (Alpha 1.6): URL-Erkennung, SecurityGate-
Integration (jeder Seitenaufruf MUSS bestätigt werden) und die Offline-testbaren
Pfade (kein ANTHROPIC_API_KEY -> roher Seitentext) über eine injizierte
``_fetch_page``-Funktion.

Läuft bewusst ohne ``ANTHROPIC_API_KEY`` (wie test_vision.py) – testet damit
die vollständig offline nutzbaren Pfade, ohne die Anthropic-SDK-Streaming-
Schnittstelle mocken zu müssen. Das echte Playwright-Browsing selbst braucht
ein installiertes Chromium (``playwright install chromium``) – hier per
Monkeypatch von ``_fetch_page`` ersetzt, analog zu ``_grab_screenshot_png``
in test_vision.py.
"""

from __future__ import annotations

from aphelios.core.config import Config
from aphelios.core.event_bus import Event, EventBus
from aphelios.core.security import SecurityGate
from aphelios.engines import browser_engine as browser_module
from aphelios.engines.browser_engine import BrowserEngine, _parse_browse_request


def _engine(bus: EventBus) -> BrowserEngine:
    return BrowserEngine(bus, Config(), SecurityGate(bus))


def _auto_approve(bus: EventBus) -> None:
    async def approve(event: Event) -> None:
        await bus.publish(Event("confirmation.approve", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", approve)


def _auto_deny(bus: EventBus) -> None:
    async def deny(event: Event) -> None:
        await bus.publish(Event("confirmation.deny", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", deny)


async def _run(engine: BrowserEngine, text: str) -> str:
    await engine.start()
    responses: list[dict] = []
    engine.bus.subscribe("chat.response", lambda e: responses.append(e.data))
    await engine.handle(Event("browser.request", {"id": "t1", "text": text}))
    return responses[-1]["text"]


# -- URL-Erkennung -------------------------------------------------------------
def test_parse_recognizes_bare_domain_and_adds_https():
    assert _parse_browse_request("example.com") == ("https://example.com", "")


def test_parse_keeps_explicit_scheme():
    assert _parse_browse_request("http://example.com Was steht da?") == (
        "http://example.com",
        "Was steht da?",
    )


def test_parse_splits_url_and_question():
    assert _parse_browse_request("https://example.com/docs Was ist der Titel?") == (
        "https://example.com/docs",
        "Was ist der Titel?",
    )


def test_parse_rejects_text_without_url():
    assert _parse_browse_request("was ist die hauptstadt von frankreich") is None


def test_parse_rejects_empty_text():
    assert _parse_browse_request("") is None
    assert _parse_browse_request("   ") is None


# -- Fehlende/ungültige URL ------------------------------------------------------
async def test_missing_url_reports_clear_error():
    bus = EventBus()
    engine = _engine(bus)
    text = await _run(engine, "")
    assert "URL" in text


async def test_text_without_url_reports_clear_error():
    bus = EventBus()
    engine = _engine(bus)
    text = await _run(engine, "was ist die hauptstadt von frankreich")
    assert "URL" in text


# -- SecurityGate: jede Anfrage MUSS bestätigt werden ---------------------------
async def test_denied_never_opens_page(monkeypatch):
    called = False

    async def fake_fetch(url, headless):
        nonlocal called
        called = True
        return "Titel", "Text"

    monkeypatch.setattr(browser_module, "_fetch_page", fake_fetch)
    bus = EventBus()
    _auto_deny(bus)
    engine = _engine(bus)

    text = await _run(engine, "example.com")

    assert "abgelehnt" in text.lower()
    assert called is False


async def test_confirmation_names_the_real_action_and_url(monkeypatch):
    async def fake_fetch(url, headless):
        return "Titel", "Text"

    monkeypatch.setattr(browser_module, "_fetch_page", fake_fetch)
    bus = EventBus()
    confirmations: list[dict] = []

    async def approve_and_capture(event: Event) -> None:
        confirmations.append(event.data)
        await bus.publish(Event("confirmation.approve", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", approve_and_capture)
    engine = _engine(bus)

    await _run(engine, "example.com")

    assert confirmations[0]["action"] == "Webseite öffnen"
    assert confirmations[0]["target"] == "https://example.com"


# -- Ohne API-Key: roher Seitentext ---------------------------------------------
async def test_without_api_key_returns_raw_page_text(monkeypatch):
    async def fake_fetch(url, headless):
        return "Beispiel-Titel", "Das ist der sichtbare Seitentext."

    monkeypatch.setattr(browser_module, "_fetch_page", fake_fetch)
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, "example.com Was steht da?")

    assert "kein" in text.lower() and "api" in text.lower()
    assert "Beispiel-Titel" in text
    assert "Das ist der sichtbare Seitentext." in text


async def test_empty_page_text_reports_that_clearly(monkeypatch):
    async def fake_fetch(url, headless):
        return "Leere Seite", ""

    monkeypatch.setattr(browser_module, "_fetch_page", fake_fetch)
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, "example.com")

    assert "kein Text" in text
    assert "Leere Seite" in text


# -- Fehlerfälle beim Öffnen der Seite -------------------------------------------
async def test_reports_missing_playwright_dependency(monkeypatch):
    async def fail(url, headless):
        raise ImportError("No module named 'playwright'")

    monkeypatch.setattr(browser_module, "_fetch_page", fail)
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, "example.com")

    assert "playwright" in text.lower()
    assert "nicht installiert" in text.lower()
    assert 'pip install -e ".[browser]"' in text


async def test_reports_page_open_failure(monkeypatch):
    async def fail(url, headless):
        raise RuntimeError("net::ERR_NAME_NOT_RESOLVED")

    monkeypatch.setattr(browser_module, "_fetch_page", fail)
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)

    text = await _run(engine, "does-not-exist.invalid")

    assert "Seite konnte nicht geöffnet werden" in text
    assert "ERR_NAME_NOT_RESOLVED" in text


# -- headless-Konfiguration wird durchgereicht -----------------------------------
async def test_uses_configured_headless_setting(monkeypatch):
    seen: list[bool] = []

    async def fake_fetch(url, headless):
        seen.append(headless)
        return "Titel", "Text"

    monkeypatch.setattr(browser_module, "_fetch_page", fake_fetch)
    bus = EventBus()
    _auto_approve(bus)
    engine = BrowserEngine(bus, Config(browser_headless=False), SecurityGate(bus))

    await _run(engine, "example.com")

    assert seen == [False]
