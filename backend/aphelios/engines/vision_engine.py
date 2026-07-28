"""VisionEngine – Bildschirm-Verständnis: Screenshot, OCR und KI-Beschreibung
(Alpha 1.4, erste Ausbaustufe).

Drei Aktionen, ausgelöst über Chat-Slash-Befehle (direkt vom Nutzer getippt –
**nicht** von einer AI-Entscheidung ausgelöst, dasselbe Prinzip wie bei der
``AutomationEngine``: kein Prompt-Injection-Pfad zu einer Bildschirmaufnahme):

    * ``/sieh <Frage>`` – Screenshot + Claude Vision beantwortet die Frage
      (oder beschreibt den Bildschirm ohne Frage). Ohne ``ANTHROPIC_API_KEY``
      Fallback auf reinen OCR-Text (siehe unten), keine echte Interpretation.
    * ``/lies`` – nur den sichtbaren Text extrahieren (lokal, Tesseract OCR,
      kein API-Key nötig).
    * ``/fehler`` – sucht per Heuristik nach einer sichtbaren Fehlermeldung;
      gefunden UND ein API-Key vorhanden, erklärt Claude sie und schlägt
      nächste Schritte vor.

**Sicherheit:** Jede Aktion nimmt den Bildschirm auf – das kann beliebig
sensible Inhalte zeigen (Passwörter in Eingabefeldern, private Nachrichten,
andere Fenster). Deshalb läuft **jede** Vision-Aktion über das SecurityGate
(``docs/security.md``), genau wie „Passwörter anzeigen" dort explizit als
bestätigungspflichtig gilt – auch die rein lokale OCR-Aktion, nicht nur die,
die den Screenshot an Claude schickt.

**Bewusst NICHT in dieser ersten Ausbaustufe:**

- **Fenster-/Button-/Icon-Erkennung (OpenCV)** – klassische Objekterkennung
  bräuchte entweder eine kuratierte Bibliothek von Referenz-Templates (die es
  nicht gibt) oder ein trainiertes Modell (eigenes Projekt). `/sieh` deckt
  „was sehe ich, was soll ich klicken" bereits über Claude Vision ab, ganz
  ohne Template-Matching.
- **Dediziertes Tabellen-/Diagramm-Parsing** – Claude liest Tabellen/Diagramme
  aus einem Screenshot bereits nativ mit (multimodal), eine gezielte Frage
  über `/sieh` (z. B. "Was zeigt diese Tabelle?") reicht dafür aus. Ein
  spezialisierter Parser wäre in den allermeisten Fällen redundant.
- **Automatisches/proaktives Hintergrund-Monitoring** – nur On-Demand über
  die Slash-Befehle, kein kontinuierliches Screenshotten (Ressourcen- und
  Privatsphäre-Kosten wären unverhältnismäßig für eine erste Ausbaustufe).

Bus-Schnittstelle:
    * ``vision.request`` (in) – ``{id, action, question?}``
    * ``chat.token`` / ``chat.response`` (out) – wie AutomationEngine
"""

from __future__ import annotations

import asyncio
import base64
import io
import re

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event
from aphelios.core.security import RiskLevel

VISION_PERSONA = """\
Du bist APHELIOS im Bildschirm-Analyse-Modus. Dir wird ein Screenshot des \
Bildschirms deines Nutzers gezeigt. Beschreibe knapp und konkret, was zu \
sehen ist, bzw. beantworte die gestellte Frage dazu – ruhig, präzise, auf \
Deutsch. Keine Warnhinweise zum Datenschutz wiederholen, der Nutzer hat die \
Aufnahme bereits ausdrücklich bestätigt.
"""

#: Schlüsselwörter, die auf eine sichtbare Fehlermeldung hindeuten (deutsch +
#: englisch, da viele Windows-Dialoge/Programme weiterhin englisch sind).
_ERROR_PATTERN = re.compile(
    r"error|fehler|exception|failed|fehlgeschlagen|abgest[uü]rzt|crashed?|"
    r"reagiert nicht|not responding|access denied|zugriff verweigert|"
    r"traceback|stack trace",
    re.IGNORECASE,
)


def _grab_screenshot_png() -> bytes:
    """Nimmt den Hauptbildschirm auf und liefert ihn als PNG-Bytes.

    Blockierend (läuft über ``asyncio.to_thread``) – braucht eine echte oder
    virtuelle Anzeige (in einer reinen Server-/CI-Umgebung ohne Display
    schlägt das mit einer klaren ``Exception`` fehl, siehe ``_capture_screenshot``).
    """
    import mss
    import mss.tools

    with mss.mss() as sct:
        monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        shot = sct.grab(monitor)
        return mss.tools.to_png(shot.rgb, shot.size)


