"""CalendarEngine – liest kommende Google-Kalender-Termine (echte Integration, optional).

Nutzt dieselbe Google-Anmeldung wie die ``MailEngine`` (ein Consent-Vorgang
deckt beide Scopes ab, siehe ``docs/integrations.md``). Ohne abgeschlossene
Anmeldung bleibt die Engine inaktiv und das HUD zeigt weiterhin Mock-Termine.

Termine **anlegen/ändern** (Schreibzugriff) ist eine spätere Ausbaustufe und
würde über das SecurityGate bestätigt werden müssen (siehe ``docs/security.md``)
– Alpha 1.0 liest bewusst nur.

Bus-Schnittstelle:
    * ``calendar.update`` (out) – ``{events: [{title, start, location}], updated_at}``
      bei Erfolg, ``{error, updated_at}`` bei Fehler.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from aphelios.core.engine import BaseEngine
from aphelios.integrations.google_auth import load_credentials


class CalendarEngine(BaseEngine):
    """Ruft periodisch die nächsten Google-Kalender-Termine ab (nur lesend)."""

    name = "calendar"

    async def start(self) -> None:
        self._running = True
        self._service: Any = None
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
        except Exception:  # noqa: BLE001
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
