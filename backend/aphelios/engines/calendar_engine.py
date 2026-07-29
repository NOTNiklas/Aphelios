"""CalendarEngine – liest kommende Google-Kalender-Termine, seit Alpha 1.7
auch Termine anlegen (echte Integration, optional).

Nutzt dieselbe Google-Anmeldung wie die ``MailEngine`` (ein Consent-Vorgang
deckt beide Scopes ab, siehe ``docs/integrations.md``). Ohne abgeschlossene
Anmeldung bleibt die Engine inaktiv und das HUD zeigt weiterhin Mock-Termine,
``/termin-anlegen`` meldet klar "nicht verbunden".

**Termine anlegen (``/termin-anlegen <Titel> | <Start> | <Dauer in Minuten>``,
Start als ``JJJJ-MM-TT HH:MM``):** läuft über das SecurityGate (CONFIRM) – ein
angelegter Termin ist für andere Kalender-Teilnehmer sichtbar und lässt sich
nicht rückstandslos zurücknehmen (Einladungen können schon verschickt sein).
Startzeit wird als **lokale Systemzeit** interpretiert (passend zum
Windows-Desktop, auf dem APHELIOS läuft).

**Für vor Alpha 1.7 bereits angemeldete Nutzer:** Das gespeicherte Google-
Token kennt evtl. noch nicht den ``calendar.events``-Scope – ``python
scripts/google_auth.py`` muss dann einmalig erneut ausgeführt werden (siehe
``aphelios/integrations/google_auth.py`` und ``docs/integrations.md``). Ein
entsprechender Fehlversuch beim Anlegen weist darauf explizit hin.

Bus-Schnittstelle:
    * ``calendar.update`` (out) – ``{events: [{title, start, location}], updated_at}``
      bei Erfolg, ``{error, updated_at}`` bei Fehler.
    * ``calendar.create.request`` (in) – ``{id, text}`` (``text`` =
      ``"<Titel> | <Start JJJJ-MM-TT HH:MM> | <Dauer in Minuten>"``)
      → ``chat.token`` / ``chat.response`` (out), wie bei der ``MailEngine``.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event
from aphelios.core.security import RiskLevel
from aphelios.integrations.google_auth import (
    is_insufficient_scope_error,
    is_invalid_scope_error,
    load_credentials,
)


def _parse_create_request(text: str) -> tuple[str, datetime, int] | None:
    """Trennt ``"<Titel> | <Start JJJJ-MM-TT HH:MM> | <Dauer in Minuten>"``.

    Pipe-getrennt statt Freitext-Datumserkennung ("morgen um 15 Uhr") – das
    bräuchte eine eigene Sprachverarbeitung mit vielen Sonderfällen
    (Zeitzonen, relative Angaben), für eine erste Ausbaustufe unverhältnismäßig.
    """
    parts = [p.strip() for p in text.split("|")]
    if len(parts) != 3 or not all(parts):
        return None
    title, start_str, duration_str = parts
    try:
        start = datetime.strptime(start_str, "%Y-%m-%d %H:%M").astimezone()
        duration = int(duration_str)
    except ValueError:
        return None
    if duration <= 0:
        return None
    return title, start, duration


class CalendarEngine(BaseEngine):
    """Ruft periodisch die nächsten Google-Kalender-Termine ab und kann neue anlegen."""

    name = "calendar"

    async def start(self) -> None:
        self._running = True
        self._service: Any = None
        self.bus.subscribe("calendar.create.request", self.handle_create)
        if not self.config.has_google:
            self.log.info(
                "Google nicht verbunden – CalendarEngine bleibt inaktiv. "
                "Einmalig ausführen: python scripts/google_auth.py "
                "(siehe docs/integrations.md)."
            )
            return
        try:
            self._service = await asyncio.to_thread(self._build_service)
            self.log.info("Kalender-Verbindung aktiv")
        except Exception as exc:  # noqa: BLE001
            if is_invalid_scope_error(exc):
                self.log.error(
                    "Google-Token wurde mit älteren, engeren Scopes erteilt als "
                    "aktuell benötigt – ein Refresh kann keine neuen Scopes "
                    "nachfordern. Einmalig erneut ausführen: python "
                    "scripts/google_auth.py (siehe docs/integrations.md)."
                )
            else:
                self.log.exception("Kalender-Verbindung fehlgeschlagen")
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        task = getattr(self, "_task", None)
        if task:
            task.cancel()

    def _build_service(self) -> Any:
        # Lazy-Import: google-api-python-client ist optional
        # (pip install -e ".[google]") – Standard-Installation bleibt schlank.
        from googleapiclient.discovery import build

        creds = load_credentials(self.config)
        return build("calendar", "v3", credentials=creds)

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._refresh()
            except Exception as exc:  # noqa: BLE001
                self.log.exception("Kalender-Abruf fehlgeschlagen")
                await self.emit(
                    "calendar.update",
                    {"error": f"Kalender nicht erreichbar: {exc}"[:200], "updated_at": time.time()},
                )
            await asyncio.sleep(self.config.google_poll_interval)

    async def _refresh(self) -> None:
        events = await asyncio.to_thread(self._fetch_upcoming)
        await self.emit("calendar.update", {"events": events, "updated_at": time.time()})

    def _fetch_upcoming(self, limit: int = 6) -> list[dict]:
        assert self._service is not None
        now_iso = datetime.now(timezone.utc).isoformat()
        result = (
            self._service.events()
            .list(
                calendarId="primary",
                timeMin=now_iso,
                maxResults=limit,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events: list[dict] = []
        for item in result.get("items", []):
            start = item.get("start", {})
            events.append(
                {
                    "title": item.get("summary", "(ohne Titel)"),
                    "start": start.get("dateTime") or start.get("date", ""),
                    "location": item.get("location", ""),
                }
            )
        return events

    # -- Termine anlegen (Alpha 1.7) --------------------------------------------
    async def handle_create(self, event: Event) -> None:
        text = (event.data.get("text") or "").strip()
        request_id = event.data.get("id", "")

        parsed = _parse_create_request(text)
        if parsed is None:
            await self._reply(
                request_id,
                'Bitte im Format "Titel | Start (JJJJ-MM-TT HH:MM) | Dauer in Minuten" '
                'angeben, z. B. "/termin-anlegen Team-Meeting | 2026-08-01 15:00 | 60".',
            )
            return
        title, start, duration = parsed

        if self._service is None:
            await self._reply(
                request_id,
                "Google nicht verbunden – einmalig ausführen: python scripts/google_auth.py "
                "(siehe docs/integrations.md).",
            )
            return

        if not await self._confirm_create(request_id, title, start):
            return

        try:
            await asyncio.to_thread(self._create, title, start, duration)
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Termin konnte nicht angelegt werden")
            hint = (
                " Vermutlich fehlt der Schreib-Scope – einmalig erneut ausführen: "
                "python scripts/google_auth.py (siehe docs/integrations.md)."
                if is_insufficient_scope_error(exc)
                else ""
            )
            await self._reply(request_id, f"Termin konnte nicht angelegt werden: {exc}"[:250] + hint)
            return

        await self._reply(
            request_id, f'Termin „{title}" angelegt: {start.strftime("%d.%m.%Y %H:%M")} ({duration} Min.)'
        )

    async def _confirm_create(self, request_id: str, title: str, start: datetime) -> bool:
        """Fragt vor JEDEM Anlegen das SecurityGate – ein Termin ist für
        andere Teilnehmer sichtbar und lässt sich nicht rückstandslos
        zurücknehmen (Einladungen können schon verschickt sein)."""
        allowed = await self.security.request(
            action="Termin anlegen",
            target=f'„{title}" am {start.strftime("%d.%m.%Y %H:%M")}',
            level=RiskLevel.CONFIRM,
            reason="Der Termin ist für andere Kalender-Teilnehmer sichtbar.",
        )
        if not allowed:
            await self._reply(request_id, "Abgelehnt.")
        return allowed

    def _create(self, title: str, start: datetime, duration_minutes: int) -> None:
        assert self._service is not None
        end = start + timedelta(minutes=duration_minutes)
        body = {
            "summary": title,
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
        }
        self._service.events().insert(calendarId="primary", body=body).execute()

    async def _reply(self, request_id: str, text: str) -> None:
        for word in text.split(" "):
            await self.emit("chat.token", {"id": request_id, "text": word + " "})
            await asyncio.sleep(0.02)
        await self.emit("chat.response", {"id": request_id, "text": text, "final": True})
