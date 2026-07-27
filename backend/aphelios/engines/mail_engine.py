"""MailEngine – liest ungelesene Gmail-Nachrichten (echte Integration, optional).

Anders als die ``WeatherEngine`` benötigt Gmail zwingend eine eigene
Google-OAuth-Anmeldung des Nutzers – Google erlaubt keinen Zugriff ohne
ausdrückliche Einwilligung. Einrichtung: ``docs/integrations.md``.

Ohne abgeschlossene Anmeldung (``config.has_google`` ist ``False``) bleibt die
Engine bewusst inaktiv – kein Fehler, kein Absturz, das HUD zeigt in diesem
Fall weiterhin die Mock-Mails.

Bus-Schnittstelle:
    * ``mail.update`` (out) – ``{emails: [{from, subject, snippet}], updated_at}``
      bei Erfolg, ``{error, updated_at}`` bei Fehler.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from aphelios.core.engine import BaseEngine
from aphelios.integrations.google_auth import load_credentials


class MailEngine(BaseEngine):
    """Ruft periodisch ungelesene Gmail-Nachrichten ab (nur lesend)."""

    name = "mail"

    async def start(self) -> None:
        self._running = True
        self._service: Any = None
        if not self.config.has_google:
            self.log.info(
                "Google nicht verbunden – MailEngine bleibt inaktiv. "
                "Einmalig ausführen: python scripts/google_auth.py "
                "(siehe docs/integrations.md)."
            )
            return
        try:
            self._service = await asyncio.to_thread(self._build_service)
            self.log.info("Gmail-Verbindung aktiv")
        except Exception:  # noqa: BLE001
            self.log.exception("Gmail-Verbindung fehlgeschlagen")
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
        return build("gmail", "v1", credentials=creds)

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._refresh()
            except Exception as exc:  # noqa: BLE001
                self.log.exception("Gmail-Abruf fehlgeschlagen")
                await self.emit(
                    "mail.update",
                    {"error": f"Gmail nicht erreichbar: {exc}"[:200], "updated_at": time.time()},
                )
            await asyncio.sleep(self.config.google_poll_interval)

    async def _refresh(self) -> None:
        # Synchrone Google-Client-Aufrufe im Thread ausführen, damit der
        # Event-Loop nicht blockiert.
        emails = await asyncio.to_thread(self._fetch_unread)
        await self.emit("mail.update", {"emails": emails, "updated_at": time.time()})

    def _fetch_unread(self, limit: int = 8) -> list[dict]:
        assert self._service is not None
        result = (
            self._service.users()
            .messages()
            .list(userId="me", labelIds=["INBOX", "UNREAD"], maxResults=limit)
            .execute()
        )
        emails: list[dict] = []
        for ref in result.get("messages", []):
            msg = (
                self._service.users()
                .messages()
                .get(
                    userId="me",
                    id=ref["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject"],
                )
                .execute()
            )
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            emails.append(
                {
                    "from": headers.get("From", "Unbekannt"),
                    "subject": headers.get("Subject", "(kein Betreff)"),
                    "snippet": msg.get("snippet", ""),
                }
            )
        return emails
