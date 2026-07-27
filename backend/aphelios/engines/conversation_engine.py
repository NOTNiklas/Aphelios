"""ConversationEngine – Dialog über die Claude API (mit Fallback).

Abonniert ``chat.request`` und antwortet mit gestreamten ``chat.token``-Events,
gefolgt von einem abschließenden ``chat.response``. Der Systemprompt definiert
die APHELIOS-Persönlichkeit (ruhig, präzise, deutsch, dezenter Humor).

Ohne ``ANTHROPIC_API_KEY`` läuft die Engine im **Fallback-Modus** mit lokalen
Standardantworten, damit das System jederzeit lauffähig bleibt.

Erweiterung: OpenAI- und Ollama-Fallback sind als Hooks vorgesehen (Roadmap).
"""

from __future__ import annotations

import asyncio

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event

APHELIOS_PERSONA = """\
Du bist APHELIOS – ein hochentwickelter Desktop-AI-Assistent im Stil von \
J.A.R.V.I.S. aus Iron Man. Du bist KEIN gewöhnlicher Chatbot, sondern das \
zweite Gehirn und Betriebssystem-Assistent deines Nutzers.

Sprich ruhig, intelligent, präzise und lösungsorientiert. Nutze dezenten, \
trockenen Humor, wenn er passt – niemals aufdringlich, niemals übertrieben. \
Antworte auf Deutsch, kurz und klar. Du kennst die Projekte des Nutzers, \
merkst dir seine Arbeitsweise und schlägst proaktiv Optimierungen vor.

Wenn du eine Aktion am System ausführen würdest, die gefährlich ist \
(Dateien löschen, Registry ändern, Programme deinstallieren), weist du \
darauf hin, dass eine Bestätigung nötig ist.
"""

# Kurze, thematisch passende Offline-Antworten für den Fallback-Modus.
_FALLBACK_REPLIES = {
    "greeting": "Systeme online. Ich bin bereit, Sir.",
    "no_key": (
        "Ich arbeite gerade im Offline-Modus – es ist kein AI-Schlüssel "
        "hinterlegt. Trage einen ANTHROPIC_API_KEY in die .env ein, und ich "
        "stehe dir mit voller Leistung zur Verfügung."
    ),
}


class ConversationEngine(BaseEngine):
    """Verarbeitet Chat-Anfragen und streamt Antworten zurück."""

    name = "conversation"

    async def start(self) -> None:
        self._running = True
        self._client = None
        self._init_error: str | None = None
        if self.config.has_anthropic:
            try:
                import anthropic

                self._client = anthropic.AsyncAnthropic(api_key=self.config.anthropic_api_key)
                self.log.info("Claude API aktiv (%s)", self.config.anthropic_model)
            except Exception as exc:  # noqa: BLE001
                self.log.exception("Anthropic-Client konnte nicht initialisiert werden")
                self._init_error = str(exc)
        else:
            self.log.warning("Kein ANTHROPIC_API_KEY – ConversationEngine läuft im Fallback-Modus")

        self.bus.subscribe("chat.request", self.handle)

    async def handle(self, event: Event) -> None:
        text = (event.data.get("text") or "").strip()
        request_id = event.data.get("id", "")
        if not text:
            return
        if self._client is None:
            await self._respond_fallback(text, request_id)
        else:
            await self._respond_claude(text, request_id)

    # -- Claude ---------------------------------------------------------------
    async def _respond_claude(self, text: str, request_id: str) -> None:
        assert self._client is not None
        collected: list[str] = []
        try:
            async with self._client.messages.stream(
                model=self.config.anthropic_model,
                max_tokens=1024,
                system=APHELIOS_PERSONA,
                messages=[{"role": "user", "content": text}],
            ) as stream:
                async for chunk in stream.text_stream:
                    collected.append(chunk)
                    await self.emit("chat.token", {"id": request_id, "text": chunk})
            reply = "".join(collected)
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Claude-Anfrage fehlgeschlagen – nutze Fallback")
            await self._respond_fallback(text, request_id, error=str(exc))
            return
        await self.emit("chat.response", {"id": request_id, "text": reply, "final": True})

    # -- Fallback -------------------------------------------------------------
    async def _respond_fallback(
        self, text: str, request_id: str, error: str | None = None
    ) -> None:
        lowered = text.lower()
        if error:
            # Ein Key ist vorhanden, aber die Anfrage ist trotzdem gescheitert –
            # das darf NICHT wie "kein Key hinterlegt" aussehen, sonst ist der
            # eigentliche Fehler für den Nutzer unsichtbar.
            reply = (
                "Die Verbindung zur Claude API ist gerade gestört, obwohl ein "
                f"API-Key hinterlegt ist. Fehlermeldung: {error[:200]}. Prüfe den "
                "Key in der .env auf zusätzliche Leerzeichen/Anführungszeichen, "
                "das Kontingent in der Anthropic Console und deine "
                "Internetverbindung."
            )
        elif self._init_error:
            reply = (
                "Der Claude-Client konnte nicht gestartet werden: "
                f"{self._init_error[:200]}"
            )
        elif any(word in lowered for word in ("hallo", "hi", "hey", "aphelios")):
            reply = _FALLBACK_REPLIES["greeting"]
        else:
            reply = _FALLBACK_REPLIES["no_key"]

        # Antwort zeichenweise streamen, damit sich das HUD echt anfühlt.
        for word in reply.split(" "):
            await self.emit("chat.token", {"id": request_id, "text": word + " "})
            await asyncio.sleep(0.03)
        await self.emit("chat.response", {"id": request_id, "text": reply, "final": True})
