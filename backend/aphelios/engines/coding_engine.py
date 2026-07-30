"""CodingEngine – Code schreiben, erklären und überarbeiten über Claude
(Alpha 1.6, erste Ausbaustufe, seit Kurzem inkl. Datei-Schreiben).

Zwei Aktionen, ausgelöst über Chat-Slash-Befehle:

    * ``/code <Anfrage>`` – Claude beantwortet eine Programmier-Frage mit
      vollständigem, lauffähigem Code (Markdown-Codeblöcke) plus kurzer
      Erklärung, gestreamt wie bei der ``ReasoningEngine``. Bleibt im Chat,
      keine Datei wird angefasst.
    * ``/code-datei <Pfad> <Anfrage>`` – wie oben, aber der erste
      Code-Block der Antwort wird zusätzlich in ``<Pfad>`` geschrieben
      (VS-Code-Workflow: Datei danach im Editor öffnen) – **immer** mit
      SecurityGate-Bestätigung, siehe unten.

Ohne ``ANTHROPIC_API_KEY`` gibt es eine ehrliche Absage statt eines
Fallback-Rateversuchs: anders als z. B. die ``PlanningEngine`` (die ohne
Claude auf eine simple Satzgrenzen-Heuristik zurückfällt) ergibt ein
"Fallback" für Code-Generierung keinen sinnvollen Ersatz – lieber ehrlich
sagen, dass es einen Key braucht, als schlechten Code zu erfinden.

**Sicherheit beim Datei-Schreiben:** ``/code-datei`` läuft über das
SecurityGate (CONFIRM, dieselbe Abwägung wie ``delete_path`` in der
``AutomationEngine``: eine beliebige Datei zu überschreiben ist riskant).
Zusätzlich bewusst restriktiver als ``delete_path``: das Elternverzeichnis
muss bereits existieren – APHELIOS legt keine neuen Ordnerstrukturen an,
das würde das Risiko verstreuter, unbeabsichtigter Ordner erhöhen.

**Bewusst NICHT in dieser ersten Ausbaustufe:**

- **Kein Datei-Lesen.** ``/code-datei`` schreibt, liest aber keinen
  bestehenden Dateiinhalt zum Refactoring ein – das bräuchte dieselbe
  Sensibilitäts-Abwägung wie bei der ``OfficeEngine`` (Inhalt könnte
  sensible Daten enthalten UND ginge an die Claude-API), hier aber für
  BELIEBIGE Dateitypen statt nur Office-Formate – eine spätere Ausbaustufe.
- **Nur EIN Code-Block pro Datei.** Enthält Claudes Antwort mehrere
  Code-Blöcke (z. B. Hauptdatei + Beispielaufruf), wird nur der erste in
  die Datei geschrieben; der volle Text bleibt trotzdem im Chat sichtbar.
- **Kein dediziertes Git/Docker/WSL-Kommando.** Das sind normale
  Kommandozeilenbefehle, die ``/run`` (``AutomationEngine``) bereits
  abdeckt (z. B. ``/run git status``, ``/run docker ps``, ``/run wsl -l``)
  – eine zweite, redundante Ausführungsschiene nur für diese Befehle wäre
  unnötiger Mehraufwand ohne Zusatznutzen.
- **Keine eigene VS-Code-Extension.** ``/code-datei`` schreibt die Datei,
  der Nutzer öffnet sie selbst in VS Code (oder APHELIOS öffnet den Ordner
  via ``/oeffne``) – eine echte Extension mit Live-Anbindung wäre ein
  eigenständiges, deutlich größeres Softwareprojekt (siehe ROADMAP.md).

Bus-Schnittstelle:
    * ``coding.request`` (in) – ``{id, text, action?}`` (``action``:
      ``"explain"`` (Standard) oder ``"write_file"``)
    * ``chat.token`` / ``chat.response`` (out) – wie ``ReasoningEngine``
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event
from aphelios.core.security import RiskLevel

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

#: Erkennt Markdown-Codeblöcke (```sprache\n...code...```) – der erste
#: Treffer wird bei ``/code-datei`` in die Zieldatei geschrieben.
_CODE_BLOCK_RE = re.compile(r"```[a-zA-Z0-9_+-]*\r?\n(.*?)```", re.DOTALL)


def _parse_code_file_request(text: str) -> tuple[str, str] | None:
    """Trennt eine ``/code-datei``-Anfrage in Pfad und Programmier-Anfrage.

    Pfade mit Leerzeichen werden über Anführungszeichen unterstützt (anders
    als bei ``OfficeEngine``, wo eine bekannte Datei-Endung als Trenner
    diente – Code-Dateien haben zu viele mögliche Endungen, um das
    zuverlässig zu erkennen): ``/code-datei "C:\\Mein Ordner\\a.py" ...``.
    Ohne Anführungszeichen zählt das erste Wort als Pfad.
    """
    stripped = text.strip()
    if not stripped:
        return None
    if stripped[0] in "\"'":
        quote = stripped[0]
        end = stripped.find(quote, 1)
        if end == -1:
            return None
        path = stripped[1:end].strip()
        rest = stripped[end + 1 :].strip()
    else:
        path, _, rest = stripped.partition(" ")
        rest = rest.strip()
    if not path:
        return None
    return path, rest


def _first_code_block(markdown_text: str) -> str | None:
    match = _CODE_BLOCK_RE.search(markdown_text)
    if not match:
        return None
    return match.group(1).rstrip("\n")


class CodingEngine(BaseEngine):
    """Beantwortet Programmier-Anfragen mit Code über Claude, optional in eine Datei."""

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
        action = event.data.get("action", "explain")
        if action == "write_file":
            await self._handle_write_file(event)
        else:
            await self._handle_explain(event)

    # -- /code: nur im Chat -----------------------------------------------------
    async def _handle_explain(self, event: Event) -> None:
        text = (event.data.get("text") or "").strip()
        request_id = event.data.get("id", "")
        if not text:
            return

        if self._client is None:
            await self._reply(request_id, self._no_key_message())
            return

        try:
            reply = await self._generate_code(text, request_id)
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Code-Anfrage fehlgeschlagen")
            await self._reply(request_id, f"Code-Anfrage fehlgeschlagen: {str(exc)[:200]}")
            return
        await self.emit("chat.response", {"id": request_id, "text": reply, "final": True})

    # -- /code-datei: zusätzlich in eine Datei schreiben -------------------------
    async def _handle_write_file(self, event: Event) -> None:
        text = (event.data.get("text") or "").strip()
        request_id = event.data.get("id", "")

        parsed = _parse_code_file_request(text)
        if parsed is None:
            await self._reply(
                request_id,
                'Bitte Pfad und Anfrage angeben, z. B. "/code-datei hello.py '
                'Schreibe eine Begrüßungsfunktion" (Pfade mit Leerzeichen in '
                'Anführungszeichen).',
            )
            return
        path_str, request_text = parsed
        if not request_text:
            await self._reply(request_id, "Bitte zusätzlich beschreiben, welcher Code entstehen soll.")
            return

        if self._client is None:
            await self._reply(request_id, self._no_key_message())
            return

        path = Path(path_str)
        if not await self._confirm_write(request_id, path_str, path):
            return

        if not path.parent.exists():
            await self._reply(request_id, f"Verzeichnis existiert nicht: {path.parent}")
            return

        try:
            reply = await self._generate_code(request_text, request_id)
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Code-Anfrage fehlgeschlagen")
            await self._reply(request_id, f"Code-Anfrage fehlgeschlagen: {str(exc)[:200]}")
            return
        await self.emit("chat.response", {"id": request_id, "text": reply, "final": True})

        code = _first_code_block(reply)
        save_id = f"{request_id}-save"
        if code is None:
            await self._reply(save_id, "Kein Code-Block in der Antwort gefunden, nichts gespeichert.")
            return

        try:
            await asyncio.to_thread(path.write_text, code, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Datei konnte nicht geschrieben werden: %s", path_str)
            await self._reply(save_id, f"Datei konnte nicht geschrieben werden: {exc}"[:300])
            return

        lines = code.count("\n") + 1
        await self._reply(save_id, f"Gespeichert unter {path_str} ({lines} Zeile(n)) – bereit für VS Code.")

    async def _confirm_write(self, request_id: str, path_str: str, path: Path) -> bool:
        """Fragt vor JEDEM Datei-Schreiben das SecurityGate – dieselbe
        Abwägung wie ``delete_path`` in der ``AutomationEngine``: eine
        beliebige Datei zu überschreiben ist riskant, unabhängig davon,
        wer den Inhalt vorgeschlagen hat."""
        verb = "überschreiben" if path.exists() else "anlegen"
        allowed = await self.security.request(
            action="Code-Datei schreiben",
            target=path_str,
            level=RiskLevel.CONFIRM,
            reason=f"APHELIOS würde diese Datei {verb} – mit von Claude generiertem Code.",
        )
        if not allowed:
            await self._reply(request_id, "Abgelehnt.")
        return allowed

    async def _generate_code(self, text: str, request_id: str) -> str:
        assert self._client is not None
        buffer: list[str] = []
        async with self._client.messages.stream(
            model=self.config.anthropic_model,
            max_tokens=2048,
            system=CODING_PERSONA,
            messages=[{"role": "user", "content": text}],
        ) as stream:
            async for chunk in stream.text_stream:
                buffer.append(chunk)
                await self.emit("chat.token", {"id": request_id, "text": chunk})
        return "".join(buffer)

    def _no_key_message(self) -> str:
        return (
            "Code-Generierung braucht Claude – es ist kein ANTHROPIC_API_KEY "
            "konfiguriert. Trage einen Key in die .env ein (siehe .env.example), "
            "und ich schreibe dir Code."
        )

    async def _reply(self, request_id: str, text: str) -> None:
        for word in text.split(" "):
            await self.emit("chat.token", {"id": request_id, "text": word + " "})
            await asyncio.sleep(0.02)
        await self.emit("chat.response", {"id": request_id, "text": text, "final": True})
