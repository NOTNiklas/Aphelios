"""Spotify-OAuth-Anmeldung (Authorization-Code-Flow) für die MusicEngine.

Die eigentliche Anmeldung passiert **einmalig** über
``backend/scripts/spotify_auth.py`` (siehe ``docs/integrations.md``); dieses
Modul lädt danach nur noch die gespeicherten Zugangsdaten und erneuert das
Access-Token bei Bedarf automatisch über das Refresh-Token – analog zu
``aphelios/integrations/google_auth.py``, nur ohne die schwere
``google-auth``-Abhängigkeit: Spotifys OAuth ist ein einfacher REST-Aufruf,
den ``httpx`` (ohnehin Basis-Abhängigkeit) direkt kann.

Playback-Steuerung (Play/Pause/Skip/Lautstärke/Like) braucht zwingend eine
Nutzeranmeldung mit den unten gelisteten Scopes – anders als z. B. Wetter
gibt es keinen Weg ohne OAuth (Spotifys Client-Credentials-Flow liefert nur
Zugriff auf öffentliche Katalogdaten, keine Wiedergabesteuerung).
"""

from __future__ import annotations

import json
import time

import httpx

from aphelios.core.config import Config

#: Von APHELIOS angeforderte Spotify-Scopes.
SPOTIFY_SCOPES = [
    "user-read-currently-playing",
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-library-read",
    "user-library-modify",
]

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"

#: Muss Zeichen für Zeichen mit der im Spotify-Developer-Dashboard
#: hinterlegten Redirect-URI übereinstimmen (siehe docs/integrations.md).
#: Fester Port statt ``port=0`` wie beim Google-Flow, weil Spotify die
#: Redirect-URI vorab registriert verlangt und keine beliebigen Ports erlaubt.
SPOTIFY_REDIRECT_URI = "http://127.0.0.1:8898/callback"


class SpotifyAuthError(RuntimeError):
    """Spotify-Zugangsdaten fehlen, sind ungültig oder abgelaufen."""


async def load_access_token(config: Config, client: httpx.AsyncClient) -> str:
    """Lädt ein gültiges Access-Token, erneuert es bei Bedarf über das
    Refresh-Token und schreibt das Ergebnis zurück in die Token-Datei.

    Voraussetzung: ``backend/scripts/spotify_auth.py`` wurde bereits
    einmalig erfolgreich ausgeführt (siehe ``docs/integrations.md``).
    """
    if not config.spotify_token_path.exists():
        raise SpotifyAuthError(
            f"Keine Spotify-Anmeldung gefunden unter {config.spotify_token_path}. "
            "Einmalig ausführen: python scripts/spotify_auth.py"
        )

    data = json.loads(config.spotify_token_path.read_text(encoding="utf-8"))

    if time.time() < data.get("expires_at", 0) - 30:
        return data["access_token"]

    if not config.spotify_client_id or not config.spotify_client_secret:
        raise SpotifyAuthError(
            "SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET fehlen in der .env – "
            "können ein abgelaufenes Token nicht erneuern."
        )

    resp = await client.post(
        SPOTIFY_TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": data["refresh_token"]},
        auth=(config.spotify_client_id, config.spotify_client_secret),
    )
    if resp.status_code != 200:
        raise SpotifyAuthError(
            f"Spotify-Token-Erneuerung fehlgeschlagen ({resp.status_code}): {resp.text[:200]}. "
            "Vermutlich zurückgezogene Berechtigung – erneut ausführen: "
            "python scripts/spotify_auth.py"
        )
    refreshed = resp.json()

    data["access_token"] = refreshed["access_token"]
    data["expires_at"] = time.time() + refreshed.get("expires_in", 3600)
    # Spotify liefert nicht bei jeder Erneuerung ein neues Refresh-Token –
    # nur überschreiben, wenn tatsächlich eines dabei ist.
    if refreshed.get("refresh_token"):
        data["refresh_token"] = refreshed["refresh_token"]

    config.spotify_token_path.write_text(json.dumps(data), encoding="utf-8")
    return data["access_token"]


def is_no_active_device_error(status_code: int, body: str) -> bool:
    """Heuristik für Spotifys 404 "NO_ACTIVE_DEVICE" – tritt auf, wenn keine
    Spotify-App gerade offen/aktiv ist. Eigene Erkennung statt nur den
    rohen Statuscode zu zeigen, damit die MusicEngine eine verständliche
    Fehlermeldung ausgeben kann."""
    return status_code == 404 and "NO_ACTIVE_DEVICE" in body


def is_premium_required_error(status_code: int, body: str) -> bool:
    """Heuristik für Spotifys 403 "PREMIUM_REQUIRED" – Wiedergabesteuerung
    (Play/Pause/Skip/Lautstärke) ist Teil der Spotify-Web-API und
    erfordert einen Premium-Account; reines Auslesen des aktuellen Songs
    funktioniert auch mit einem Free-Account."""
    return status_code == 403 and "PREMIUM_REQUIRED" in body
