"""ScreenShareEngine – Live-Bildschirmfreigabe: Chat-Analyse geteilter Frames.

Ergänzt die Einzel-Screenshot-Befehle der VisionEngine (``/sieh`` etc., die
einen eigenen OS-Screenshot per ``mss`` aufnehmen) um einen Weg, bei dem der
NUTZER aktiv seinen Bildschirm über den Browser teilt (Screen Capture API,
``getDisplayMedia``) – z. B. um gezielt ein bestimmtes Fenster/einen
Anwendungsbereich zu zeigen statt des ganzen Desktops.

**Kein echtes Video-Streaming an Claude** – die Messages-API nimmt nur
Einzelbilder, kein Video. Der Browser sendet stattdessen periodisch Frames
(alle paar Sekunden), das Backend hält immer nur den JEWEILS LETZTEN im
Speicher (kein Frame-Archiv, keine Aufzeichnung).

Zwei Nutzungswege:
    * **Auf Zuruf** – ``/bildschirm <Frage>`` analysiert den aktuell letzten
      Frame einmalig.
    * **Proaktiv (Schalter im HUD)** – alle 10s wird der letzte Frame
      automatisch geprüft; APHELIOS meldet sich nur, wenn Claude etwas
      Auffälliges findet (Fehlermeldung, Absturz, offensichtliches
      Problem) – sonst bleibt es lautlos, kein Spam bei jedem Intervall.

Bus-Schnittstelle:
    * ``screen.frame`` (in) – ``{frame_base64}`` (JPEG, roh oder als
      Data-URL) – vom Frontend periodisch gesendet, solange geteilt wird.
    * ``screen.share.stop`` (in) – Nutzer hat die Freigabe beendet, letzter
      Frame wird verworfen (keine veralteten Analysen mehr möglich).
    * ``screen.ask.request`` (in) – ``{id, question}`` → ``chat.token``/
      ``chat.response`` (out), wie bei anderen Engines.
    * ``screen.proactive.set`` (in) – ``{enabled}`` – schaltet die
      automatische Prüfung an/aus.
"""

from __future__ import annotations

import asyncio
import uuid

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event

_PROACTIVE_INTERVAL = 10.0
_NOTHING_MARKER = "NICHTS"

_ASK_SYSTEM = (
    "Du bist APHELIOS und siehst gerade den per Bildschirmfreigabe geteilten "
    "Bildschirm des Nutzers (ein Einzelbild, kein echtes Video, kann leicht "
    "veraltet sein). Beantworte die Frage dazu kurz, konkret und auf Deutsch."
)
_PROACTIVE_SYSTEM = (
    "Du bist APHELIOS und beobachtest den per Bildschirmfreigabe geteilten "
    "Bildschirm des Nutzers (ein Einzelbild). Antworte NUR mit dem Wort "
    "'NICHTS', wenn nichts Auffälliges zu sehen ist (normale Arbeit, keine "
    "Fehler, kein offensichtliches Problem). Siehst du dagegen eine "
    "Fehlermeldung, einen Absturz oder etwas, wo offensichtlich Hilfe "
    "gebraucht wird, antworte stattdessen mit einem kurzen, konkreten "
    "Hinweis auf Deutsch (1-2 Sätze), was du siehst und wie du helfen "
    "kannst."
)


class ScreenShareEngine(BaseEngine):
    """Hält den zuletzt geteilten Bildschirm-Frame und lässt Claude ihn
    auf Zuruf oder proaktiv analysieren."""

    name = "screen"

    async def start(self) -> None:
        self._running = True
        self._client = None
        if self.config.has_anthropic:
            try:
                import anthropic

                self._client = anthropic.AsyncAnthropic(api_key=self.config.anthropic_api_key)
            except Exception:  # noqa: BLE001
                self._client = None

        self._latest_frame: str | None = None
        self._proactive_enabled = False

        self.bus.subscribe("screen.frame", self._on_frame)
        self.bus.subscribe("screen.share.stop", self._on_stop)
        self.bus.subscribe("screen.ask.request", self._on_ask)
        self.bus.subscribe("screen.proactive.set", self._on_proactive_set)

        self._task = asyncio.create_task(self._proactive_loop())

    async def stop(self) -> None:
        self._running = False
        task = getattr(self, "_task", None)
        if task:
            task.cancel()

    async def _on_frame(self, event: Event) -> None:
        raw = event.data.get("frame_base64") or ""
        # Data-URL-Prefix ("data:image/jpeg;base64,...") abschneiden, falls vorhanden.
        if raw.startswith("data:") and "," in raw:
            raw = raw.split(",", 1)[1]
        self._latest_frame = raw or None

    async def _on_stop(self, event: Event) -> None:
        self._latest_frame = None
        self._proactive_enabled = False

    async def _on_proactive_set(self, event: Event) -> None:
        self._proactive_enabled = bool(event.data.get("enabled"))

    async def _ask_claude(self, system: str, user_text: str) -> str:
        assert self._client is not None
        assert self._latest_frame is not None
        resp = await self._client.messages.create(
            model=self.config.anthropic_model,
            max_tokens=400,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": self._latest_frame,
                            },
                        },
                        {"type": "text", "text": user_text},
                    ],
                }
            ],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()

    # -- Auf Zuruf ("/bildschirm <Frage>") ----------------------------------------
    async def _on_ask(self, event: Event) -> None:
        request_id = event.data.get("id", "")
        question = (event.data.get("question") or "Was siehst du gerade?").strip()
        if self._client is None:
            await self._reply(request_id, "Ohne ANTHROPIC_API_KEY keine Bildschirm-Analyse möglich.")
            return
        if self._latest_frame is None:
            await self._reply(
                request_id,
                "Keine aktive Bildschirmfreigabe – zuerst über den 'Bildschirm teilen'-Button starten.",
            )
            return
        try:
            answer = await self._ask_claude(_ASK_SYSTEM, question)
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Bildschirm-Analyse fehlgeschlagen")
            await self._reply(request_id, f"Analyse fehlgeschlagen: {exc}"[:200])
            return
        await self._reply(request_id, answer)

    # -- Proaktiv -------------------------------------------------------------
    async def _proactive_loop(self) -> None:
        while self._running:
            await asyncio.sleep(_PROACTIVE_INTERVAL)
            if not self._proactive_enabled or self._client is None or self._latest_frame is None:
                continue
            try:
                comment = await self._ask_claude(_PROACTIVE_SYSTEM, "Was siehst du gerade?")
            except Exception:  # noqa: BLE001
                self.log.exception("Proaktive Bildschirm-Prüfung fehlgeschlagen")
                continue
            if comment.strip().upper().startswith(_NOTHING_MARKER):
                continue
            await self._speak(comment)

    async def _speak(self, text: str) -> None:
        """Meldet sich unaufgefordert im Chat – eigene, frische ID (kein
        vorheriger Nutzer-Turn), analog zum unaufgeforderten Wake-Word-Gruß."""
        request_id = f"screen-proactive-{uuid.uuid4().hex[:8]}"
        for word in text.split(" "):
            await self.emit("chat.token", {"id": request_id, "text": word + " "})
            await asyncio.sleep(0.02)
        await self.emit("chat.response", {"id": request_id, "text": text, "final": True})

    async def _reply(self, request_id: str, text: str) -> None:
        for word in text.split(" "):
            await self.emit("chat.token", {"id": request_id, "text": word + " "})
            await asyncio.sleep(0.02)
        await self.emit("chat.response", {"id": request_id, "text": text, "final": True})
