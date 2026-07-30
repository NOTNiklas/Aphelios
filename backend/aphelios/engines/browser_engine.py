"""BrowserEngine – Playwright-gesteuertes Lesen von Webseiten (Alpha 1.6,
erste Ausbaustufe).

Ausgelöst über ``/browse <URL> [Frage]`` (server.py routet das statt an
``chat.request`` an ``browser.request``): öffnet die Seite in einem echten
Chromium (via [Playwright](https://playwright.dev/python/)), extrahiert
Titel + sichtbaren Text und lässt Claude die Seite zusammenfassen bzw. eine
konkrete Frage dazu beantworten – ohne ``ANTHROPIC_API_KEY`` gibt es nur den
rohen, ungekürzten Seitentext (dasselbe Fallback-Prinzip wie bei
VisionEngine/KnowledgeEngine).

**Sicherheit:** Jede Anfrage läuft über das SecurityGate (CONFIRM) – APHELIOS
öffnet dabei eine beliebige, vom Nutzer angegebene externe Seite und lädt
deren Inhalt (potenziell inklusive Tracking-Pixeln, Cookies etc.).

**Bewusst NICHT in dieser ersten Ausbaustufe:**

- **Interaktion** (Klicks, Formulare ausfüllen, Login-Flows) – nur lesend.
  Automatisches Klicken auf einer beliebigen Seite ohne granulare, pro-Aktion
  Bestätigung wäre ein zu großes Risiko (Käufe auslösen, Formulare absenden,
  Aktionen im Namen des Nutzers). Eine spätere Ausbaustufe könnte einzelne,
  explizit bestätigte Aktionen ergänzen.
- **Mehrseitige Navigation / Websuche** – der Nutzer muss eine konkrete URL
  angeben, APHELIOS sucht nicht selbstständig im Web. Eine Freitext-Anfrage
  ohne erkennbare URL wird mit einer klaren Fehlermeldung abgelehnt statt
  geraten zu werden.
- **JavaScript-lastige Single-Page-Apps** – ``domcontentloaded`` reicht für
  die meisten Seiten; Seiten, die ihren Inhalt erst nach komplexen
  Client-Interaktionen nachladen, liefern ggf. unvollständigen Text.

Bus-Schnittstelle:
    * ``browser.request`` (in) – ``{id, text}`` (``text`` = URL, optional
      gefolgt von einer Frage)
    * ``chat.token`` / ``chat.response`` (out) – wie VisionEngine/KnowledgeEngine
"""

from __future__ import annotations

import asyncio
import re

from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event
from aphelios.core.security import RiskLevel

BROWSER_PERSONA = """\
Du bist APHELIOS im Browser-Analyse-Modus. Dir wird der Titel und der \
sichtbare Text einer Webseite gezeigt. Beantworte die gestellte Frage \
ausschließlich anhand dieses Inhalts, bzw. fasse die Seite knapp zusammen, \
wenn keine konkrete Frage gestellt wurde – ruhig, präzise, auf Deutsch. \
Ist die Antwort im gegebenen Text nicht enthalten, sag das ehrlich statt zu \
raten.
"""

#: Maximale Zeichen des extrahierten Seitentexts, die an Claude bzw. als
#: roher Fallback-Text gehen – lange Seiten (News-Artikel mit Kommentaren
#: etc.) würden sonst unnötig viele Tokens kosten bzw. den Chat fluten.
_MAX_PAGE_CHARS = 6000

#: Grobe Heuristik, ob das erste Wort einer Anfrage wie eine Domain/URL
#: aussieht (enthält einen Punkt, keine Leerzeichen) – reicht, um
#: "https://example.com Was steht da?" von einer reinen Frage ohne URL
#: ("was ist die hauptstadt von frankreich") zu unterscheiden.
_URL_LIKE_RE = re.compile(r"^\S+\.\S+$")


def _parse_browse_request(text: str) -> tuple[str, str] | None:
    """Trennt eine ``/browse``-Anfrage in URL und optionale Frage.

    Gibt ``None`` zurück, wenn das erste Wort nicht wie eine URL aussieht –
    der Aufrufer soll dann um eine konkrete URL bitten statt zu raten (siehe
    "Bewusst NICHT: Websuche" im Modul-Docstring).
    """
    stripped = text.strip()
    if not stripped:
        return None
    first, _, rest = stripped.partition(" ")
    if not _URL_LIKE_RE.match(first):
        return None
    url = first if first.startswith(("http://", "https://")) else f"https://{first}"
    return url, rest.strip()


