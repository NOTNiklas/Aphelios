"""MusicEngine – Spotify-Wiedergabesteuerung (Play/Pause/Skip/Lautstärke/Like).

Anders als die ``WeatherEngine`` braucht Spotify zwingend eine eigene
OAuth-Anmeldung des Nutzers (Wiedergabesteuerung ist über Spotifys
Client-Credentials-Flow nicht möglich). Einrichtung: ``docs/integrations.md``.

Ohne abgeschlossene Anmeldung (``config.has_spotify`` ist ``False``) bleibt
die Engine bewusst inaktiv – kein Fehler, kein Absturz, das HUD zeigt in
diesem Fall eine Vorschau mit Beispieldaten (wie bei Kalender/Mails).

**Risikostufe:** Play/Pause/Skip/Lautstärke/Like laufen bewusst über
``RiskLevel.SAFE`` (sofort erlaubt, kein Bestätigungsdialog) – anders als
z. B. das Löschen einer Datei oder das Senden einer Mail sind das trivial
reversible Aktionen ohne Konsequenz für Dritte, dasselbe Risikoniveau wie
„Stats lesen" in ``docs/security.md``.

Bus-Schnittstelle:
    * ``music.update`` (out) – ``{connected, is_playing, track, artist,
      album, album_art, duration_ms, progress_ms, volume, liked,
      updated_at}`` bei Erfolg, ``{error, updated_at}`` bei Fehler.
    * ``music.play.request`` / ``music.pause.request`` /
      ``music.next.request`` / ``music.previous.request`` (in) – kein Feld.
    * ``music.volume.request`` (in) – ``{level}`` (0–100).
    * ``music.like.request`` (in) – ``{liked}`` (bool) für den aktuell
      laufenden Song.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event
from aphelios.integrations.spotify_auth import (
    SpotifyAuthError,
    is_no_active_device_error,
    is_premium_required_error,
    load_access_token,
)

_API_BASE = "https://api.spotify.com/v1"

#: Nach einer Steuerungsaktion (Play/Skip/…) kurz warten, bevor der neue
#: Zustand abgefragt wird – Spotify braucht einen Moment, um den
#: Wiedergabestatus intern zu aktualisieren; ohne Wartezeit käme oft noch
#: der alte Song/Zustand zurück, was im HUD wie ein nicht reagierender
#: Button wirkt.
_POST_ACTION_DELAY = 0.4


class MusicEngine(BaseEngine):
    """Ruft periodisch den aktuell gespielten Spotify-Song ab und steuert
    die Wiedergabe (Play/Pause/Skip/Lautstärke/Like)."""

    name = "music"

    async def start(self) -> None:
        self._running = True
        self._client = httpx.AsyncClient(timeout=10.0)
        self.bus.subscribe("music.play.request", self._handle_play)
        self.bus.subscribe("music.pause.request", self._handle_pause)
        self.bus.subscribe("music.next.request", self._handle_next)
        self.bus.subscribe("music.previous.request", self._handle_previous)
        self.bus.subscribe("music.volume.request", self._handle_volume)
        self.bus.subscribe("music.like.request", self._handle_like)

        if not self.config.has_spotify:
            self.log.info(
                "Spotify nicht verbunden – MusicEngine bleibt inaktiv. "
                "Einmalig ausführen: python scripts/spotify_auth.py "
                "(siehe docs/integrations.md)."
            )
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        task = getattr(self, "_task", None)
        if task:
            task.cancel()
        client = getattr(self, "_client", None)
        if client:
            await client.aclose()

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._refresh()
            except Exception as exc:  # noqa: BLE001
                self.log.exception("Spotify-Abruf fehlgeschlagen")
                await self.emit(
                    "music.update",
                    {"error": f"Spotify nicht erreichbar: {exc}"[:200], "updated_at": time.time()},
                )
            await asyncio.sleep(self.config.spotify_poll_interval)

    # -- Zustand abrufen --------------------------------------------------------
    async def _auth_headers(self) -> dict[str, str]:
        token = await load_access_token(self.config, self._client)
        return {"Authorization": f"Bearer {token}"}

    async def _refresh(self) -> None:
        try:
            headers = await self._auth_headers()
        except SpotifyAuthError as exc:
            await self.emit("music.update", {"error": str(exc)[:200], "updated_at": time.time()})
            return

        resp = await self._client.get(f"{_API_BASE}/me/player", headers=headers)

        if resp.status_code == 204 or not resp.content:
            await self.emit(
                "music.update",
                {"connected": True, "is_playing": False, "track": None, "updated_at": time.time()},
            )
            return

        if resp.status_code == 401:
            await self.emit(
                "music.update",
                {
                    "error": "Spotify-Anmeldung abgelaufen – erneut ausführen: "
                    "python scripts/spotify_auth.py",
                    "updated_at": time.time(),
                },
            )
            return

        if resp.status_code != 200:
            await self.emit(
                "music.update",
                {"error": f"Spotify-Fehler ({resp.status_code}): {resp.text[:150]}", "updated_at": time.time()},
            )
            return

        payload = resp.json()
        await self.emit("music.update", await self._build_update(payload, headers))

    async def _build_update(self, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        item = payload.get("item") or {}
        images = (item.get("album") or {}).get("images") or []
        device = payload.get("device") or {}
        track_id = item.get("id")

        liked: bool | None = None
        if track_id:
            liked = await self._is_liked(track_id, headers)

        return {
            "connected": True,
            "is_playing": bool(payload.get("is_playing")),
            "track": item.get("name"),
            "artist": ", ".join(a.get("name", "") for a in item.get("artists", [])) or None,
            "album": (item.get("album") or {}).get("name"),
            # Erstes Bild ist bei Spotify konventionell das größte.
            "album_art": images[0]["url"] if images else None,
            "duration_ms": item.get("duration_ms"),
            "progress_ms": payload.get("progress_ms"),
            "volume": device.get("volume_percent"),
            "liked": liked,
            "updated_at": time.time(),
        }

    async def _is_liked(self, track_id: str, headers: dict[str, str]) -> bool | None:
        resp = await self._client.get(
            f"{_API_BASE}/me/tracks/contains", params={"ids": track_id}, headers=headers
        )
        if resp.status_code != 200:
            return None
        result = resp.json()
        return bool(result[0]) if result else None

    # -- Steuerung ----------------------------------------------------------------
    async def _control(self, method: str, path: str, **kwargs: Any) -> None:
        """Führt einen Steuerungsaufruf aus und aktualisiert danach den Zustand."""
        try:
            headers = await self._auth_headers()
        except SpotifyAuthError as exc:
            await self.emit("music.update", {"error": str(exc)[:200], "updated_at": time.time()})
            return

        resp = await self._client.request(method, f"{_API_BASE}{path}", headers=headers, **kwargs)

        if resp.status_code not in (200, 202, 204):
            body = resp.text
            if is_no_active_device_error(resp.status_code, body):
                message = "Kein aktives Gerät – öffne Spotify auf einem Gerät und starte einen Song."
            elif is_premium_required_error(resp.status_code, body):
                message = "Wiedergabesteuerung erfordert Spotify Premium."
            else:
                message = f"Spotify-Steuerung fehlgeschlagen ({resp.status_code}): {body[:150]}"
            await self.emit("music.update", {"error": message, "updated_at": time.time()})
            return

        await asyncio.sleep(_POST_ACTION_DELAY)
        await self._refresh()

    async def _handle_play(self, event: Event) -> None:
        await self._control("PUT", "/me/player/play")

    async def _handle_pause(self, event: Event) -> None:
        await self._control("PUT", "/me/player/pause")

    async def _handle_next(self, event: Event) -> None:
        await self._control("POST", "/me/player/next")

    async def _handle_previous(self, event: Event) -> None:
        await self._control("POST", "/me/player/previous")

    async def _handle_volume(self, event: Event) -> None:
        level = event.data.get("level")
        if not isinstance(level, (int, float)):
            return
        level = max(0, min(100, int(level)))
        await self._control("PUT", "/me/player/volume", params={"volume_percent": level})

    async def _handle_like(self, event: Event) -> None:
        try:
            headers = await self._auth_headers()
        except SpotifyAuthError as exc:
            await self.emit("music.update", {"error": str(exc)[:200], "updated_at": time.time()})
            return

        # Braucht die Track-ID des aktuellen Songs – ein direkter Zustandsabruf
        # statt eines gecachten Werts, da sich der Song zwischenzeitlich
        # geändert haben könnte.
        resp = await self._client.get(f"{_API_BASE}/me/player/currently-playing", headers=headers)
        track_id = (resp.json().get("item") or {}).get("id") if resp.status_code == 200 and resp.content else None
        if not track_id:
            return

        liked = bool(event.data.get("liked"))
        method = "PUT" if liked else "DELETE"
        await self._control(method, "/me/tracks", params={"ids": track_id})
