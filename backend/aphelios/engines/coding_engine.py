"""CodingEngine – Code schreiben, erklären und überarbeiten über Claude
(Alpha 1.6, erste Ausbaustufe).

Ausgelöst über ``/code <Anfrage>`` (server.py routet das statt an
``chat.request`` an ``coding.request``): Claude beantwortet eine
Programmier-Frage mit vollständigem, lauffähigem Code (Markdown-Codeblöcke)
plus kurzer Erklärung – gestreamt wie bei der ``ReasoningEngine``.

Ohne ``ANTHROPIC_API_KEY`` gibt es eine ehrliche Absage statt eines
Fallback-Rateversuchs: anders als z. B. die ``PlanningEngine`` (die ohne
Claude auf eine simple Satzgrenzen-Heuristik zurückfällt) ergibt ein
"Fallback" für Code-Generierung keinen sinnvollen Ersatz – lieber ehrlich
sagen, dass es einen Key braucht, als schlechten Code zu erfinden.

**Bewusst NICHT in dieser ersten Ausbaustufe:**

- **Kein Datei-Lesen/-Schreiben.** Code entsteht nur im Chat, wird nicht
  automatisch irgendwo gespeichert oder von der Platte gelesen. Beides
  bräuchte eine sorgfältig durchdachte SecurityGate-Bestätigung (Lesen:
  Dateiinhalt könnte sensible Daten enthalten UND ginge an die Claude-API;
  Schreiben: beliebige Datei überschreiben) – eine spätere Ausbaustufe.
- **Kein dediziertes Git/Docker/WSL-Kommando.** Das sind normale
  Kommandozeilenbefehle, die ``/run`` (``AutomationEngine``) bereits
  abdeckt (z. B. ``/run git status``, ``/run docker ps``, ``/run wsl -l``)
  – eine zweite, redundante Ausführungsschiene nur für diese Befehle wäre
  unnötiger Mehraufwand ohne Zusatznutzen.

Bus-Schnittstelle:
    * ``coding.request`` (in) – ``{id, text}``
    * ``chat.token`` / ``chat.response`` (out) – wie ``ReasoningEngine``
"""

from __future__ import annotations

import asyncio

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event

CODING_PERSONA = """\
Du bist APHELIOS im Coding-Modus. Du schreibst, erklärst oder überarbeitest \
Code für einen erfahrenen Entwickler. Antworte auf Deutsch, aber halte Code, \
Bezeichner, Dateinamen und Fehlermeldungen im Original (nicht übersetzen). \
Gib VOLLSTÄNDIGEN, lauffähigen Code in Markdown-Codeblöcken mit \
Sprachangabe aus, danach eine kurze Erklärung (wenige Sätze) – keine \
ausschweifenden Tutorials. Nennt die Anfrage Sprache/Framework nicht \
explizit, triff eine sinnvolle Annahme anhand des Kontexts und nenne sie \
kurz.
"""


class CodingEngine(BaseEngine):
    """Beantwortet Programmier-Anfragen mit Code über Claude (nur im Chat)."""

    name = "coding"

    async def start(self) -> None:
        self._running = True
        self._client = None
        if self.config.has_anthropic:
            try:
                import anthropic

                self._client = anthropic.AsyncAnthropic(api_key=self.config.anthropic_api_key)
            except Exception:  # noqa: BLE001
                self._client = None
        self.bus.subscribe("coding.request", self.handle)

    async def handle(self, event: Event) -> None:
        text = (event.data.get("text") or "").strip()
        request_id = event.data.get("id", "")
        if not text:
            return

        if self._client is None:
            await self._reply(
                request_id,
                "Code-Generierung braucht Claude – es ist kein ANTHROPIC_API_KEY "
                "konfiguriert. Trage einen Key in die .env ein (siehe .env.example), "
                "und ich schreibe dir Code.",
            )
            return

        buffer: list[str] = []
        try:
            async with self._client.messages.stream(
                model=self.config.anthropic_model,
                max_tokens=2048,
                system=CODING_PERSONA,
                messages=[{"role": "user", "content": text}],
            ) as stream:
                async for chunk in stream.text_stream:
                    buffer.append(chunk)
                    await self.emit("chat.token", {"id": request_id, "text": chunk})
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Code-Anfrage fehlgeschlagen")
            await self._reply(request_id, f"Code-Anfrage fehlgeschlagen: {str(exc)[:200]}")
            return
        await self.emit("chat.response", {"id": request_id, "text": "".join(buffer), "final": True})

    async def _reply(self, request_id: str, text: str) -> None:
        for word in text.split(" "):
            await self.emit("chat.token", {"id": request_id, "text": word + " "})
            await asyncio.sleep(0.02)
        await self.emit("chat.response", {"id": request_id, "text": text, "final": True})