async def _fetch_page(url: str, headless: bool) -> tuple[str, str]:
    """Öffnet ``url`` in einem echten Chromium und liefert (Titel, sichtbarer Text).

    Läuft nativ async (Playwrights ``async_api``, kein ``asyncio.to_thread``
    nötig wie bei den synchronen mss/pytesseract-Aufrufen in VisionEngine).
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            title = await page.title()
            text = await page.inner_text("body")
        finally:
            await browser.close()
    return title, text.strip()


class BrowserEngine(BaseEngine):
    """Öffnet Webseiten via Playwright und lässt Claude ihren Inhalt beantworten."""

    name = "browser"

    async def start(self) -> None:
        self._running = True
        self._client = None
        if self.config.has_anthropic:
            try:
                import anthropic

                self._client = anthropic.AsyncAnthropic(api_key=self.config.anthropic_api_key)
            except Exception:  # noqa: BLE001
                self._client = None
        self.bus.subscribe("browser.request", self.handle)

    async def handle(self, event: Event) -> None:
        text = (event.data.get("text") or "").strip()
        request_id = event.data.get("id", "")

        parsed = _parse_browse_request(text)
        if parsed is None:
            await self._reply(
                request_id,
                "Bitte eine URL angeben, z. B. „/browse example.com Was steht auf der Startseite?\"",
            )
            return
        url, question = parsed

        if not await self._confirm_visit(request_id, url):
            return

        try:
            title, page_text = await _fetch_page(url, self.config.browser_headless)
        except ImportError:
            await self._reply(
                request_id,
                'Browser-Steuerung nicht verfügbar: playwright nicht installiert '
                '(pip install -e ".[browser]", danach "playwright install chromium"), '
                'siehe docs/browser.md.',
            )
            return
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Seite konnte nicht geöffnet werden: %s", url)
            await self._reply(
                request_id,
                f"Seite konnte nicht geöffnet werden: {exc}"[:300]
                + ' – wurde "playwright install chromium" schon ausgeführt? Siehe docs/browser.md.',
            )
            return

        if not page_text:
            await self._reply(request_id, f'„{title}" geöffnet, aber kein Text auf der Seite gefunden.')
            return

        if self._client is None:
            await self._reply(
                request_id,
                f'Kein ANTHROPIC_API_KEY konfiguriert, deshalb nur roher Seitentext von „{title}":\n\n'
                f"{page_text[:_MAX_PAGE_CHARS]}",
            )
            return

        await self._answer_with_claude(title, page_text, question, request_id)

    async def _confirm_visit(self, request_id: str, url: str) -> bool:
        """Fragt vor JEDEM Seitenaufruf das SecurityGate – APHELIOS öffnet
        dabei eine beliebige externe Seite im Namen des Nutzers."""
        allowed = await self.security.request(
            action="Webseite öffnen",
            target=url,
            level=RiskLevel.CONFIRM,
            reason="APHELIOS öffnet diese Seite in einem echten Browser und liest ihren Inhalt.",
        )
        if not allowed:
            await self._reply(request_id, "Abgelehnt.")
        return allowed

    async def _answer_with_claude(
        self, title: str, page_text: str, question: str, request_id: str
    ) -> None:
        assert self._client is not None
        prompt = question or "Fasse den Inhalt dieser Seite kurz zusammen."
        user_message = (
            f"Titel der Seite: {title}\n\n"
            f"Sichtbarer Seitentext (ggf. gekürzt):\n{page_text[:_MAX_PAGE_CHARS]}\n\n"
            f"Frage: {prompt}"
        )
        buffer: list[str] = []
        try:
            async with self._client.messages.stream(
                model=self.config.anthropic_model,
                max_tokens=800,
                system=BROWSER_PERSONA,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                async for chunk in stream.text_stream:
                    buffer.append(chunk)
                    await self.emit("chat.token", {"id": request_id, "text": chunk})
        except Exception as exc:  # noqa: BLE001
            self.log.exception("Browser-Analyse fehlgeschlagen")
            await self._reply(request_id, f"Analyse fehlgeschlagen: {str(exc)[:200]}")
            return
        await self.emit("chat.response", {"id": request_id, "text": "".join(buffer), "final": True})

    async def _reply(self, request_id: str, text: str) -> None:
        for word in text.split(" "):
            await self.emit("chat.token", {"id": request_id, "text": word + " "})
            await asyncio.sleep(0.02)
        await self.emit("chat.response", {"id": request_id, "text": text, "final": True})
