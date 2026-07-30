"""Gemeinsamer Yahoo-Finance-Kursabruf – von ``StockEngine`` UND
``ResearchEngine`` genutzt (beide brauchen echte Kursdaten als Grundlage:
die eine fürs Dashboard/Ad-hoc-Abfragen, die andere als Kontext für die
Investment-Committee-Perspektiven). Ausgelagert statt dupliziert, siehe
``aphelios/integrations/google_auth.py``/``spotify_auth.py`` für dasselbe
Muster bei anderen externen Anbindungen.

Kein API-Key nötig: öffentlicher Chart-Endpunkt, dieselbe Datenquelle, auf
der auch die verbreitete ``yfinance``-Bibliothek aufbaut.
"""

from __future__ import annotations

from typing import Any

import httpx

_YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
#: Yahoo blockt Anfragen ohne plausiblen User-Agent häufig mit 429 – kein
#: offizieller Vertrag, nur die übliche, weithin genutzte Umgehung (auch
#: yfinance & Co. setzen einen Browser-User-Agent).
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


async def fetch_quote(client: httpx.AsyncClient, symbol: str) -> dict[str, Any]:
    """Ruft den aktuellen Kurs eines Symbols ab.

    Wirft ``RuntimeError`` mit einer verständlichen deutschen Meldung bei
    HTTP-Fehlern, unbekanntem Symbol oder fehlenden Kursdaten.
    """
    resp = await client.get(f"{_YAHOO_CHART_URL}/{symbol}", params={"interval": "1d", "range": "1d"})
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


def format_quote(q: dict) -> str:
    """Formt eine Kurs-Antwort in einen natürlichsprachlichen Satz."""
    if q.get("change") is None:
        return f"{q['name']} ({q['symbol']}): {q['price']} {q['currency']}"
    sign = "+" if q["change"] >= 0 else ""
    return (
        f"{q['name']} ({q['symbol']}): {q['price']} {q['currency']} "
        f"({sign}{q['change']} / {sign}{q['change_percent']}%)"
    )
