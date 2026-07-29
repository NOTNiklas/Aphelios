"""Tests für das Mail-Senden der MailEngine (Alpha 1.7): Format-Erkennung,
SecurityGate-Integration (jeder Sendevorgang MUSS bestätigt werden) und
Fehlerfälle – über eine injizierte Fake-Gmail-Service (dieselbe Dependency-
Injection wie ``engine._piper_voice``/``engine._chroma_collection`` in den
anderen Test-Dateien), damit kein echtes Google-Konto nötig ist.
"""

from __future__ import annotations

import base64

from aphelios.core.config import Config
from aphelios.core.event_bus import Event, EventBus
from aphelios.core.security import SecurityGate
from aphelios.engines.mail_engine import MailEngine, _parse_send_request


class _FakeGmailService:
    """Steht für den ``users().messages().send(...).execute()``-Aufrufkettenteil
    des echten Gmail-API-Clients ein."""

    def __init__(self, fail_with: Exception | None = None) -> None:
        self.sent: list[dict] = []
        self._fail_with = fail_with
        self._last_body: dict | None = None

    def users(self) -> "_FakeGmailService":
        return self

    def messages(self) -> "_FakeGmailService":
        return self

    def send(self, userId: str, body: dict) -> "_FakeGmailService":  # noqa: N803
        self._last_body = body
        return self

    def execute(self) -> dict:
        if self._fail_with is not None:
            raise self._fail_with
        self.sent.append(self._last_body)
        return {"id": "msg123"}


def _engine(bus: EventBus) -> MailEngine:
    return MailEngine(bus, Config(), SecurityGate(bus))


def _auto_approve(bus: EventBus) -> None:
    async def approve(event: Event) -> None:
        await bus.publish(Event("confirmation.approve", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", approve)


def _auto_deny(bus: EventBus) -> None:
    async def deny(event: Event) -> None:
        await bus.publish(Event("confirmation.deny", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", deny)


async def _run(engine: MailEngine, text: str) -> str:
    await engine.start()
    responses: list[dict] = []
    engine.bus.subscribe("chat.response", lambda e: responses.append(e.data))
    await engine.handle_send(Event("mail.send.request", {"id": "t1", "text": text}))
    return responses[-1]["text"]


# -- Format-Erkennung ------------------------------------------------------------
def test_parse_splits_three_pipe_separated_fields():
    assert _parse_send_request("max@example.com | Update | Alles erledigt.") == (
        "max@example.com",
        "Update",
        "Alles erledigt.",
    )


def test_parse_rejects_wrong_field_count():
    assert _parse_send_request("nur ein feld") is None
    assert _parse_send_request("a | b") is None
    assert _parse_send_request("a | b | c | d") is None


def test_parse_rejects_empty_field():
    assert _parse_send_request("max@example.com |  | Text") is None


def test_parse_rejects_empty_text():
    assert _parse_send_request("") is None


# -- Nicht verbunden / falsches Format -------------------------------------------
async def test_missing_format_reports_clear_error():
    bus = EventBus()
    engine = _engine(bus)
    text = await _run(engine, "kein pipe hier")
    assert "Format" in text


async def test_not_connected_reports_clear_error():
    bus = EventBus()
    engine = _engine(bus)  # Config() ohne Google-Anmeldung -> _service bleibt None

    text = await _run(engine, "max@example.com | Betreff | Text")

    assert "Google nicht verbunden" in text
    assert "google_auth.py" in text


# -- SecurityGate: jeder Sendevorgang MUSS bestätigt werden ----------------------
async def test_denied_never_sends():
    bus = EventBus()
    _auto_deny(bus)
    engine = _engine(bus)
    await engine.start()
    engine._service = _FakeGmailService()

    responses: list[dict] = []
    bus.subscribe("chat.response", lambda e: responses.append(e.data))
    await engine.handle_send(
        Event("mail.send.request", {"id": "t2", "text": "max@example.com | Betreff | Text"})
    )

    assert "abgelehnt" in responses[0]["text"].lower()
    assert engine._service.sent == []


async def test_confirmation_names_recipient_and_subject():
    bus = EventBus()
    confirmations: list[dict] = []

    async def approve_and_capture(event: Event) -> None:
        confirmations.append(event.data)
        await bus.publish(Event("confirmation.approve", {"id": event.data["id"]}))

    bus.subscribe("confirmation.request", approve_and_capture)
    engine = _engine(bus)
    await engine.start()
    engine._service = _FakeGmailService()

    await engine.handle_send(
        Event("mail.send.request", {"id": "t3", "text": "max@example.com | Update | Text"})
    )

    assert confirmations[0]["action"] == "Mail senden"
    assert "max@example.com" in confirmations[0]["target"]
    assert "Update" in confirmations[0]["target"]


# -- Erfolgreiches Senden ---------------------------------------------------------
async def test_successful_send_encodes_mime_message_correctly():
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)
    await engine.start()
    fake = _FakeGmailService()
    engine._service = fake
    responses: list[dict] = []
    bus.subscribe("chat.response", lambda e: responses.append(e.data))

    await engine.handle_send(
        Event("mail.send.request", {"id": "t4", "text": "max@example.com | Update | Alles erledigt."})
    )
    text = responses[0]["text"]

    assert "gesendet" in text.lower()
    assert "max@example.com" in text
    assert len(fake.sent) == 1
    raw = base64.urlsafe_b64decode(fake.sent[0]["raw"]).decode("utf-8")
    assert "To: max@example.com" in raw
    assert "Subject: Update" in raw
    assert "Alles erledigt." in raw


# -- Fehlerfälle -------------------------------------------------------------------
async def test_insufficient_scope_error_hints_at_reauth():
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)
    await engine.start()
    engine._service = _FakeGmailService(fail_with=RuntimeError("Insufficient Permission (scope)"))
    responses: list[dict] = []
    bus.subscribe("chat.response", lambda e: responses.append(e.data))

    await engine.handle_send(Event("mail.send.request", {"id": "t5", "text": "max@example.com | Betreff | Text"}))
    text = responses[0]["text"]

    assert "nicht gesendet werden" in text
    assert "google_auth.py" in text


async def test_generic_error_does_not_show_scope_hint():
    bus = EventBus()
    _auto_approve(bus)
    engine = _engine(bus)
    await engine.start()
    engine._service = _FakeGmailService(fail_with=RuntimeError("network timeout"))
    responses: list[dict] = []
    bus.subscribe("chat.response", lambda e: responses.append(e.data))

    await engine.handle_send(Event("mail.send.request", {"id": "t6", "text": "max@example.com | Betreff | Text"}))
    text = responses[0]["text"]

    assert "nicht gesendet werden" in text
    assert "google_auth.py" not in text
