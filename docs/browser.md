# Browser-Steuerung – Webseiten lesen und beantworten

## Ziel

APHELIOS soll eine Webseite öffnen und ihren Inhalt verstehen können – „was
steht auf dieser Seite", „fasse diesen Artikel zusammen", „was ist die
neueste Version von X laut dieser Release-Seite".

Ein Slash-Befehl im Chat (siehe `docs/engines.md`):

| Befehl | Wirkung | Braucht |
|---|---|---|
| `/browse <URL> [Frage]` | Öffnet die Seite in einem echten Chromium, beantwortet die Frage (oder fasst zusammen) | Playwright + installiertes Chromium; `ANTHROPIC_API_KEY` für echte Analyse, sonst nur roher Seitentext |

Beispiele:

```
/browse example.com
/browse https://example.com/docs Was steht in der Einleitung?
```

Ohne erkennbare URL im ersten Wort der Anfrage kommt eine klare Fehlermeldung
statt eines Rateversuchs – APHELIOS sucht **nicht** selbstständig im Web nach
einer passenden Seite, siehe „Grenzen" unten.

**Grundsatz:** Ohne jede Einrichtung ist die Browser-Steuerung inaktiv und
meldet das klar („playwright nicht installiert" bzw. „wurde playwright
install chromium schon ausgeführt?") – kein Absturz, kein stiller Fehlschlag.

---

## Sicherheit: jede Anfrage muss bestätigt werden

APHELIOS öffnet dabei eine beliebige, vom Nutzer angegebene externe Seite und
lädt deren Inhalt (potenziell inklusive Tracking-Skripten, Cookies-Bannern
etc.) – deshalb läuft **jede** `/browse`-Anfrage über das SecurityGate
(`docs/security.md`). Kein Pfad führt an der Bestätigung vorbei.

---

## Einrichtung

```bash
cd backend
pip install -e ".[browser]"
playwright install chromium
```

Der erste Befehl installiert das `playwright`-Python-Paket, der zweite lädt
das eigentliche Chromium-Browser-Binary herunter (kein pip-Paket – ähnlich
wie bei Tesseract für die Vision-Engine muss das separat passieren). Ohne
diesen zweiten Schritt meldet `/browse` beim ersten Versuch einen klaren
Fehler mit genau diesem Hinweis.

Kein weiterer API-Key nötig für das reine Öffnen/Lesen einer Seite. Für die
eigentliche Analyse/Zusammenfassung durch Claude wird der ohnehin für die
`ConversationEngine` genutzte `ANTHROPIC_API_KEY` verwendet (siehe
`.env.example`) – ohne Key liefert `/browse` nur den rohen, ungekürzten
Seitentext ohne Interpretation.

### Sichtbares Browser-Fenster (optional)

Standardmäßig läuft der Browser **unsichtbar** (headless) – sicherer Standard
für Server-/CI-Umgebungen. Für den JARVIS-Effekt auf dem eigenen Windows-
Desktop (der Nutzer sieht, wie sich ein Browser-Fenster öffnet) lässt sich das
über die `.env` umschalten:

```bash
APHELIOS_BROWSER_HEADLESS=false
```

---

## Grenzen dieser ersten Ausbaustufe (bewusst)

- **Keine Interaktion.** Nur lesend – kein Klicken, keine Formulare
  ausfüllen, keine Login-Flows. Automatisches Klicken auf einer beliebigen
  Seite ohne granulare, pro-Aktion-Bestätigung wäre ein zu großes Risiko
  (versehentlich einen Kauf auslösen, ein Formular absenden, eine Aktion im
  Namen des Nutzers ausführen). Eine spätere Ausbaustufe könnte einzelne,
  explizit bestätigte Aktionen ergänzen.
- **Keine Websuche.** Der Nutzer muss eine konkrete URL angeben – APHELIOS
  rät nicht, welche Seite gemeint sein könnte, und benutzt keine
  Such-Engine im Hintergrund.
- **Kein Umgang mit Login-geschützten Seiten.** Jede Anfrage startet ein
  frisches, anonymes Browser-Profil ohne gespeicherte Cookies/Sessions –
  Inhalte hinter einem Login bleiben unsichtbar.
- **JavaScript-lastige Single-Page-Apps.** Es wird nur bis
  `domcontentloaded` gewartet; Seiten, deren Inhalt erst nach komplexen
  Client-Interaktionen nachlädt, liefern ggf. unvollständigen Text.

## Bus-Schnittstelle (für eigene Erweiterungen)

* `browser.request` (in) – `{id, text}` (`text` = URL, optional gefolgt von
  einer Frage, z. B. `"example.com Was steht da?"`)
  → `chat.token` / `chat.response` (out), wie bei der `VisionEngine`.

Das Öffnen der Seite läuft nativ asynchron über Playwrights `async_api` –
kein `asyncio.to_thread` nötig wie bei den synchronen mss/pytesseract-Aufrufen
der `VisionEngine`.
