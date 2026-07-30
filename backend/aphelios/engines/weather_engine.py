"""WeatherEngine – echte Wetterdaten via Open-Meteo (kein API-Key nötig).

Die erste vollständig funktionierende externe App-Integration in APHELIOS:
ruft periodisch aktuelle Wetterdaten für eine konfigurierte Stadt ab und
publiziert sie als ``weather.update`` auf dem Bus. Nutzt die kostenlose
Open-Meteo API (https://open-meteo.com/) – kein Account, kein Key, keine
Kreditkarte nötig. Dient als Vorlage/Beweis für weitere App-Integrationen
(Gmail, WhatsApp, …), die – anders als Wetter – echte OAuth-Zugangsdaten vom
Nutzer benötigen (siehe ``docs/integrations.md``).

Bus-Schnittstelle:
    * ``weather.update`` (out) – ``{city, temperature, condition, humidity,
      wind_kmh, updated_at}`` bei Erfolg, ``{error, updated_at}`` bei Fehler.
"""

from __future__ import annotations

import asyncio
import time

import httpx

from aphelios.core.engine import BaseEngine

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

#: WMO Weather interpretation codes → deutsche Kurzbeschreibung.
#: https://open-meteo.com/en/docs (Abschnitt "WMO Weather interpretation codes")
WEATHER_CODES: dict[int, str] = {
    0: "Klarer Himmel",
    1: "Überwiegend klar",
    2: "Teilweise bewölkt",
    3: "Bedeckt",
    45: "Nebel",
    48: "Reifnebel",
    51: "Leichter Nieselregen",
    53: "Nieselregen",
    55: "Starker Nieselregen",
    61: "Leichter Regen",
    63: "Regen",
    65: "Starker Regen",
    71: "Leichter Schneefall",
    73: "Schneefall",
    75: "Starker Schneefall",
    77: "Schneegriesel",
    80: "Leichte Regenschauer",
    81: "Regenschauer",
    82: "Heftige Regenschauer",
    85: "Leichte Schneeschauer",
    86: "Schneeschauer",
    95: "Gewitter",
    96: "Gewitter mit Hagel",
    99: "Schweres Gewitter mit Hagel",
}


def describe_weather_code(code: int | None) -> str:
    """Übersetzt einen WMO-Wettercode in eine deutsche Kurzbeschreibung."""
    if code is None:
        return "Unbekannt"
    return WEATHER_CODES.get(code, "Unbekannt")


class WeatherEngine(BaseEngine):
    """Ruft periodisch echte Wetterdaten für eine konfigurierte Stadt ab."""

    name = "weather"

    async def start(self) -> None:
        self._running = True
        self._lat: float | None = None
        self._lon: float | None = None
        self._resolved_name = self.config.weather_city
        self._client = httpx.AsyncClient(timeout=10.0)
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
        # Sofort einen ersten Versuch, danach im konfigurierten Intervall.
        while self._running:
            try:
                await self._refresh()
            except Exception as exc:  # noqa: BLE001
                self.log.exception("Wetterabruf fehlgeschlagen")
                await self.emit(
                    "weather.update",
                    {
                        "error": f"Wetterdienst nicht erreichbar: {exc}"[:200],
                        "updated_at": time.time(),
                    },
                )
            await asyncio.sleep(self.config.weather_interval)

    async def _refresh(self) -> None:
        if not self.config.weather_city:
            return
        if self._lat is None or self._lon is None:
            await self._geocode()
        if self._lat is None:
            return  # Stadt nicht auflösbar – bereits geloggt in _geocode()

        resp = await self._client.get(
            _FORECAST_URL,
            params={
                "latitude": self._lat,
                "longitude": self._lon,
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "timezone": "auto",
            },
        )
        resp.raise_for_status()
        current = resp.json().get("current", {})
        code = current.get("weather_code")

        await self.emit(
            "weather.update",
            {
                "city": self._resolved_name,
                "temperature": current.get("temperature_2m"),
                "condition": describe_weather_code(int(code) if code is not None else None),
                "humidity": current.get("relative_humidity_2m"),
                "wind_kmh": current.get("wind_speed_10m"),
                "updated_at": time.time(),
            },
        )

    async def _geocode(self) -> None:
        """Löst den konfigurierten Stadtnamen einmalig zu Koordinaten auf."""
        resp = await self._client.get(
            _GEOCODE_URL,
            params={
                "name": self.config.weather_city,
                "count": 1,
                "language": "de",
                "format": "json",
            },
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if not results:
            self.log.warning(
                "Stadt %r nicht gefunden – Wetter bleibt deaktiviert. "
                "APHELIOS_WEATHER_CITY in der .env prüfen.",
                self.config.weather_city,
            )
            return
        hit = results[0]
        self._lat = hit["latitude"]
        self._lon = hit["longitude"]
        self._resolved_name = hit.get("name", self.config.weather_city)
        self.log.info(
            "Wetter-Standort aufgelöst: %s (%.2f, %.2f)",
            self._resolved_name,
            self._lat,
            self._lon,
        )
