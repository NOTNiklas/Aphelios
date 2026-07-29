"""Tests für das Termin-Anlegen der CalendarEngine (Alpha 1.7): Format-/
Datums-Erkennung, SecurityGate-Integration (jedes Anlegen MUSS bestätigt
werden) und Fehlerfälle – über eine injizierte Fake-Calendar-Service (siehe
test_mail_send.py für dieselbe Dependency-Injection).
"""

from __future__ import annotations

from datetime import datetime

from aphelios.core.config import Config
from aphelios.core.event_bus import Event, EventBus
from aphelios.core.security import SecurityGate
from aphelios.engines.calendar_engine import CalendarEngine, _parse_create_request


class _FakeCalendarService:
    """Steht für den ``events().insert(...).execute()``-Aufrufkettenteil des
    echten Google-Calendar-API-Clients ein."""

    def __init__(self, fail_with: Exception | None = None) -> None:
        self.created: list[tuple[str, dict]] = []
        self._fail_with = fail_with
        self._last: tuple[str, dict] | None = None

    def events(self) -> "_FakeCalendarService":
        return self

    def insert(self, calendarId: str, body: dict) -> "_FakeCalendarService":  # noqa: N803
        self._last = (calendarId, body)
        return self

    def execute(self) -> dict:
        if self._fail_with is not None:
            raise self._fail_with
        assert self._last is not None
        self.created.append(self._last)
        return {"id": "evt123"}


def _engine(bus: EventBus) -> CalendarEngine:
    return CalendarEngine(bus, Config(), SecurityGate(bus))


def _auto_approve(bus: EventBus) -> None:
    async def approve(event: Event) -> None:
        await bus.publish(Event("confirmation.approve", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", approve)


def _auto_deny(bus: EventBus) -> None:
    async def deny(event: Event) -> None:
        await bus.publish(Event("confirmation.deny", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", deny)


async def _run(engine: CalendarEngine, text: str) -> str:
    await engine.start()
    responses: list[dict] = []
    engine.bus.subscribe("chat.response", lambda e: responses.append(e.data))
    await engine.handle_create(Event("calendar.create.request", {"id": "t1", "text": text}))
    return responses[-1]["text"]


# -- Format-/Datums-Erkennung -----------------------------------------------------
def test_parse_splits_title_start_and_duration():
    result = _parse_create_request("Team-Meeting | 2026-08-01 15:00 | 60")
    assert result is not None
    title, start, duration = result
    assert title == "Team-Meeting"
    assert start.replace(tzinfo=None) == datetime(2026, 8, 1, 15, 0)
    assert duration == 60


def test_parse_rejects_wrong_field_count():
    assert _parse_create_request("nur ein feld") is None
    assert _parse_create_request("a | b") is None


def test_parse_rejects_invalid_date_format():
    assert _parse_create_request("Meeting | morgen um 15 Uhr | 60") is None


def test_parse_rejects_non_integer_duration():
    assert _parse_create_request("Meeting | 2026-08-01 15:00 | eine Stunde") is None


def test_parse_rejects_zero_or_negative_duration():
    assert _parse_create_request("Meeting | 2026-08-01 15:00 | 0") is None
    assert _parse_create_request("Meeting | 2026-08-01 15:00 | -30") is None


def test_parse_rejects_empty_text():
    assert _parse_create_request("") is None


# -- Nicht verbunden / falsches Format -------------------------------------------
async def test_missing_format_reports_clear_error():
    bus = EventBus()
    engine = _engine(bus)
    text = await _run(engine, "kein pipe hier")
    assert "Format" in text


async def test_not_connected_reports_clear_error():
    bus = EventBus()
    engine = _engine(bus)  # Config() ohne Google-Anmeldung -> _service bleibt None

    text = await _run(engine, "Meeting | 2026-08-01 15:00 | 60")

    assert "Google nicht verbunden" in text
    assert "google_auth.py" in text


# -- SecurityGate: jedes Anlegen MUSS bestätigt werden ----------------------------
async def test_denied_never_creates():
    bus = EventBus()
    _auto_deny(bus)
    engine = _engine(bus)
    await engine.start()
    engine._service = _FakeCalendarService()

    responses: list[dict] = []
    bus.subscribe("chat.response", lambda e: responses.append(e.data))
    await engine.handle_create(
        Event("calendar.create.request", {"id": "t2", "text": "Meeting | 2026-08-01 15:00 | 60"})
    )

    assert "abgelehnt" in responses[0]["text"].lower()
    assert engine._service.created == []


async def test_confirmation_names_title_and_start():
    bus = EventBus()
    confirmations: list[dict] = []

    async def approve_and_capture(event: Event) -> None:
        confirmations.append(event.data)
        await bus.publish(Event("confirmation.approve", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", approve_and_capture)
    engine = _engine(bus)
    await engine.start()
    engine._service = _FakeCalendarService()

    await engine.handle_create(
        Event("calendar.create.request", {"id": "t3", "text": "Team-Meeting | 2026-08-01 15:00 | 60"})
    )

    assert confirmations[0]["action"] == "Termin anlegen"
    assert "Team-Meeting" in confirmations[0]["target"]
    assert "01.08.2026" in confirmations[0]["target"]


# -- Erfolgreiches Anlegen ---------------------------------------------------------
async def test_successful_create_computes_correct_end_time():
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)
    await engine.start()
    fake = _FakeCalendarService()
    engine._service = fake
    responses: list[dict] = []
    bus.subscribe("chat.response", lambda e: responses.append(e.data))

    await engine.handle_create(
        Event("calendar.create.request", {"id": "t4", "text": "Team-Meeting | 2026-08-01 15:00 | 90"})
    )
    text = responses[0]["text"]

    assert "angelegt" in text.lower()
    assert "Team-Meeting" in text
    assert len(fake.created) == 1
    calendar_id, body = fake.created[0]
    assert calendar_id == "primary"
    assert body["summary"] == "Team-Meeting"
    start_dt = datetime.fromisoformat(body["start"]["dateTime"])
    end_dt = datetime.fromisoformat(body["end"]["dateTime"])
    assert (end_dt - start_dt).total_seconds() == 90 * 60


# -- Fehlerfälle -------------------------------------------------------------------
async def test_insufficient_scope_error_hints_at_reauth():
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)
    await engine.start()
    engine._service = _FakeCalendarService(fail_with=RuntimeError("Insufficient Permission (scope)"))
    responses: list[dict] = []
    bus.subscribe("chat.response", lambda e: responses.append(e.data))

    await engine.handle_create(
        Event("calendar.create.request", {"id": "t5", "text": "Meeting | 2026-08-01 15:00 | 60"})
    )
    text = responses[0]["text"]

    assert "nicht angelegt werden" in text
    assert "google_auth.py" in text


async def test_generic_error_does_not_show_scope_hint():
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)
    await engine.start()
    engine._service = _FakeCalendarService(fail_with=RuntimeError("network timeout"))
    responses: list[dict] = []
    bus.subscribe("chat.response", lambda e: responses.append(e.data))

    await engine.handle_create(
        Event("calendar.create.request", {"id": "t6", "text": "Meeting | 2026-08-01 15:00 | 60"})
    )
    text = responses[0]["text"]

    assert "nicht angelegt werden" in text
    assert "google_auth.py" not in text
