"""MailEngine – liest ungelesene Gmail-Nachrichten, seit Alpha 1.7 auch
Mails senden (echte Integration, optional).

Anders als die ``WeatherEngine`` benötigt Gmail zwingend eine eigene
Google-OAuth-Anmeldung des Nutzers – Google erlaubt keinen Zugriff ohne
ausdrückliche Einwilligung. Einrichtung: ``docs/integrations.md``.

Ohne abgeschlossene Anmeldung (``config.has_google`` ist ``False``) bleibt die
Engine bewusst inaktiv – kein Fehler, kein Absturz, das HUD zeigt in diesem
Fall weiterhin die Mock-Mails, ``/mail-senden`` meldet klar "nicht verbunden".

**Mails senden (``/mail-senden <An> | <Betreff> | <Text>``):** läuft über das
SecurityGate (CONFIRM) – eine einmal gesendete Mail lässt sich nicht
zurückholen, anders als z. B. eine lokale Datei, die zumindest theoretisch
wiederherstellbar wäre. Bewusst KEIN automatisches Verfassen durch Claude in
dieser ersten Ausbaustufe – der Nutzer gibt An/Betreff/Text explizit an,
APHELIOS erfindet keinen Mailinhalt selbstständig.

**Für vor Alpha 1.7 bereits angemeldete Nutzer:** Das gespeicherte Google-
Token kennt evtl. noch nicht den ``gmail.send``-Scope – ``python
scripts/google_auth.py`` muss dann einmalig erneut ausgeführt werden (siehe
``aphelios/integrations/google_auth.py`` und ``docs/integrations.md``). Ein
entsprechender Fehlversuch beim Senden weist darauf explizit hin.

Bus-Schnittstelle:
    * ``mail.update`` (out) – ``{emails: [{from, subject, snippet}], updated_at}``
      bei Erfolg, ``{error, updated_at}`` bei Fehler.
    * ``mail.send.request`` (in) – ``{id, text}`` (``text`` =
      ``"<An> | <Betreff> | <Text>"``)
      → ``chat.token`` / ``chat.response`` (out), wie bei der ``BrowserEngine``.
"""

from __future__ import annotations

import asyncio
import base64
import time
from email.mime.text import MIMEText
from typing import Any

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event
from aphelios.core.security import RiskLevel
from aphelios.integrations.google_auth import (
    is_insufficient_scope_error,
    is_invalid_scope_error,
    load_credentials,
)


def _parse_send_request(text: str) -> tuple[str, str, str] | None:
    """Trennt ``"<An> | <Betreff> | <Text>"`` in seine drei Felder.

    Pipe-getrennt statt einer Freitext-Heuristik (wie bei URLs/Dateipfaden
    in Browser-/OfficeEngine) – eine E-Mail hat drei gleichwertig wichtige,
    beliebig lange Freitextfelder, für die es keinen zuverlässigen
    natürlichsprachlichen Trenner gibt.
    """
    parts = [p.strip() for p in text.split("|")]
    if len(parts) != 3 or not all(parts):
        return None
    to, subject, body = parts
    return to, subject, body


class MailEngine(BaseEngine):
    """Ruft periodisch ungelesene Gmail-Nachrichten ab und kann Mails senden."""

    name = "mail"

    async def start(self) -> None:
        self._running = True
        self._service: Any = None
        self.bus.subscribe("mail.send.request", self.handle_send)
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
        except Exception as exc:  # noqa: BLE001
            if is_invalid_scope_error(exc):
                self.log.error(
                    "Google-Token wurde mit älteren, engeren Scopes erteilt als "
                    "aktuell benötigt – ein Refresh kann keine neuen Scopes "
                    "nachfordern. Einmalig erneut ausführen: python "
                    "scripts/google_auth.py (siehe docs/integrations.md)."
                )
            else:
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

    # -- Mails senden (Alpha 1.7) ----------------------------------------------
    async def handle_send(self, event: Event) -> None:
        text = (event.data.get("text") or "").strip()
        request_id = event.data.get("id", "")

        parsed = _parse_send_request(text)
        if parsed is None:
            await self._reply(
                request_id,
                'Bitte im Format "An | Betreff | Text" angeben, z. B. '
                '"/mail-senden max@example.com | Update | Das Projekt ist fertig."',
            )
            return
        to, subject, body = parsed

        if self._service is None:
            await self._reply(
                request_id,
                "Google nicht verbunden – einmalig ausführen: python scripts/google_auth.py "
                "(siehe docs/integrations.md).",
            )
            return

        if not await self._confirm_send(request_id, to, subject):
            return

        try:
            await asyncio.to_thread(self._send, to, subject, body)
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Mail konnte nicht gesendet werden")
            hint = (
                " Vermutlich fehlt der Schreib-Scope – einmalig erneut ausführen: "
                "python scripts/google_auth.py (siehe docs/integrations.md)."
                if is_insufficient_scope_error(exc)
                else ""
            )
            await self._reply(request_id, f"Mail konnte nicht gesendet werden: {exc}"[:250] + hint)
            return

        await self._reply(request_id, f"Mail an {to} gesendet: „{subject}\"")

    async def _confirm_send(self, request_id: str, to: str, subject: str) -> bool:
        """Fragt vor JEDEM Sendevorgang das SecurityGate – eine gesendete
        Mail lässt sich nicht zurückholen."""
        allowed = await self.security.request(
            action="Mail senden",
            target=f"{to} – „{subject}\"",
            level=RiskLevel.CONFIRM,
            reason="Eine gesendete Mail lässt sich nicht zurückholen.",
        )
        if not allowed:
            await self._reply(request_id, "Abgelehnt.")
        return allowed

    def _send(self, to: str, subject: str, body: str) -> None:
        assert self._service is not None
        message = MIMEText(body)
        message["To"] = to
        message["Subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        self._service.users().messages().send(userId="me", body={"raw": raw}).execute()

    async def _reply(self, request_id: str, text: str) -> None:
        for word in text.split(" "):
            await self.emit("chat.token", {"id": request_id, "text": word + " "})
            await asyncio.sleep(0.02)
        await self.emit("chat.response", {"id": request_id, "text": text, "final": True})
