#!/usr/bin/env python3
"""Einmaliger OAuth-Login für Spotify (MusicEngine).

Voraussetzung: Eine App im Spotify-Developer-Dashboard
(https://developer.spotify.com/dashboard) mit der Redirect-URI
``http://127.0.0.1:8898/callback``. Die komplette Schritt-für-Schritt-
Anleitung steht in ``docs/integrations.md``.

Nutzung::

    cd backend
    # SPOTIFY_CLIENT_ID und SPOTIFY_CLIENT_SECRET in die .env eintragen, dann:
    python scripts/spotify_auth.py

Ein Browser-Fenster öffnet sich zur Spotify-Anmeldung. Nach der Bestätigung
liegt eine Token-Datei unter dem in ``APHELIOS_SPOTIFY_TOKEN_PATH``
konfigurierten Pfad (Standard: ``./data/spotify_token.json``) – die
MusicEngine nutzt sie ab dem nächsten Backend-Start automatisch.

Anders als beim Google-Flow (``google_auth.py``, nutzt die
``google-auth-oauthlib``-Bibliothek mit dynamischem Port) braucht Spotify
eine vorab im Dashboard registrierte, exakte Redirect-URI – deshalb ein
fester lokaler Port (8898) und ein selbstgebauter Mini-HTTP-Server aus der
Standardbibliothek statt einer zusätzlichen Abhängigkeit.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

# Erlaubt den Aufruf als `python scripts/spotify_auth.py` ohne vorheriges
# `pip install -e .` (z. B. direkt nach dem Klonen).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from aphelios.core.config import Config  # noqa: E402
from aphelios.integrations.spotify_auth import (  # noqa: E402
    SPOTIFY_AUTH_URL,
    SPOTIFY_REDIRECT_URI,
    SPOTIFY_SCOPES,
    SPOTIFY_TOKEN_URL,
)

_CALLBACK_HTML = (
    "<html><body style='font-family:sans-serif;background:#000;color:#0f8;"
    "text-align:center;padding-top:4rem'>"
    "<h2>APHELIOS ist mit Spotify verbunden.</h2>"
    "<p>Dieser Tab kann jetzt geschlossen werden.</p>"
    "</body></html>"
)


class _CallbackServer(HTTPServer):
    """Ein HTTPServer, der sich das empfangene ``code``-Query-Argument merkt."""

    auth_code: str | None = None
    auth_error: str | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    server: _CallbackServer  # type: ignore[assignment]

    def do_GET(self) -> None:  # noqa: N802 – von BaseHTTPRequestHandler vorgegeben
        query = parse_qs(urlparse(self.path).query)
        self.server.auth_code = query.get("code", [None])[0]
        self.server.auth_error = query.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(_CALLBACK_HTML.encode("utf-8"))

    def log_message(self, format: str, *args) -> None:  # noqa: A002 – Signatur vorgegeben
        pass  # Stille – kein Bedarf an Zugriffs-Logs für einen Einmal-Callback.


def _wait_for_code(port: int) -> tuple[str | None, str | None]:
    server = _CallbackServer(("127.0.0.1", port), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    thread.join(timeout=180)  # 3 Minuten, um sich bei Spotify anzumelden
    server.server_close()
    return server.auth_code, server.auth_error


def main() -> None:
    config = Config.from_env()

    if not config.spotify_client_id or not config.spotify_client_secret:
        print(
            "Fehlt: SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET in der .env.\n"
            "Siehe docs/integrations.md, Abschnitt 'Spotify einrichten'."
        )
        sys.exit(1)

    port = urlparse(SPOTIFY_REDIRECT_URI).port or 8898
    auth_url = f"{SPOTIFY_AUTH_URL}?" + urlencode(
        {
            "client_id": config.spotify_client_id,
            "response_type": "code",
            "redirect_uri": SPOTIFY_REDIRECT_URI,
            "scope": " ".join(SPOTIFY_SCOPES),
        }
    )
    print(f"Öffne den Browser zur Spotify-Anmeldung:\n{auth_url}\n")
    webbrowser.open(auth_url)

    code, error = _wait_for_code(port)
    if error:
        print(f"Spotify hat die Anmeldung abgelehnt: {error}")
        sys.exit(1)
    if not code:
        print("Zeitüberschreitung – keine Anmeldung innerhalb von 3 Minuten erhalten.")
        sys.exit(1)

    resp = httpx.post(
        SPOTIFY_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": SPOTIFY_REDIRECT_URI,
        },
        auth=(config.spotify_client_id, config.spotify_client_secret),
        timeout=10.0,
    )
    if resp.status_code != 200:
        print(f"Token-Austausch fehlgeschlagen ({resp.status_code}): {resp.text[:300]}")
        sys.exit(1)
    payload = resp.json()

    token_data = {
        "access_token": payload["access_token"],
        "refresh_token": payload["refresh_token"],
        "expires_at": time.time() + payload.get("expires_in", 3600),
    }
    config.spotify_token_path.parent.mkdir(parents=True, exist_ok=True)
    config.spotify_token_path.write_text(json.dumps(token_data), encoding="utf-8")
    print(f"✅ Spotify verbunden. Token gespeichert unter {config.spotify_token_path.resolve()}")
    print("Starte das Backend neu (python -m aphelios), damit das Musik-Panel aktiv wird.")


if __name__ == "__main__":
    main()