def _extract_text(png_bytes: bytes, lang: str) -> str:
    """Extrahiert sichtbaren Text aus einem Screenshot via Tesseract OCR.

    Blockierend (läuft über ``asyncio.to_thread``) – braucht das
    ``tesseract``-Kommandozeilenprogramm im PATH plus die passenden
    Sprachpakete (siehe ``docs/vision.md``).
    """
    import pytesseract
    from PIL import Image

    image = Image.open(io.BytesIO(png_bytes))
    return pytesseract.image_to_string(image, lang=lang).strip()


class VisionEngine(BaseEngine):
    """Screenshot + OCR + optionale Claude-Vision-Beschreibung."""

    name = "vision"

    async def start(self) -> None:
        self._running = True
        self._client = None
        if self.config.has_anthropic:
            try:
                import anthropic

                self._client = anthropic.AsyncAnthropic(api_key=self.config.anthropic_api_key)
            except Exception:  # noqa: BLE001
                self._client = None
        self.bus.subscribe("vision.request", self.handle)

    async def handle(self, event: Event) -> None:
        action = event.data.get("action", "describe")
        request_id = event.data.get("id", "")
        handler = self._ACTIONS.get(action)
        if handler is None:
            await self._reply(request_id, f"Unbekannte Vision-Aktion: {action!r}")
            return
        try:
            await handler(self, event.data, request_id)
        except Exception as exc:  # noqa: BLE001 – Fehlerursache soll im Chat sichtbar bleiben
            self.log.exception("Vision-Aktion fehlgeschlagen: %s", action)
            await self._reply(request_id, f"Fehlgeschlagen: {exc}"[:300])

    async def _reply(self, request_id: str, text: str) -> None:
        for word in text.split(" "):
            await self.emit("chat.token", {"id": request_id, "text": word + " "})
            await asyncio.sleep(0.02)
        await self.emit("chat.response", {"id": request_id, "text": text, "final": True})

    # -- Aufnahme/OCR-Hilfen ---------------------------------------------------
    async def _capture_screenshot(self) -> bytes:
        return await asyncio.to_thread(_grab_screenshot_png)

    async def _ocr(self, png_bytes: bytes) -> str:
        return await asyncio.to_thread(_extract_text, png_bytes, self.config.ocr_lang)

    async def _confirm_capture(self, request_id: str, purpose: str) -> bool:
        """Fragt vor JEDER Bildschirmaufnahme das SecurityGate – Bildschirminhalt
        kann beliebig sensibel sein, unabhängig davon, ob er lokal bleibt oder
        an Claude geschickt wird."""
        allowed = await self.security.request(
            action="Bildschirm aufnehmen",
            target=purpose,
            level=RiskLevel.CONFIRM,
            reason="Der Screenshot kann sensible Informationen enthalten (Passwörter, private Nachrichten, andere Fenster).",
        )
        if not allowed:
            await self._reply(request_id, "Abgelehnt.")
        return allowed

    async def _safe_ocr(self, png_bytes: bytes, request_id: str) -> str | None:
        """OCR mit klarer Fehlermeldung statt Absturz, falls Tesseract/Pillow
        fehlen. Gibt ``None`` zurück, wenn bereits geantwortet wurde (Aufrufer
        soll dann nichts mehr tun). Ergebnis immer getrimmt – ein OCR-Backend,
        das nur Leerraum liefert, soll wie "kein Text erkannt" behandelt werden,
        nicht wie ein bedeutungsvolles (aber unsichtbares) Ergebnis."""
        try:
            text = await self._ocr(png_bytes)
            return text.strip()
        except ImportError:
            await self._reply(
                request_id,
                'OCR nicht verfügbar: pytesseract/Pillow nicht installiert '
                '(pip install -e ".[vision]"), siehe docs/vision.md.',
            )
            return None
        except Exception as exc:  # noqa: BLE001 – z. B. Tesseract-Binary fehlt im PATH
            await self._reply(
                request_id,
                f"OCR fehlgeschlagen: {exc}"[:250] + " – ist Tesseract installiert und im PATH? Siehe docs/vision.md.",
            )
            return None

    # -- /sieh: Screenshot + Claude Vision (oder OCR-Fallback) -----------------
    async def _describe(self, data: dict, request_id: str) -> None:
        question = (data.get("question") or "").strip()
        if not await self._confirm_capture(request_id, "Screenshot analysieren"):
            return

        try:
            png = await self._capture_screenshot()
        except Exception as exc:  # noqa: BLE001
            await self._reply(request_id, f"Bildschirmaufnahme fehlgeschlagen: {exc}"[:300])
            return

        if self._client is not None:
            await self._describe_with_claude(png, question, request_id)
            return

        text = await self._safe_ocr(png, request_id)
        if text is None:
            return
        if not text:
            await self._reply(
                request_id,
                "Kein Text im Screenshot erkannt, und kein ANTHROPIC_API_KEY konfiguriert "
                "für eine echte Bildanalyse – siehe docs/vision.md.",
            )
            return
        await self._reply(
            request_id,
            "Kein ANTHROPIC_API_KEY konfiguriert, deshalb nur roher OCR-Text ohne "
            f"Interpretation:\n\n{text[:1500]}",
        )

    async def _describe_with_claude(self, png: bytes, question: str, request_id: str) -> None:
        assert self._client is not None
        b64 = base64.b64encode(png).decode("ascii")
        prompt = question or "Beschreibe, was auf diesem Bildschirm zu sehen ist."
        buffer: list[str] = []
        try:
            async with self._client.messages.stream(
                model=self.config.anthropic_model,
                max_tokens=800,
                system=VISION_PERSONA,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {"type": "base64", "media_type": "image/png", "data": b64},
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            ) as stream:
                async for chunk in stream.text_stream:
                    buffer.append(chunk)
                    await self.emit("chat.token", {"id": request_id, "text": chunk})
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Vision-Anfrage an Claude fehlgeschlagen")
            await self._reply(request_id, f"Bildanalyse fehlgeschlagen: {str(exc)[:200]}")
            return
        await self.emit("chat.response", {"id": request_id, "text": "".join(buffer), "final": True})

    # -- /lies: nur Text extrahieren (rein lokal) -------------------------------
    async def _read_text(self, data: dict, request_id: str) -> None:
        if not await self._confirm_capture(request_id, "Bildschirmtext lesen (lokales OCR)"):
            return
        try:
            png = await self._capture_screenshot()
        except Exception as exc:  # noqa: BLE001
            await self._reply(request_id, f"Bildschirmaufnahme fehlgeschlagen: {exc}"[:300])
            return
        text = await self._safe_ocr(png, request_id)
        if text is None:
            return
        await self._reply(request_id, text or "Kein Text erkannt.")

    # -- /fehler: Fehlermeldung erkennen + erklären -----------------------------
    async def _find_error(self, data: dict, request_id: str) -> None:
        purpose = "Bildschirm nach Fehlermeldungen durchsuchen"
        if not await self._confirm_capture(request_id, purpose):
            return
        try:
            png = await self._capture_screenshot()
        except Exception as exc:  # noqa: BLE001
            await self._reply(request_id, f"Bildschirmaufnahme fehlgeschlagen: {exc}"[:300])
            return
        text = await self._safe_ocr(png, request_id)
        if text is None:
            return

        match = _ERROR_PATTERN.search(text)
        if not match:
            await self._reply(request_id, "Keine Fehlermeldung im aktuell sichtbaren Bereich erkannt.")
            return

        if self._client is None:
            await self._reply(
                request_id,
                "Möglicher Fehlerhinweis erkannt (kein ANTHROPIC_API_KEY für eine "
                f"echte Erklärung konfiguriert):\n\n{text[:1000]}",
            )
            return

        await self._explain_error(text, request_id)

    async def _explain_error(self, ocr_text: str, request_id: str) -> None:
        assert self._client is not None
        system = VISION_PERSONA + f"\n\nErkannter Text vom Bildschirm:\n{ocr_text[:1500]}"
        buffer: list[str] = []
        try:
            async with self._client.messages.stream(
                model=self.config.anthropic_model,
                max_tokens=600,
                system=system,
                messages=[
                    {"role": "user", "content": "Was bedeutet diese Fehlermeldung, und was soll ich tun?"}
                ],
            ) as stream:
                async for chunk in stream.text_stream:
                    buffer.append(chunk)
                    await self.emit("chat.token", {"id": request_id, "text": chunk})
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Fehler-Erklärung fehlgeschlagen")
            await self._reply(request_id, f"Erklärung fehlgeschlagen: {str(exc)[:200]}")
            return
        await self.emit("chat.response", {"id": request_id, "text": "".join(buffer), "final": True})

    _ACTIONS = {
        "describe": _describe,
        "ocr": _read_text,
        "find_error": _find_error,
    }
