# Bildschirm-Verständnis – Screenshot, OCR und KI-Beschreibung

## Ziel

APHELIOS soll sehen können, was auf dem Bildschirm passiert – eine Fehlermeldung
erklären, eine Frage zu einem sichtbaren Fenster beantworten, oder einfach nur
den sichtbaren Text vorlesbar machen.

Drei Slash-Befehle im Chat (siehe `docs/engines.md`):

| Befehl | Wirkung | Braucht |
|---|---|---|
| `/sieh <Frage>` (oder ohne Frage) | Screenshot + Claude beschreibt/beantwortet | `ANTHROPIC_API_KEY` für echte Analyse, sonst nur OCR-Text |
| `/lies` | Nur den sichtbaren Text extrahieren | Tesseract (lokal, kein API-Key) |
| `/fehler` | Sucht eine sichtbare Fehlermeldung und erklärt sie | Tesseract; für die Erklärung zusätzlich `ANTHROPIC_API_KEY` |

**Grundsatz:** Ohne jede Einrichtung ist Vision inaktiv und meldet das klar
(„kein ANTHROPIC_API_KEY konfiguriert" bzw. „Tesseract nicht gefunden") –
kein Absturz, kein stiller Fehlschlag.

---

## Sicherheit: jede Aktion muss bestätigt werden

Ein Screenshot kann **beliebig sensible Inhalte** zeigen – Passwörter in
Eingabefeldern, private Nachrichten, andere geöffnete Fenster. Deshalb läuft
**jede** Vision-Aktion über das SecurityGate (`docs/security.md`), genau wie
„Passwörter anzeigen" dort explizit bestätigungspflichtig ist – auch `/lies`,
obwohl es rein lokal bleibt und nichts an Claude schickt. Kein Pfad führt an
der Bestätigung vorbei.

---

## Einrichtung

### 1 · Screenshot (immer nötig)

```bash
cd backend
pip install -e ".[vision]"
```

Installiert [`mss`](https://python-mss.readthedocs.io/) (Screenshot,
plattformübergreifend) sowie `pytesseract` + `Pillow` für die OCR-Anbindung.

### 2 · Tesseract (für `/lies` und `/fehler`, sowie den OCR-Fallback von `/sieh`)

`pytesseract` ist nur ein Python-Wrapper – das eigentliche
[Tesseract](https://github.com/tesseract-ocr/tesseract)-Programm muss separat
installiert und im PATH verfügbar sein:

- **Windows:** Installer von der
  [Tesseract-Releases-Seite](https://github.com/UB-Mannheim/tesseract/wiki),
  „Additional language data" für Deutsch mitinstallieren (sonst nur
  Englisch möglich).
- Nach der Installation: neues Terminal öffnen (PATH-Änderungen wirken erst
  danach) und mit `tesseract --version` prüfen.

Sprachpakete über die `.env` wählen (müssen zur Tesseract-Installation passen):

```bash
APHELIOS_OCR_LANG=deu+eng   # Standard: Deutsch + Englisch gemischt
```

### 3 · Claude Vision (für echte Bildbeschreibung/-erklärung)

Braucht nur den ohnehin für die `ConversationEngine` genutzten
`ANTHROPIC_API_KEY` (siehe `.env.example`) – keine separate Einrichtung.
Ohne Key fällt `/sieh` automatisch auf reinen, uninterpretierten OCR-Text
zurück (falls Tesseract installiert ist), `/fehler` zeigt den erkannten
Fehlertext ohne KI-Erklärung.

---

## Grenzen dieser ersten Ausbaustufe (bewusst)

- **Keine Fenster-/Button-/Icon-Erkennung (OpenCV).** Klassische
  Objekterkennung bräuchte entweder eine kuratierte Bibliothek von
  Referenz-Templates (gibt es nicht) oder ein eigens trainiertes Modell
  (eigenständiges Projekt). `/sieh` mit einer gezielten Frage („Wo ist der
  Speichern-Button?") deckt den praktischen Anwendungsfall über Claude
  Vision bereits ab, ganz ohne Template-Matching.
- **Kein dediziertes Tabellen-/Diagramm-Parsing.** Claude liest Tabellen und
  Diagramme aus einem Screenshot bereits nativ mit (multimodal) – eine
  gezielte Frage über `/sieh` („Was zeigt diese Tabelle?") reicht aus, ein
  spezialisierter Parser wäre in den meisten Fällen redundant.
- **Kein automatisches/proaktives Monitoring.** Nur On-Demand über die drei
  Slash-Befehle – kein kontinuierliches Screenshotten im Hintergrund
  (Ressourcen- und Privatsphäre-Kosten wären für eine erste Ausbaustufe
  unverhältnismäßig).
- **Nur der Hauptbildschirm.** Mehrere Monitore: aktuell wird immer nur der
  erste (primäre) aufgenommen.

## Bus-Schnittstelle (für eigene Erweiterungen)

* `vision.request` (in) – `{id, action: "describe"|"ocr"|"find_error", question?}`
  → `chat.token` / `chat.response` (out), wie bei der `AutomationEngine`.

Screenshot und OCR laufen jeweils in einem Thread (`asyncio.to_thread`), damit
eine langsame Tesseract-Erkennung den Event-Loop nicht blockiert.
