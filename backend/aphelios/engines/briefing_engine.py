"""BriefingEngine – tägliches Morgen-Briefing aus Wetter/Kalender/Mail/Aktien.

Fasst die Daten zusammen, die andere Engines ohnehin periodisch abrufen
(WeatherEngine, CalendarEngine, MailEngine, StockEngine) – die BriefingEngine
ruft dafür NICHTS aktiv ab, sondern hört nur auf deren ``*.update``-Events und
hält jeweils den letzten Stand im Speicher (dieselbe Idee wie
``ConnectionManager.REPLAYABLE_TOPICS`` im API-Server).

**Läuft nur einmal pro Kalendertag** – das zuletzt ausgeführte Datum wird
über den generischen ``memory.kv``-Speicher der MemoryEngine persistiert
(überlebt einen Neustart). Ohne das würde jeder Backend-Neustart nach der
konfigurierten Uhrzeit ein erneutes Briefing auslösen – genau der Fehler, der
die frühere ResearchEngine-Scheduled-Research bei jedem Neustart erneut
Aktien analysieren ließ (deshalb ganz entfernt, siehe research_engine.py).

Zwei Nutzungswege:
    * **Automatisch** – alle 2 Minuten wird geprüft, ob die konfigurierte
      Uhrzeit (``APHELIOS_BRIEFING_TIME``) erreicht UND heute noch kein
      Briefing gelaufen ist.
    * **Auf Zuruf** – ``/briefing`` liefert sofort ein Briefing, unabhängig
      vom Tagesstatus (zum Testen oder wenn man es spontan hören will).

Bus-Schnittstelle:
    * ``briefing.request`` (in) – ``{id}`` → ``chat.token``/``chat.response``
      (out), wie bei anderen Engines. Löst zusätzlich ``push.notify`` aus.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event, request

_CHECK_INTERVAL = 120.0
_LAST_RUN_KEY = "briefing.last_run_date"

_SYSTEM_PROMPT = (
    "Du bist APHELIOS, ein persönlicher KI-Assistent. Formuliere aus den "
    "folgenden Rohdaten ein kurzes, natürliches Morgen-Briefing auf Deutsch "
    "(3-5 Sätze, sprechbar, kein Aufzählungsformat, keine Emojis). Nenne bei "
    "Aktienkursen nur die Zahlen, keine Anlageberatung/Kaufempfehlung."
)


class BriefingEngine(BaseEngine):
    """Baut ein tägliches Morgen-Briefing aus zwischengespeicherten Engine-Daten."""

    name = "briefing"

    async def start(self) -> None:
        self._running = True
        self._client = None
        if self.config.has_anthropic:
            try:
                import anthropic

                self._client = anthropic.AsyncAnthropic(api_key=self.config.anthropic_api_key)
            except Exception:  # noqa: BLE001
                self._client = None

        self._weather: dict | None = None
        self._calendar: dict | None = None
        self._mail: dict | None = None
        self._stock: dict | None = None

        self.bus.subscribe("weather.update", self._cache_weather)
        self.bus.subscribe("calendar.update", self._cache_calendar)
        self.bus.subscribe("mail.update", self._cache_mail)
        self.bus.subscribe("stock.update", self._cache_stock)
        self.bus.subscribe("briefing.request", self._on_manual_request)

        self._task = None
        if self.config.briefing_enabled:
            self._task = asyncio.create_task(self._loop())
        else:
            self.log.info("Morgen-Briefing per Konfiguration deaktiviert (APHELIOS_BRIEFING_ENABLED=false).")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    # -- Zwischenspeicher (siehe Docstring) ------------------------------------
    async def _cache_weather(self, event: Event) -> None:
        self._weather = event.data

    async def _cache_calendar(self, event: Event) -> None:
        self._calendar = event.data

    async def _cache_mail(self, event: Event) -> None:
        self._mail = event.data

    async def _cache_stock(self, event: Event) -> None:
        self._stock = event.data

    # -- Automatischer Lauf -----------------------------------------------------
    async def _loop(self) -> None:
        while self._running:
            await asyncio.sleep(_CHECK_INTERVAL)
            try:
                await self._maybe_run()
            except Exception:  # noqa: BLE001
                self.log.exception("Morgen-Briefing-Prüfung fehlgeschlagen")

    async def _maybe_run(self) -> None:
        now = datetime.now()
        if now.strftime("%H:%M") < self.config.briefing_time:
            return
        today = now.strftime("%Y-%m-%d")
        last = await self._get_last_run_date()
        if last == today:
            return
        await self._set_last_run_date(today)
        text = await self._compose()
        await self._speak(text)
        await self.emit("push.notify", {"title": "Morgen-Briefing", "body": text[:180], "url": "/"})

    async def _get_last_run_date(self) -> str | None:
        result = await request(self.bus, "memory.kv.get", "memory.kv.result", {"key": _LAST_RUN_KEY}, timeout=5.0)
        return (result or {}).get("value")

    async def _set_last_run_date(self, date_str: str) -> None:
        await self.emit("memory.kv.set", {"key": _LAST_RUN_KEY, "value": date_str})

    # -- Auf Zuruf ("/briefing") -----------------------------------------------
    async def _on_manual_request(self, event: Event) -> None:
        request_id = event.data.get("id", "")
        text = await self._compose()
        await self._reply(request_id, text)
        await self.emit("push.notify", {"title": "Morgen-Briefing", "body": text[:180], "url": "/"})

    # -- Zusammenfassung bauen ---------------------------------------------------
    async def _compose(self) -> str:
        weather_line = ""
        if self._weather and not self._weather.get("error"):
            weather_line = (
                f"{self._weather.get('temperature')}°C, {self._weather.get('condition')} "
                f"in {self._weather.get('city')}"
            )
        today_str = datetime.now().strftime("%Y-%m-%d")
        events = [
            e for e in ((self._calendar or {}).get("events") or []) if str(e.get("start", "")).startswith(today_str)
        ]
        mail_count = len((self._mail or {}).get("emails") or [])
        quotes = (self._stock or {}).get("quotes") or []

        if self._client is not None:
            try:
                return await self._compose_with_claude(weather_line, events, mail_count, quotes)
            except Exception:  # noqa: BLE001
                self.log.exception("Claude-Briefing fehlgeschlagen, Fallback auf Vorlage")
        return self._compose_template(weather_line, events, mail_count, quotes)

    async def _compose_with_claude(
        self, weather_line: str, events: list[dict], mail_count: int, quotes: list[dict]
    ) -> str:
        assert self._client is not None
        lines = [f"Wetter: {weather_line}" if weather_line else "Wetter: keine Daten"]
        if events:
            titles = "; ".join(f"{e.get('title')} um {e.get('start')}" for e in events[:5])
            lines.append(f"Heutige Termine: {titles}")
        else:
            lines.append("Heute keine Termine.")
        lines.append(f"Ungelesene Mails: {mail_count}")
        if quotes:
            movers = ", ".join(f"{q.get('symbol')} {q.get('change_percent', 0):+.1f}%" for q in quotes[:5])
            lines.append(f"Watchlist: {movers}")
        resp = await self._client.messages.create(
            model=self.config.anthropic_model,
            max_tokens=250,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": "\n".join(lines)}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()

    def _compose_template(
        self, weather_line: str, events: list[dict], mail_count: int, quotes: list[dict]
    ) -> str:
        parts = ["Guten Morgen!"]
        if weather_line:
            parts.append(f"Wetter: {weather_line}.")
        if events:
            titles = "; ".join(e.get("title", "") for e in events[:5])
            parts.append(f"Heute {len(events)} Termin(e): {titles}.")
        else:
            parts.append("Heute keine Termine im Kalender.")
        if mail_count:
            parts.append(f"{mail_count} ungelesene Mail(s).")
        if quotes:
            movers = ", ".join(f"{q.get('symbol')} {q.get('change_percent', 0):+.1f}%" for q in quotes[:5])
            parts.append(f"Watchlist: {movers}.")
        return " ".join(parts)

    # -- Ausgabe ------------------------------------------------------------------
    async def _speak(self, text: str) -> None:
        """Meldet sich unaufgefordert im Chat – eigene, frische ID, analog zur
        proaktiven ScreenShareEngine."""
        request_id = f"briefing-{uuid.uuid4().hex[:8]}"
        for word in text.split(" "):
            await self.emit("chat.token", {"id": request_id, "text": word + " "})
            await asyncio.sleep(0.02)
        await self.emit("chat.response", {"id": request_id, "text": text, "final": True})

    async def _reply(self, request_id: str, text: str) -> None:
        for word in text.split(" "):
            await self.emit("chat.token", {"id": request_id, "text": word + " "})
            await asyncio.sleep(0.02)
        await self.emit("chat.response", {"id": request_id, "text": text, "final": True})
