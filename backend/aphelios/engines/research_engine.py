"""ResearchEngine – Investment-Committee-Analyse (Swarm), rein auf Zuruf.

Baut die *nicht* handelnde, rein analytische Idee aus dem extern
angeschauten Projekt "Vibe-Trading" nativ im Aphelios-Stil nach (eigene
Engine, eigenes Bus-Protokoll, keine übernommene Fremd-Codebasis) – bewusst
OHNE Order-Ausführung/Broker-Anbindung, das bleibt außerhalb dessen, was
diese Engine tut.

``/aktien-analyse <Symbol>`` im Chat oder Claudes Werkzeug
``run_investment_committee``: drei unabhängige Claude-"Perspektiven"
(Bulle/Bär/Risiko) analysieren PARALLEL dasselbe Symbol auf Basis des
echten aktuellen Kurses (``aphelios.integrations.yahoo_finance``), eine
vierte Anfrage fasst sie zu einer ausgewogenen Einschätzung zusammen. Alle
Schritte werden sichtbar gestreamt, analog zur ``ReasoningEngine``.

Jede Ausgabe trägt einen Disclaimer – automatisch generierte Meinung,
keine Anlageberatung.

**Bewusst KEIN automatischer Hintergrund-Lauf mehr** (früher "Scheduled
Research", alle N Stunden über die komplette Watchlist): lief bei jedem
Backend-Neustart erneut, weil sich der letzte Lauf nirgends persistent
merkte – mehrere Neustarts während einer Sitzung führten so zu unerwartet
vielen, ungefragten Claude-Aufrufen und Vault-Notizen. Auf ausdrücklichen
Nutzerwunsch entfernt statt "repariert"; nur noch Ad-hoc-Analyse.

Bus-Schnittstelle:
    * ``research.committee.request`` (in) – ``{id, symbol}`` (Claude-Werkzeug)
      oder ``{id, text}`` (Slash-Befehl) → ``chat.token``/``chat.response``.
"""

from __future__ import annotations

import asyncio

import httpx

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event
from aphelios.integrations.yahoo_finance import USER_AGENT, fetch_quote, format_quote

_DISCLAIMER = "_Automatisch generierte Analyse (Claude), keine Anlageberatung._"

_BULL_PERSONA = (
    "Du bist ein optimistischer Aktienanalyst (die 'Bullen'-Perspektive in "
    "einem Investment-Committee). Nenne die stärksten Argumente FÜR eine "
    "Investition in die genannte Aktie, basierend auf dem aktuellen Kurs und "
    "deinem Wissen über das Unternehmen. 3-4 kurze, konkrete Sätze auf "
    "Deutsch, keine Einleitung."
)
_BEAR_PERSONA = (
    "Du bist ein skeptischer Aktienanalyst (die 'Bären'-Perspektive in einem "
    "Investment-Committee). Nenne die stärksten Argumente GEGEN eine "
    "Investition in die genannte Aktie, basierend auf dem aktuellen Kurs und "
    "deinem Wissen über das Unternehmen. 3-4 kurze, konkrete Sätze auf "
    "Deutsch, keine Einleitung."
)
_RISK_PERSONA = (
    "Du bist der Risikomanager in einem Investment-Committee. Nenne die "
    "größten Risiken (Unternehmen, Branche, Makroökonomie) für die genannte "
    "Aktie, unabhängig von der Kursrichtung. 3-4 kurze, konkrete Sätze auf "
    "Deutsch, keine Einleitung."
)
_SYNTHESIS_PERSONA = (
    "Du bist der Vorsitzende eines Investment-Committees. Dir liegen drei "
    "unabhängige Perspektiven vor (Bulle, Bär, Risiko). Fasse sie zu einer "
    "kurzen, ausgewogenen Einschätzung zusammen (4-6 Sätze, Deutsch) – OHNE "
    "eine konkrete Kauf-/Verkaufsempfehlung auszusprechen, sondern worauf "
    "ein Anleger als Nächstes achten sollte."
)


class ResearchEngine(BaseEngine):
    """Investment-Committee-Analyse, ausschließlich auf Zuruf."""

    name = "research"

    async def start(self) -> None:
        self._running = True
        self._http = httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT})
        self._client = None
        if self.config.has_anthropic:
            try:
                import anthropic

                self._client = anthropic.AsyncAnthropic(api_key=self.config.anthropic_api_key)
            except Exception:  # noqa: BLE001
                self._client = None
        else:
            self.log.info(
                "Kein ANTHROPIC_API_KEY – Investment-Committee-Analyse antwortet auf "
                "Anfragen mit einem Hinweis statt eines Ergebnisses."
            )

        self.bus.subscribe("research.committee.request", self.handle_committee_request)

    async def stop(self) -> None:
        self._running = False
        http = getattr(self, "_http", None)
        if http:
            await http.aclose()

    # -- Kern: drei Perspektiven + Synthese ---------------------------------------
    async def _perspective(self, persona: str, symbol: str, quote_line: str) -> str:
        assert self._client is not None
        resp = await self._client.messages.create(
            model=self.config.anthropic_model,
            max_tokens=300,
            system=persona,
            messages=[{"role": "user", "content": f"Aktie: {symbol}\n{quote_line}"}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()

    async def _synthesize(self, symbol: str, quote_line: str, bull: str, bear: str, risk: str) -> str:
        assert self._client is not None
        prompt = f"Aktie: {symbol}\n{quote_line}\n\nBulle: {bull}\n\nBär: {bear}\n\nRisiko: {risk}"
        resp = await self._client.messages.create(
            model=self.config.anthropic_model,
            max_tokens=400,
            system=_SYNTHESIS_PERSONA,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()

    async def _run_committee(self, symbol: str) -> dict[str, str]:
        """Kompletter Durchlauf: Kurs holen, drei Perspektiven PARALLEL, dann
        Synthese. Von der Ad-hoc-Anfrage UND der geplanten Recherche genutzt,
        damit die eigentliche Logik nicht doppelt existiert."""
        quote = await fetch_quote(self._http, symbol)
        quote_line = format_quote(quote)

        bull, bear, risk = await asyncio.gather(
            self._perspective(_BULL_PERSONA, symbol, quote_line),
            self._perspective(_BEAR_PERSONA, symbol, quote_line),
            self._perspective(_RISK_PERSONA, symbol, quote_line),
        )
        synthesis = await self._synthesize(symbol, quote_line, bull, bear, risk)
        return {"quote_line": quote_line, "bull": bull, "bear": bear, "risk": risk, "synthesis": synthesis}

    # -- Ad-hoc (Slash-Befehl/Claude-Werkzeug) ------------------------------------
    async def handle_committee_request(self, event: Event) -> None:
        request_id = event.data.get("id", "")
        symbol = (event.data.get("symbol") or event.data.get("text") or "").strip().upper()
        if not symbol:
            await self._reply(request_id, 'Bitte ein Börsensymbol angeben, z. B. "/aktien-analyse AAPL".')
            return
        if self._client is None:
            await self._reply(
                request_id,
                "Ohne ANTHROPIC_API_KEY keine Investment-Committee-Analyse möglich – "
                "trage einen Key in die .env ein.",
            )
            return

        buffer: list[str] = []

        async def say(chunk: str) -> None:
            buffer.append(chunk)
            await self.emit("chat.token", {"id": request_id, "text": chunk})

        try:
            result = await self._run_committee(symbol)
        except Exception as exc:  # noqa: BLE001
            self.log.info("Investment-Committee-Analyse für %s fehlgeschlagen: %s", symbol, exc)
            await self._reply(request_id, f"Analyse für {symbol} fehlgeschlagen: {exc}"[:250])
            return

        await say(f"📊 _{result['quote_line']}_\n\n🧠 _Investment-Committee tagt …_\n\n")
        await say(f"🐂 **Bulle:** {result['bull']}\n\n")
        await say(f"🐻 **Bär:** {result['bear']}\n\n")
        await say(f"⚠️ **Risiko:** {result['risk']}\n\n")
        await say(f"🎯 **Fazit:** {result['synthesis']}\n\n")
        await say(_DISCLAIMER)

        await self.emit("chat.response", {"id": request_id, "text": "".join(buffer), "final": True})

    async def _reply(self, request_id: str, text: str) -> None:
        for word in text.split(" "):
            await self.emit("chat.token", {"id": request_id, "text": word + " "})
            await asyncio.sleep(0.02)
        await self.emit("chat.response", {"id": request_id, "text": text, "final": True})
