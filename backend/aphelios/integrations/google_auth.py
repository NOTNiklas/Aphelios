"""Gemeinsame Google-OAuth-Anmeldung für Gmail + Kalender.

Eine einzige Anmeldung (ein Token) deckt alle Scopes ab – Google erlaubt,
mehrere APIs mit demselben OAuth-Client und Consent-Vorgang freizuschalten.
Die eigentliche Anmeldung passiert **einmalig** über
``backend/scripts/google_auth.py`` (siehe ``docs/integrations.md``); dieses
Modul lädt danach nur noch die gespeicherten Zugangsdaten und erneuert sie
bei Bedarf automatisch.

**Seit Alpha 1.7 auch schreibende Scopes** (Mails senden, Termine anlegen –
beides über das SecurityGate bestätigungspflichtig, siehe
``docs/security.md``). ``gmail.send`` erlaubt AUSSCHLIESSLICH das Senden
neuer Mails, kein Lesen/Löschen/Ändern bestehender – bewusst der
engstmögliche Gmail-Schreib-Scope. ``calendar.events`` deckt Lesen UND
Schreiben von Terminen ab (ersetzt das bisherige ``calendar.readonly``).

**Wichtig für bereits angemeldete Nutzer:** Ein VOR Alpha 1.7 gespeichertes
Token kennt nur die alten (rein lesenden) Scopes – Google prüft angeforderte
Scopes beim Erstellen des Tokens, nicht bei jeder einzelnen Anfrage. Schreib-
Aktionen schlagen mit einem Berechtigungsfehler fehl, bis
``python scripts/google_auth.py`` erneut ausgeführt wird (neuer
Consent-Bildschirm mit den zusätzlichen Berechtigungen) – die Fehlermeldung
bei einem Schreib-Versuch weist explizit darauf hin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aphelios.core.config import Config

if TYPE_CHECKING:  # pragma: no cover – nur für Typprüfung, keine Laufzeit-Pflicht
    from google.oauth2.credentials import Credentials

#: Von APHELIOS angeforderte Google-Scopes.
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
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


def is_insufficient_scope_error(exc: Exception) -> bool:
    """Grobe Heuristik, ob ``exc`` Googles 403-Fehler für fehlende Scopes ist.

    Erkennt typische Fehlertext-Fragmente statt den exakten HTTP-Statuscode/
    die JSON-Fehlerstruktur zu parsen (robuster gegenüber leichten
    Abweichungen zwischen Client-Versionen) – gedacht für Mail-
    /Kalender-Schreibversuche mit einem VOR Alpha 1.7 erteilten, nur
    lesenden Token (siehe Modul-Docstring oben)."""
    text = str(exc).lower()
    return "insufficient" in text and ("scope" in text or "permission" in text)
