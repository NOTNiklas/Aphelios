"""StockEngine – Aktienkurse für das Trading-Dashboard + Chat-Werkzeug.

Anders als Gmail/Kalender/Spotify braucht diese Engine **keinen** eigenen
API-Key: sie nutzt Yahoo Finances öffentlichen Chart-Endpunkt (dieselbe
Datenquelle, auf der u. a. die verbreitete ``yfinance``-Bibliothek aufbaut) –
sofort aktiv, wie die ``WeatherEngine``.

Zwei Nutzungswege:
    * **Watchlist fürs Dashboard** – pollt periodisch eine konfigurierbare
      Symbol-Liste (``APHELIOS_STOCK_SYMBOLS``) und sendet sie als
      ``stock.update`` ans HUD (Trading-Dashboard-Popup).
    * **Ad-hoc-Einzelabfrage** – ``/aktie <Symbol>`` im Chat oder Claudes
      Werkzeug ``get_stock_quote`` (ConversationEngine) beantworten eine
      Frage zu EINEM Symbol, unabhängig von der Watchlist.

Bewusst NICHT: Firmenname-zu-Symbol-Auflösung ("Apple" → "AAPL") – Claude
kennt gängige Ticker-Symbole selbst und füllt sie beim Werkzeug-Aufruf aus;
der Slash-Befehl-Weg erwartet das Symbol direkt, wie z. B. ``/oeffne`` einen
Programmnamen direkt erwartet statt ihn zu erraten.

Bus-Schnittstelle:
    * ``stock.update`` (out) – ``{quotes: [{symbol, name, price, currency,
      change, change_percent}], updated_at}`` bei Erfolg,
      ``{error, updated_at}`` bei Fehler.
    * ``stock.quote.request`` (in) – ``{id, symbol}`` (Claude-Werkzeug) oder
      ``{id, text}`` (Slash-Befehl) → ``chat.token``/``chat.response`` (out).
"""

from __future__ import annotations

import asyncio
import time

import httpx

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event
from aphelios.integrations.yahoo_finance import USER_AGENT, fetch_quote, format_quote


class StockEngine(BaseEngine):
    """Ruft periodisch eine Aktien-Watchlist ab und beantwortet Ad-hoc-Kursfragen."""

    name = "stock"

    async def start(self) -> None:
        self._running = True
        self._client = httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT})
        self.bus.subscribe("stock.quote.request", self.handle_quote_request)
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        task = getattr(self, "_task", None)
        if task:
            task.cancel()
        client = getattr(self, "_client", None)
        if client:
            await client.aclose()

    def _watchlist_symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.config.stock_symbols.split(",") if s.strip()]

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._refresh_watchlist()
            except Exception as exc:  # noqa: BLE001
                self.log.exception("Aktien-Watchlist-Abruf fehlgeschlagen")
                await self.emit(
                    "stock.update",
                    {"error": f"Aktienkurse nicht erreichbar: {exc}"[:200], "updated_at": time.time()},
                )
            await asyncio.sleep(self.config.stock_poll_interval)

    async def _refresh_watchlist(self) -> None:
        symbols = self._watchlist_symbols()
        results = await asyncio.gather(
            *(fetch_quote(self._client, s) for s in symbols), return_exceptions=True
        )
        quotes = [r for r in results if isinstance(r, dict)]
        if symbols and not quotes:
            await self.emit(
                "stock.update",
                {"error": "Keine Kursdaten für die Watchlist erhalten.", "updated_at": time.time()},
            )
            return
        await self.emit("stock.update", {"quotes": quotes, "updated_at": time.time()})

    # -- Ad-hoc-Einzelabfrage (Slash-Befehl/Claude-Werkzeug) ----------------------
    async def handle_quote_request(self, event: Event) -> None:
        request_id = event.data.get("id", "")
        raw = (event.data.get("symbol") or event.data.get("text") or "").strip().upper()
        if not raw:
            await self._reply(request_id, 'Bitte ein Börsensymbol angeben, z. B. "/aktie AAPL".')
            return
        try:
            quote = await fetch_quote(self._client, raw)
        except Exception as exc:  # noqa: BLE001
            self.log.info("Kursabfrage für %s fehlgeschlagen: %s", raw, exc)
            await self._reply(request_id, f"Kurs für {raw} nicht gefunden: {exc}"[:200])
            return
        await self._reply(request_id, format_quote(quote))

    async def _reply(self, request_id: str, text: str) -> None:
        for word in text.split(" "):
            await self.emit("chat.token", {"id": request_id, "text": word + " "})
            await asyncio.sleep(0.02)
        await self.emit("chat.response", {"id": request_id, "text": text, "final": True})
