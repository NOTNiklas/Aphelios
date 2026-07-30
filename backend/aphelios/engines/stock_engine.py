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
from typing import Any

import httpx

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event

_YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
# Yahoo blockt Anfragen ohne plausiblen User-Agent häufig mit 429 – kein
# offizieller Vertrag, nur die übliche, weithin genutzte Umgehung (auch
# yfinance & Co. setzen einen Browser-User-Agent).
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _format_quote(q: dict) -> str:
    """Formt eine Kurs-Antwort in einen natürlichsprachlichen Satz."""
    if q.get("change") is None:
        return f"{q['name']} ({q['symbol']}): {q['price']} {q['currency']}"
    sign = "+" if q["change"] >= 0 else ""
    return (
        f"{q['name']} ({q['symbol']}): {q['price']} {q['currency']} "
        f"({sign}{q['change']} / {sign}{q['change_percent']}%)"
    )


class StockEngine(BaseEngine):
    """Ruft periodisch eine Aktien-Watchlist ab und beantwortet Ad-hoc-Kursfragen."""

    name = "stock"

    async def start(self) -> None:
        self._running = True
        self._client = httpx.AsyncClient(timeout=10.0, headers={"User-Agent": _USER_AGENT})
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
            *(self._fetch_quote(s) for s in symbols), return_exceptions=True
        )
        quotes = [r for r in results if isinstance(r, dict)]
        if symbols and not quotes:
            await self.emit(
                "stock.update",
                {"error": "Keine Kursdaten für die Watchlist erhalten.", "updated_at": time.time()},
            )
            return
        await self.emit("stock.update", {"quotes": quotes, "updated_at": time.time()})

    async def _fetch_quote(self, symbol: str) -> dict[str, Any]:
        resp = await self._client.get(
            f"{_YAHOO_CHART_URL}/{symbol}", params={"interval": "1d", "range": "1d"}
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Yahoo Finance antwortete mit Status {resp.status_code}")

        payload = resp.json()
        result = ((payload.get("chart") or {}).get("result")) or []
        if not result:
            chart_error = (payload.get("chart") or {}).get("error")
            raise RuntimeError(
                str(chart_error.get("description", chart_error))
                if isinstance(chart_error, dict)
                else f"Symbol nicht gefunden: {symbol}"
            )

        meta = result[0].get("meta") or {}
        price = meta.get("regularMarketPrice")
        previous_close = meta.get("previousClose") or meta.get("chartPreviousClose")
        if price is None:
            raise RuntimeError(f"Keine Kursdaten für {symbol}")

        change = (price - previous_close) if previous_close else None
        change_percent = (change / previous_close * 100) if change is not None and previous_close else None

        return {
            "symbol": meta.get("symbol", symbol),
            "name": meta.get("shortName") or meta.get("longName") or symbol,
            "price": round(price, 2),
            "currency": meta.get("currency", "USD"),
            "change": round(change, 2) if change is not None else None,
            "change_percent": round(change_percent, 2) if change_percent is not None else None,
        }

    # -- Ad-hoc-Einzelabfrage (Slash-Befehl/Claude-Werkzeug) ----------------------
    async def handle_quote_request(self, event: Event) -> None:
        request_id = event.data.get("id", "")
        raw = (event.data.get("symbol") or event.data.get("text") or "").strip().upper()
        if not raw:
            await self._reply(request_id, 'Bitte ein Börsensymbol angeben, z. B. "/aktie AAPL".')
            return
        try:
            quote = await self._fetch_quote(raw)
        except Exception as exc:  # noqa: BLE001
            self.log.info("Kursabfrage für %s fehlgeschlagen: %s", raw, exc)
            await self._reply(request_id, f"Kurs für {raw} nicht gefunden: {exc}"[:200])
            return
        await self._reply(request_id, _format_quote(quote))

    async def _reply(self, request_id: str, text: str) -> None:
        for word in text.split(" "):
            await self.emit("chat.token", {"id": request_id, "text": word + " "})
            await asyncio.sleep(0.02)
        await self.emit("chat.response", {"id": request_id, "text": text, "final": True})
