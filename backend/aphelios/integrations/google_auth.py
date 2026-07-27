"""Gemeinsame Google-OAuth-Anmeldung für Gmail + Kalender.

Eine einzige Anmeldung (ein Token) deckt beide Scopes ab – Google erlaubt,
mehrere APIs mit demselben OAuth-Client und Consent-Vorgang freizuschalten.
Die eigentliche Anmeldung passiert **einmalig** über
``backend/scripts/google_auth.py`` (siehe ``docs/integrations.md``); dieses
Modul lädt danach nur noch die gespeicherten Zugangsdaten und erneuert sie
bei Bedarf automatisch.

Bewusst nur **lesende** Scopes (``.readonly``) – schreibender Zugriff (Termine
anlegen, Mails senden) ist eine spätere Ausbaustufe und würde über das
SecurityGate bestätigt werden müssen (siehe ``docs/security.md``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aphelios.core.config import Config

if TYPE_CHECKING:  # pragma: no cover – nur für Typprüfung, keine Laufzeit-Pflicht
    from google.oauth2.credentials import Credentials

#: Von APHELIOS angeforderte Google-Scopes (rein lesend).
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]


class GoogleAuthError(RuntimeError):
    """Google-Zugangsdaten fehlen, sind ungültig oder abgelaufen."""


def load_credentials(config: Config) -> "Credentials":
    """Lädt die gespeicherten Google-Zugangsdaten und erneuert sie bei Bedarf.

    Setzt voraus, dass ``backend/scripts/google_auth.py`` bereits einmalig
    erfolgreich ausgeführt wurde (siehe ``docs/integrations.md``).
    """
    if not config.google_token_path.exists():
        raise GoogleAuthError(
            f"Keine Google-Anmeldung gefunden unter {config.google_token_path}. "
            "Einmalig ausführen: python scripts/google_auth.py"
        )

    # Lazy-Import: google-auth-* sind optionale Abhängigkeiten
    # (pip install -e ".[google]") – die Standard-Installation bleibt schlank.
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_file(str(config.google_token_path), GOOGLE_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        config.google_token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds
