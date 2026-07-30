"""ReasoningEngine – mehrstufige Analyse & Werkzeug-Auswahl (Alpha 1.1).

Ausgelöst über den Chat mit dem Präfix ``/denke <Frage>`` (server.py routet das
statt an ``chat.request`` an ``reasoning.request``). Macht ihre Zwischenschritte
sichtbar, statt nur eine fertige Antwort auszuspucken – „mehrstufige Analyse
und Werkzeug-Auswahl" im Sinne der Roadmap:

    1. Werkzeug-Auswahl: eine kurze, deterministische Heuristik (``select_tool``)
       entscheidet, welche Wissensquelle am besten passt – Obsidian-Vault
       (``memory``), Live-Systemwerte (``system``), Aufgaben-Zerlegung
       (``plan``, nutzt dieselbe Logik wie ``PlanningEngine``) oder direkte
       Antwort ohne Zusatzkontext (``direct``). Deterministisch statt ein
       zweiter LLM-Call: schneller, günstiger und ohne Mock unit-testbar.
    2. Kontext aus der gewählten Quelle sammeln – sichtbar im Chat-Verlauf.
    3. Finale Antwort über Claude (oder Fallback) mit dem gesammelten Kontext.

Wiederverwendet bewusst die bestehende ``chat.token``/``chat.response``-Pipeline
statt eigener Frontend-Topics – das HUD zeigt Reasoning-Ausgaben wie jede
andere APHELIOS-Antwort, nur mit sichtbaren Zwischenschritten davor. Zugleich
der Beweis, dass die Streaming-Pipeline "Ende-zu-Ende" auch für eine zweite,
unabhängige Engine funktioniert (Roadmap-Punkt „Streaming-Antworten
Ende-zu-Ende im HUD").

Wichtig: ``chat.response.text`` muss die VOLLSTÄNDIGE, bereits gestreamte
Ausgabe enthalten (Zwischenschritte + finale Antwort) – das Frontend ERSETZT
den Nachrichtentext beim Empfang von ``chat.response`` komplett (siehe
``frontend/src/store/hud.ts``). Würde dort nur die finale Antwort stehen,
würden die sichtbar gestreamten Zwischenschritte augenblicklich wieder
verschwinden. Deshalb sammelt ``handle`` jeden emittierten Token-Text in
einem lokalen Puffer und sendet dessen vollständigen Inhalt als
``chat.response``.

Bus-Schnittstelle:
    * ``reasoning.request`` (in) – ``{id, text}``
    * ``chat.token`` / ``chat.response`` (out) – wie ConversationEngine
"""

from __future__ import annotations

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event, request
from aphelios.engines.planning_engine import break_into_steps

REASONING_PERSONA = """\
Du bist APHELIOS im Analyse-Modus. Du hast bereits recherchiert (Kontext \
unten) und gibst nun eine kurze, klare finale Antwort auf Deutsch – ruhig, \
präzise, ohne die Recherche zu wiederholen.
"""

#: Schlüsselwörter je Werkzeug – erste Übereinstimmung gewinnt, sonst "direct".
_TOOL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "memory": ("erinnerst", "notiz", "vault", "gespeichert", "gemerkt", "weißt du noch"),
    "system": (
        "cpu", "ram", "arbeitsspeicher", "auslastung", "temperatur",
        "akku", "gpu", "vram", "netzwerk",
    ),
    "plan": ("plane", "schritte", "zerleg", "plan für", "schritt für schritt"),
}


def select_tool(text: str) -> str:
    """Deterministische, unit-testbare Werkzeug-Auswahl (kein LLM-Call nötig)."""
    lowered = text.lower()
    for tool, keywords in _TOOL_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return tool
    return "direct"


