# Office-Dokumente lesen und analysieren

## Ziel

APHELIOS soll bestehende Word-/Excel-/PowerPoint-Dokumente und PDFs lesen und
verstehen können – „was steht in diesem Bericht", „wie hoch war der Umsatz
laut dieser Tabelle", „fasse diese Präsentation zusammen".

Ein Slash-Befehl im Chat (siehe `docs/engines.md`):

| Befehl | Wirkung | Braucht |
|---|---|---|
| `/dokument <Pfad> [Frage]` | Liest die Datei, beantwortet die Frage (oder fasst zusammen) | `python-docx`/`openpyxl`/`python-pptx`/`pypdf`; `ANTHROPIC_API_KEY` für echte Analyse, sonst nur roher Text |

Beispiele:

```
/dokument C:\Berichte\Q3.docx
/dokument C:\Tabellen\Umsatz.xlsx Wie hoch war der Umsatz im Januar?
/dokument C:\Praesentationen\Kickoff.pptx Fasse die wichtigsten Punkte zusammen
```

Unterstützte Formate: `.docx` (Word), `.xlsx` (Excel), `.pptx` (PowerPoint),
`.pdf`. Die Datei-Endung entscheidet, welcher Reader läuft – der Pfad wird
per Endung erkannt, nicht am ersten Leerzeichen gesplittet, damit Windows-Pfade
mit Leerzeichen (z. B. `C:\Users\User\Meine Dokumente\Bericht.docx`)
korrekt funktionieren.

**Grundsatz:** Ohne jede Einrichtung ist die Dokumenten-Analyse inaktiv und
meldet das klar („zusätzliches Paket nötig" bzw. „Datei nicht gefunden") –
kein Absturz, kein stiller Fehlschlag.

---

## Sicherheit: jede Anfrage muss bestätigt werden

APHELIOS liest dabei den Inhalt einer beliebigen, vom Nutzer angegebenen
Datei und schickt ihn (mit `ANTHROPIC_API_KEY`) an die Claude-API – deshalb
läuft **jede** `/dokument`-Anfrage über das SecurityGate (`docs/security.md`),
dieselbe Abwägung wie bei `/sieh` (Screenshot) und `/browse` (Webseite): der
Inhalt kann beliebig sensibel sein. Kein Pfad führt an der Bestätigung vorbei.

---

## Einrichtung

```bash
cd backend
pip install -e ".[office]"
```

Installiert [`python-docx`](https://python-docx.readthedocs.io/) (Word),
[`openpyxl`](https://openpyxl.readthedocs.io/) (Excel),
[`python-pptx`](https://python-pptx.readthedocs.io/) (PowerPoint) und
[`pypdf`](https://pypdf.readthedocs.io/) (PDF) – alles reine Python-Pakete,
kein zusätzliches Kommandozeilenprogramm nötig (anders als Tesseract bei
Vision oder das Chromium-Binary bei Browser).

Kein weiterer API-Key nötig für das reine Lesen/Extrahieren. Für die
eigentliche Analyse/Zusammenfassung durch Claude wird der ohnehin für die
`ConversationEngine` genutzte `ANTHROPIC_API_KEY` verwendet (siehe
`.env.example`) – ohne Key liefert `/dokument` nur den rohen, ungekürzten
extrahierten Text ohne Interpretation.

---

## Grenzen dieser ersten Ausbaustufe (bewusst)

- **Kein Erstellen/Schreiben neuer Dokumente.** Nur lesend – ein Dokument
  mit korrektem Layout/Formatierung neu zu erzeugen ist ein deutlich
  größerer, eigenständiger Scope (Vorlagen, Styling, Corporate Design …).
- **Keine Formel-Berechnung in Excel.** Zellen werden mit ihrem zuletzt
  gespeicherten Wert gelesen, Formeln selbst werden nicht neu ausgewertet.
- **Keine eingebetteten Bilder/Diagramme.** Nur Text (Excel: Zellwerte,
  PowerPoint: Text-Shapes) – für Bildinhalte gibt es bereits `/sieh` auf
  einen Screenshot der geöffneten Datei.
- **Keine alten Binärformate** (`.doc`/`.xls`/`.ppt` vor Office 2007) – die
  genutzten Bibliotheken unterstützen nur die moderneren XML-Formate.

## Bus-Schnittstelle (für eigene Erweiterungen)

* `office.request` (in) – `{id, text}` (`text` = Pfad, optional gefolgt von
  einer Frage, z. B. `"C:\Berichte\Q3.docx Was ist das Fazit?"`)
  → `chat.token` / `chat.response` (out), wie bei der `BrowserEngine`.

Die Extraktion läuft blockierend in einem Thread (`asyncio.to_thread`) –
python-docx/openpyxl/python-pptx/pypdf sind synchrone Bibliotheken, genau wie
mss/pytesseract bei der `VisionEngine`.
