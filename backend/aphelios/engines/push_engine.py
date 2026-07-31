"""PushEngine – Web-Push-Benachrichtigungen (VAPID) ans Handy/den Browser.

Andere Engines lösen darüber proaktive Benachrichtigungen aus (Morgen-
Briefing, künftig z. B. Bildschirm-Warnungen), OHNE dass APHELIOS offen sein
muss – Web Push liefert der Browser-eigene Push-Dienst (FCM/Mozilla Autopush)
zu, auch bei geschlossenem Tab.

**Kein eigener Account nötig:** Ein VAPID-Schlüsselpaar wird beim ersten
Start automatisch lokal erzeugt (``py_vapid``, Teil von ``pywebpush``) und in
``APHELIOS_VAPID_PRIVATE_KEY_PATH`` gespeichert – analog zum Piper-Modell:
optional, ohne installiertes ``pywebpush`` (``pip install -e ".[push]"``)
bleibt die Engine inaktiv (loggt einmalig einen Hinweis), kein Absturz.

**Sicherer Kontext nötig:** Browser erlauben ``pushManager.subscribe`` nur
über HTTPS oder ``http://localhost`` – ein Zugriff übers LAN (``http://<IP>:
5173``) kann sich NICHT anmelden. Für Zustellung aufs Handy muss das Frontend
also über HTTPS erreichbar sein (siehe docs/integrations.md).

Bus-Schnittstelle:
    * ``push.subscribe`` (in) – ``{endpoint, keys: {p256dh, auth}}`` – neues
      Browser-Abo speichern (Upsert per ``endpoint``).
    * ``push.unsubscribe`` (in) – ``{endpoint}`` – Abo entfernen.
    * ``push.notify`` (in) – ``{title, body, url?}`` – schickt an ALLE
      gespeicherten Abos; abgelaufene/widerrufene (HTTP 404/410 der
      Zustellung) werden automatisch bereinigt statt bei jedem weiteren
      Versuch erneut zu scheitern.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event


class PushEngine(BaseEngine):
    """Verwaltet Web-Push-Abos und stellt Benachrichtigungen darüber zu."""

    name = "push"

    async def start(self) -> None:
        self._running = True
        self._available = False
        self._vapid_path = ""
        self.public_key = ""

        try:
            from cryptography.hazmat.primitives import serialization
            from py_vapid import Vapid
            from py_vapid.utils import b64urlencode

            self.config.vapid_private_key_path.parent.mkdir(parents=True, exist_ok=True)
            self._vapid_path = str(self.config.vapid_private_key_path)
            # Vapid.from_file erzeugt+speichert automatisch ein neues
            # Schlüsselpaar, falls die Datei noch nicht existiert.
            vapid = Vapid.from_file(self._vapid_path)
            raw_public = vapid.public_key.public_bytes(
                serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
            )
            self.public_key = b64urlencode(raw_public)
            self._available = True
            self.log.info("Push-Benachrichtigungen aktiv (VAPID-Schlüssel bereit)")
        except Exception:  # noqa: BLE001
            self.log.info(
                "pywebpush nicht installiert – Push-Benachrichtigungen bleiben inaktiv. "
                'Einmalig ausführen: pip install -e ".[push]" (siehe docs/integrations.md).'
            )

        self.config.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.config.db_path)
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                endpoint TEXT PRIMARY KEY,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        self._db.commit()

        self.bus.subscribe("push.subscribe", self._on_subscribe)
        self.bus.subscribe("push.unsubscribe", self._on_unsubscribe)
        self.bus.subscribe("push.notify", self._on_notify)

    async def stop(self) -> None:
        self._running = False
        db = getattr(self, "_db", None)
        if db:
            db.close()

    async def _on_subscribe(self, event: Event) -> None:
        endpoint = (event.data.get("endpoint") or "").strip()
        keys = event.data.get("keys") or {}
        p256dh = (keys.get("p256dh") or "").strip()
        auth = (keys.get("auth") or "").strip()
        if not endpoint or not p256dh or not auth:
            return
        self._db.execute(
            "INSERT INTO push_subscriptions (endpoint, p256dh, auth, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(endpoint) DO UPDATE SET p256dh = excluded.p256dh, auth = excluded.auth",
            (endpoint, p256dh, auth, time.time()),
        )
        self._db.commit()
        self.log.info("Push-Abo registriert (%d aktiv)", self._count())

    async def _on_unsubscribe(self, event: Event) -> None:
        endpoint = (event.data.get("endpoint") or "").strip()
        if not endpoint:
            return
        self._db.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
        self._db.commit()

    def _count(self) -> int:
        row = self._db.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()
        return row[0] if row else 0

    async def _on_notify(self, event: Event) -> None:
        """Schickt an ALLE gespeicherten Abos – der Aufruf ('title'/'body')
        ist absichtlich generisch, damit beliebige Engines (Morgen-Briefing,
        künftig weitere) proaktive Handy-Benachrichtigungen auslösen können,
        ohne die PushEngine zu kennen."""
        if not self._available:
            self.log.info("push.notify ignoriert – pywebpush nicht verfügbar.")
            return
        title = (event.data.get("title") or "APHELIOS").strip()
        body = (event.data.get("body") or "").strip()
        if not body:
            return
        url = event.data.get("url") or "/"
        payload = json.dumps({"title": title, "body": body, "url": url})

        rows = self._db.execute("SELECT endpoint, p256dh, auth FROM push_subscriptions").fetchall()
        for endpoint, p256dh, auth in rows:
            # webpush() ist synchron (nutzt requests) -> in einem Thread-Pool-
            # Worker ausführen, damit der Event-Loop nicht blockiert. DB-
            # Zugriffe bleiben bewusst HIER im Event-Loop-Thread: sqlite3-
            # Connections sind nicht thread-übergreifend nutzbar, _send_one
            # gibt daher nur den Ausgang zurück statt selbst zu löschen.
            outcome = await asyncio.to_thread(self._send_one, endpoint, p256dh, auth, payload)
            if outcome == "expired":
                self._db.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
                self._db.commit()

    def _send_one(self, endpoint: str, p256dh: str, auth: str, payload: str) -> str:
        from pywebpush import WebPushException, webpush

        try:
            webpush(
                subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
                data=payload,
                vapid_private_key=self._vapid_path,
                vapid_claims={"sub": self.config.vapid_subject},
            )
            return "ok"
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                return "expired"
            self.log.warning("Push-Zustellung fehlgeschlagen: %s", exc)
            return "error"