class ReasoningEngine(BaseEngine):
    """Wählt ein Werkzeug, sammelt sichtbar Kontext, antwortet dann final."""

    name = "reasoning"

    async def start(self) -> None:
        self._running = True
        self._client = None
        if self.config.has_anthropic:
            try:
                import anthropic

                self._client = anthropic.AsyncAnthropic(api_key=self.config.anthropic_api_key)
            except Exception:  # noqa: BLE001
                self._client = None
        self._last_stats: dict | None = None
        self.bus.subscribe("reasoning.request", self.handle)
        self.bus.subscribe("system.stats", self._on_stats)

    async def _on_stats(self, event: Event) -> None:
        self._last_stats = event.data

    async def handle(self, event: Event) -> None:
        text = (event.data.get("text") or "").strip()
        request_id = event.data.get("id", "")
        if not text:
            return

        buffer: list[str] = []

        async def say(chunk: str) -> None:
            buffer.append(chunk)
            await self.emit("chat.token", {"id": request_id, "text": chunk})

        tool = select_tool(text)
        await say(f"🧠 _Analysiere Anfrage … Werkzeug gewählt: **{tool}**._\n\n")

        context = await self._gather_context(tool, text, say)
        await self._answer(request_id, text, context, say)

        await self.emit("chat.response", {"id": request_id, "text": "".join(buffer), "final": True})

    # -- Schritt 2: Kontext je Werkzeug -----------------------------------------
    async def _gather_context(self, tool: str, text: str, say) -> str:
        if tool == "memory":
            result = await request(self.bus, "memory.search", "memory.result", {"query": text}, timeout=1.5)
            hits = (result or {}).get("results") or []
            if not hits:
                await say("_Keine passenden Notizen im Vault gefunden._\n\n")
                return ""
            lines = [f'„{h["title"]}" ({h["category"]}, {h.get("age", "?")})' for h in hits[:3]]
            await say(f"_Gefunden: {', '.join(lines)}._\n\n")
            return "Relevante Vault-Notizen: " + "; ".join(lines)

        if tool == "system":
            if not self._last_stats:
                await say("_Noch keine System-Werte verfügbar._\n\n")
                return ""
            cpu = self._last_stats.get("cpu", {}).get("percent")
            ram = self._last_stats.get("ram", {}).get("percent")
            temp = self._last_stats.get("temperature")
            summary = f"CPU {cpu}%, RAM {ram}%"
            if temp is not None:
                summary += f", Temperatur {temp}°C"
            await say(f"_Aktuelle Werte: {summary}._\n\n")
            return f"Live-Systemwerte: {summary}"

        if tool == "plan":
            steps = await break_into_steps(text, self._client, self.config.anthropic_model)
            listing = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
            await say(f"_Zerlegt in {len(steps)} Schritt(e):_\n{listing}\n\n")
            return "Schritte: " + "; ".join(steps)

        return ""

    # -- Schritt 3: finale Antwort -----------------------------------------------
    async def _answer(self, request_id: str, text: str, context: str, say) -> None:
        if self._client is None:
            # Wichtig: NICHT den rohen `context` ausgeben – der ist für den
            # System-Prompt eines LLM-Aufrufs gedacht (Stichwort-Stil), keine
            # an den Nutzer gerichtete Antwort. Die eigentlichen Rohdaten
            # wurden bereits lesbar in _gather_context() gezeigt.
            await say(
                "_Ohne AI-Schlüssel bleibt es bei den oben gesammelten Rohdaten – "
                "trage einen ANTHROPIC_API_KEY in die .env ein für eine echte Analyse._"
            )
            return

        system = REASONING_PERSONA + (f"\n\nKontext:\n{context}" if context else "")
        try:
            async with self._client.messages.stream(
                model=self.config.anthropic_model,
                max_tokens=800,
                system=system,
                messages=[{"role": "user", "content": text}],
            ) as stream:
                async for chunk in stream.text_stream:
                    await say(chunk)
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Reasoning-Anfrage fehlgeschlagen")
            await say(f"\n\nAnalyse-Antwort fehlgeschlagen: {str(exc)[:200]}")
