#!/usr/bin/env python3
"""Einmaliger OAuth-Login für Gmail + Google Kalender.

Voraussetzung: Ein Google-Cloud-Projekt mit aktivierter Gmail- und
Calendar-API sowie einem OAuth-Client vom Typ "Desktop-App". Die komplette
Schritt-für-Schritt-Anleitung steht in ``docs/integrations.md``.

Nutzung::

    cd backend
    pip install -e ".[google]"
    # GOOGLE_CLIENT_ID und GOOGLE_CLIENT_SECRET in die .env eintragen, dann:
    python scripts/google_auth.py

Ein Browser-Fenster öffnet sich zur Google-Anmeldung. Nach der Bestätigung
liegt eine Token-Datei unter dem in ``APHELIOS_GOOGLE_TOKEN_PATH``
konfigurierten Pfad (Standard: ``./data/google_token.json``) – MailEngine und
CalendarEngine nutzen sie ab dem nächsten Backend-Start automatisch.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Erlaubt den Aufruf als `python scripts/google_auth.py` ohne vorheriges
# `pip install -e .` (z. B. direkt nach dem Klonen).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aphelios.core.config import Config  # noqa: E402
from aphelios.integrations.google_auth import GOOGLE_SCOPES  # noqa: E402


def main() -> None:
    config = Config.from_env()

    if not config.google_client_id or not config.google_client_secret:
        print(
            "Fehlt: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET in der .env.\n"
            "Siehe docs/integrations.md, Abschnitt 'Gmail & Kalender einrichten'."
        )
        sys.exit(1)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print('Fehlt: pip install -e ".[google]"  (optionale Google-Abhängigkeiten).')
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": config.google_client_id,
            "client_secret": config.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, GOOGLE_SCOPES)
    creds = flow.run_local_server(port=0)

    config.google_token_path.parent.mkdir(parents=True, exist_ok=True)
    config.google_token_path.write_text(creds.to_json(), encoding="utf-8")
    print(f"✅ Google verbunden. Token gespeichert unter {config.google_token_path.resolve()}")
    print("Starte das Backend neu (python -m aphelios), damit Mail/Kalender aktiv werden.")


if __name__ == "__main__":
    main()
