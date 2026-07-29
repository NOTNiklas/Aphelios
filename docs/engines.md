# Engines

Eine **Engine** ist ein unabhängiges Modul, das eine Fähigkeit von APHELIOS bereitstellt.
Alle Engines erben von `BaseEngine` und kommunizieren ausschließlich über den EventBus.

## Lebenszyklus

```
EngineManager.register(engine)
        │
        ▼
   await engine.start()      # abonniert Topics, startet Hintergrund-Loops
        │
        ▼
   engine.handle(event)      # reagiert auf abonnierte Events
        │
        ▼
   await engine.stop()       # fährt sauber herunter
```

## Eine neue Engine erstellen

```python
from aphelios.core.engine import BaseEngine
from aphelios.core.event_bus import Event

class MyEngine(BaseEngine):
    name = "my"

    async def start(self) -> None:
        self.bus.subscribe("my.request", self.handle)

    async def handle(self, event: Event) -> None:
        # ... Arbeit erledigen ...
        await self.bus.publish(Event("my.response", {"ok": True}, source=self.name))

    async def stop(self) -> None:
        pass
```

Registrieren in `aphelios/engines/__init__.py` (Liste `ALL_ENGINES`) – der
`EngineManager` instanziiert und startet sie dann automatisch:

```python
manager.register(MyEngine(bus, config, security))
```

## Engines in Alpha 1.0

### SystemEngine (real)
Sammelt System-Telemetrie mit `psutil` und publisht periodisch `system.stats`:
CPU-Last, RAM, Disk, Netzwerk-Durchsatz, Temperatur und Akku. GPU/VRAM werden
über `pynvml`/`GPUtil` gelesen, falls verfügbar – sonst wird der Wert als „n/a"
markiert. Das Intervall kommt aus `APHELIOS_STATS_INTERVAL`.

### ConversationEngine (real)
Beantwortet Chat-Anfragen (`chat.request`) über den konfigurierten AI-Provider
(Standard: Claude API). Der Systemprompt definiert die APHELIOS-Persönlichkeit
(ruhig, präzise, deutsch). Ohne API-Key antwortet die Engine mit einer sinnvollen
lokalen Fallback-Nachricht. **Wichtig:** Ist ein Key vorhanden, die Anfrage
schlägt aber trotzdem fehl (falscher Key, Kontingent, Netzwerk), zeigt die
Antwort die **echte Fehlermeldung** an – nicht dieselbe „kein Key hinterlegt"-
Nachricht wie ohne Key, damit der Fehler diagnostizierbar bleibt.

### MemoryEngine (real)
Persistiert Informationen als Markdown-Notizen in einem Obsidian-Vault. Jede Notiz
erhält YAML-Frontmatter mit `tags`, wird in eine passende Kategorie (Personen,
Projekte, Ideen, Code, Fehler, Lösungen …) einsortiert und über `[[Backlinks]]`
verknüpft. Ein SQLite-Index ermöglicht schnelles Wiederfinden. **Automatische
Verlinkung:** Neue Notizen werden automatisch mit thematisch verwandten
Notizen verknüpft (gleiche Kategorie oder gemeinsame Tags) – dadurch zeigt
Obsidians eingebauter **Graph View** die Notizen als verbundenes Netz, ganz
ohne manuelles Verlinken. **Update statt Duplikat:** Titel + Kategorie
bestimmen den Dateipfad – ein zweites `memory.note` mit demselben
Titel/derselben Kategorie überschreibt dieselbe Datei und denselben
SQLite-Eintrag, statt eine zweite Notiz anzulegen (`created` bleibt dabei
erhalten, ein zusätzliches `updated` markiert die letzte Änderung). Darauf
bauen andere Engines auf, die einen Vorgang wiederholt protokollieren, z. B.
die `PlanningEngine` und die `AutomationEngine` (siehe unten).

### WeatherEngine (real)
Ruft periodisch echtes Wetter über [Open-Meteo](https://open-meteo.com/) ab –
kein API-Key nötig. Stadt über `APHELIOS_WEATHER_CITY` konfigurierbar.

### MailEngine / CalendarEngine (real, optional)
Lesen ungelesene Gmail-Nachrichten bzw. kommende Google-Kalender-Termine.
Anders als Wetter benötigen beide eine eigene Google-OAuth-Anmeldung des
Nutzers (`docs/integrations.md`) – ohne diese bleiben sie inaktiv und das HUD
zeigt weiterhin eine Mock-Vorschau. Rein lesend; Schreibzugriff ist eine
spätere, über das SecurityGate bestätigungspflichtige Ausbaustufe.

## Engines in Alpha 1.1

### MemoryEngine – generischer KV-Store (neu)
Zusätzlich zu Notizen/Suche kann die MemoryEngine jetzt auch beliebige,
JSON-serialisierbare Werte unter einem Schlüssel persistieren – gedacht für
internen Engine-Zustand, der einen Backend-Neustart überleben soll, aber
keine eigene Obsidian-Notiz braucht:

* `memory.kv.set` (in) – `{key, value}`
* `memory.kv.get` (in) – `{id, key}` → antwortet mit `memory.kv.result`
  `{id, key, value}` (`value: null` falls nicht vorhanden)

Genutzt von der `ConversationEngine` für den Konversationsverlauf (siehe unten).

### ConversationEngine – persistenter Kontext (erweitert)
Führt jetzt einen Gesprächsverlauf (letzte `MAX_HISTORY_MESSAGES` Nachrichten)
über mehrere Chat-Anfragen hinweg mit – vorher wurde jede Anfrage isoliert
beantwortet. Der Verlauf wird über `memory.kv.set`/`memory.kv.get`
(MemoryEngine) persistiert, übersteht also einen Backend-Neustart. Vor jeder
Antwort fragt die Engine zusätzlich per `memory.search` thematisch passende
Vault-Notizen ab und reicht sie als kurzen Kontext-Hinweis in den
System-Prompt – der Vault wird damit tatsächlich mitgelesen, nicht nur
beschrieben.

### PlanningEngine (real)
Zerlegt eine Aufgabe in konkrete Schritte. Auslösen im Chat mit
`/plan <Aufgabe>` (z. B. `/plan Küche putzen und Wäsche waschen`) – der
Server erkennt das Präfix und routet an `plan.request` statt an die normale
`ConversationEngine`. Nutzt Claude zur Zerlegung; ohne `ANTHROPIC_API_KEY`
greift eine einfache Heuristik (Aufzählungs-/Satzgrenzen wie „und", „,",
„dann"). Der aktuelle Plan wird im HUD im „Aufgaben"-Panel angezeigt (echte
Daten statt Mock-Vorschau) – ein Klick auf einen Schritt togglet ihn als
erledigt (`plan.step.complete`). Verwaltet bewusst nur **einen** aktiven Plan
(Alpha 1.1: ein Nutzer, ein Fokus).

**Obsidian-Notiz je Plan:** Jeder Plan wird zusätzlich als Notiz in der
Kategorie „Projekte" gespeichert – Titel = Aufgabe, Inhalt = Checkliste +
Fortschritt (`2/5 Schritte erledigt`, bei Vollständigkeit `Abgeschlossen ✅`).
Die Notiz entsteht bei `plan.request` und wird bei jedem
`plan.step.complete` überschrieben statt dupliziert (MemoryEngine erkennt
denselben Titel/dieselbe Kategorie am Dateipfad und ersetzt den bestehenden
Eintrag). Ersetzt das aktuelle Aufgaben-Panel ein Projekt durch den nächsten
Plan, bleibt die Notiz im Vault trotzdem dauerhaft auffindbar – das ist der
Ort, an dem „bisherige/erledigte Projekte" tatsächlich landen.

Bus-Schnittstelle: `plan.request` (in) `{id, task}` · `plan.step.complete`
(in) `{index}` · `plan.update` (out, state-artig/replayable) `{id, task,
steps: [{index, text, done}], created_at}` · `memory.note` (out) –
Projekt-Notiz bei Erstellung und jedem Toggle.

### ReasoningEngine (real)
Mehrstufige Analyse mit sichtbarer Werkzeug-Auswahl. Auslösen im Chat mit
`/denke <Frage>`. Läuft in drei sichtbaren Schritten:

1. **Werkzeug-Auswahl** – eine deterministische Heuristik (`select_tool`,
   keine zweite LLM-Anfrage) entscheidet anhand von Schlüsselwörtern:
   `memory` (Vault durchsuchen), `system` (aktuelle System-Werte), `plan`
   (Aufgaben-Zerlegung wie `PlanningEngine`) oder `direct` (keine
   Zusatzquelle).
2. **Kontext sammeln** aus der gewählten Quelle – sichtbar im Chat-Verlauf,
   bevor die eigentliche Antwort kommt.
3. **Finale Antwort** über Claude (mit gesammeltem Kontext im System-Prompt)
   oder ein ehrlicher Hinweis ohne API-Key.

Wiederverwendet bewusst `chat.token`/`chat.response` (keine neuen
Frontend-Topics) – das HUD zeigt Reasoning-Ausgaben wie jede normale
APHELIOS-Antwort, nur mit sichtbaren Zwischenschritten davor. Das ist
zugleich der Beweis, dass die Streaming-Pipeline auch für eine zweite,
unabhängige Engine Ende-zu-Ende funktioniert.

### Stub-Engines
Coding, Browser, Knowledge, Vision, Voice, Agent – vollständige Signaturen,
aber noch keine Implementierung (siehe `ROADMAP.md`).

## Engines in Alpha 1.2

### AutomationEngine (real, erste Ausbaustufe)
PowerShell-Ausführung, Datei-Operationen und Programme starten/schließen –
**jede** schreibende/löschende Aktion läuft zwingend über das SecurityGate
(`docs/security.md`), es gibt keinen Pfad ohne ausdrückliche Bestätigung.

Auslösen im Chat (Slash-Befehle, direkt vom Nutzer getippt – nicht von einer
AI-Entscheidung, damit kein Prompt-Injection-Pfad zu echten Systemaktionen
führt):

| Befehl | Aktion | Risiko |
|---|---|---|
| `/run <PowerShell-Befehl>` | `run_powershell` | CONFIRM, bei zerstörerischen Mustern (Registry, Formatierung, Deinstallation, Neustart …) DANGEROUS |
| `/oeffne <Programmname>` | `open_app` | CONFIRM |
| `/schliesse <Programmname>` | `close_app` | CONFIRM |
| `/loesche <Pfad>` | `delete_path` (Datei oder Ordner, automatisch erkannt) | CONFIRM |
| `/downloads` | `downloads` – listet den Downloads-Ordner | nur lesend, kein Gate nötig |

Zusätzlich (bisher nur über den Bus, kein eigener Slash-Befehl):
`list_dir`, `find_files` (beide nur lesend), `create_folder`, `create_file`,
`move_file`.

**Programme per Anzeigename finden (`/oeffne`):** `os.startfile(name)`
allein findet nur Namen, die über PATH oder die "App Paths"-Registry
auflösbar sind (z. B. `notepad`) – die meisten installierten Apps wie
Obsidian liegen dort nicht. `find_app_path()` durchsucht deshalb zuerst das
Windows-Startmenü (eigenes Konto + alle Nutzer) und den Desktop (eigenes
Konto + öffentlich) nach einer passenden `.lnk`/`.exe`-Datei – derselbe Ort,
den auch das native Windows-Startmenü beim Tippen durchsucht. Exakter
Treffer gewinnt, sonst der spezifischste Teilstring-Treffer. Wird etwas
gefunden, zeigt der Bestätigungsdialog den **aufgelösten Pfad**, nicht nur
den eingetippten Namen (Transparenz-Prinzip aus `docs/security.md`). Kein
Treffer → Fallback auf den rohen Namen (funktioniert weiter für PATH-Namen).
Schlägt der Start trotzdem fehl, schlägt `find_similar_app_names()`
ähnliche gefundene Namen vor ("Meintest du: Obsidian?").

APHELIOS zielt auf Windows (siehe README) – auf anderen Plattformen (z. B.
in dieser Entwicklungsumgebung) geben PowerShell-Ausführung und
Programm-Start einen ehrlichen „nicht unterstützt"-Hinweis zurück statt zu
crashen, dasselbe Muster wie GPU/Temperatur in der SystemEngine.

**Obsidian-Protokoll:** Jede zustandsändernde Aktion, die tatsächlich
ausgeführt wurde (bestätigt UND erfolgreich – nicht bei Ablehnung oder
Fehlschlag), schreibt zusätzlich eine Notiz in der Kategorie „Protokolle":
PowerShell-Befehl + Ausgabe, gestartetes/geschlossenes Programm, erstellter/
verschobener/gelöschter Pfad. So bleibt nachvollziehbar, was APHELIOS am
System verändert hat, ohne den Chat-Verlauf durchsuchen zu müssen. Rein
lesende Aktionen (`list_dir`, `find_files`, `downloads`) erzeugen bewusst
keine Notiz – das wäre reines Rauschen statt nützlicher Historie.

**Bewusst NICHT in dieser ersten Ausbaustufe:**

- **Programme installieren/deinstallieren** – der Mechanismus (winget? eine
  feste Allowlist? beliebige Installer-Pfade?) ist eine echte
  Sicherheitsabwägung, keine rein technische Entscheidung. Braucht erst eine
  bewusste Entscheidung des Nutzers, genau wie WhatsApp in
  `docs/integrations.md`.
- **pywinauto-Fensterinteraktion** – erfordert eine echte, laufende
  Windows-Desktop-Sitzung zum Testen (UI Automation), die in dieser
  Entwicklungsumgebung (Linux, ohne Display) grundsätzlich nicht verfügbar
  ist. Blind implementieren, ohne es je laufen zu sehen, wäre unseriös.

**Wichtiger Architektur-Fix in diesem Zug:** Der WebSocket-Endpunkt
verarbeitete eingehende Nachrichten bisher sequenziell (`await` statt Task).
Eine Engine, die über das SecurityGate auf eine Bestätigung wartet, wartet
damit auf die *nächste* Nachricht auf genau derselben Verbindung – die
Bestätigung des Nutzers. Da die Verbindung aber noch mit der vorherigen
Nachricht "beschäftigt" war, konnte diese Bestätigung nie ankommen
(Deadlock, endete nach 120 s in einem automatischen Deny). Jetzt wird jede
eingehende Nachricht als eigener Task eingeplant, siehe
`backend/tests/test_ws_integration.py` für den Regressionstest.

## Engines in Alpha 1.3

### VoiceEngine (real, optional)
Lokale Sprachein-/ausgabe – Details, Einrichtung und Bus-Schnittstelle in
[`docs/voice.md`](./voice.md). Kurzfassung:

- **TTS** (`voice.speak`): [Piper](https://github.com/rhasspy/piper) erzeugt
  eine natürliche, tiefe Stimme lokal (kein API-Key). Ohne konfiguriertes
  Modell (`APHELIOS_PIPER_MODEL_PATH`) bleibt sie inaktiv – das Frontend
  fällt automatisch auf die Browser-Stimme zurück.
- **STT** (`voice.transcribe`): [faster-whisper](
  https://github.com/SYSTRAN/faster-whisper) transkribiert Audio lokal,
  Modell wird beim ersten Gebrauch automatisch heruntergeladen.
- Beide Modelle werden lazy geladen (erst bei der ersten Anfrage).
- `voice.transcribe` ist an eine Push-to-Talk-Oberfläche im Frontend
  angebunden – aktiv als automatischer Fallback in Browsern ohne
  `SpeechRecognition` (Firefox/Waterfox); die Wake-Word-Erkennung in
  Chromium (Chrome/Edge) nutzt weiterhin die Web Speech API. Details in
  `docs/voice.md`.

## Engines in Alpha 1.4

### VisionEngine (real, erste Ausbaustufe)
Bildschirm-Verständnis über drei Slash-Befehle – Details, Einrichtung und
Bus-Schnittstelle in [`docs/vision.md`](./vision.md). Kurzfassung:

- `/sieh <Frage>` – Screenshot (via `mss`) + Claude Vision beschreibt den
  Bildschirm bzw. beantwortet die Frage; ohne `ANTHROPIC_API_KEY` Fallback
  auf reinen OCR-Text (Tesseract), keine echte Interpretation.
- `/lies` – nur den sichtbaren Text extrahieren, rein lokal (Tesseract OCR,
  kein API-Key nötig).
- `/fehler` – sucht per Regex-Heuristik nach einer sichtbaren Fehlermeldung;
  gefunden und ein API-Key vorhanden, erklärt Claude sie.
- **Jede** Aktion läuft über das SecurityGate (CONFIRM) – ein Screenshot
  kann beliebig sensible Inhalte zeigen, unabhängig davon, ob er lokal
  bleibt oder an Claude geschickt wird.
- Screenshot und OCR laufen jeweils in einem Thread, damit eine langsame
  Tesseract-Erkennung den Event-Loop nicht blockiert.
- **Bewusst NICHT in dieser ersten Ausbaustufe:** Fenster-/Button-/
  Icon-Erkennung (OpenCV) – bräuchte entweder kuratierte Referenz-Templates
  oder ein trainiertes Modell, während `/sieh` denselben praktischen
  Anwendungsfall über Claude Vision bereits abdeckt. Ebenso kein
  dediziertes Tabellen-/Diagramm-Parsing (deckt Claude Vision nativ mit ab)
  und kein automatisches/proaktives Hintergrund-Monitoring (nur On-Demand).

## Engines in Alpha 1.5

### MemoryEngine – Vektorsuche (erweitert)
`memory.search` durchsucht den Vault jetzt in zwei Stufen statt nur per
SQL-`LIKE`:

1. **Semantische Suche über [ChromaDB](https://www.trychroma.com/)** – lokale
   Embeddings (Standard-Modell `all-MiniLM-L6-v2`, kein API-Key nötig; wird
   beim ersten Gebrauch automatisch heruntergeladen und lokal
   zwischengespeichert, `pip install -e ".[vector]"`). Jede gespeicherte
   Notiz wird zusätzlich zum SQLite-Eintrag in eine Chroma-Kollektion
   upserted (Notiz-Pfad als ID, Update statt Duplikat wie beim SQL-Index).
   Treffer über einer kalibrierten Distanz-Schwelle (`_MAX_SEMANTIC_DISTANCE`)
   werden verworfen – sonst käme bei nur wenigen Notizen im Vault selbst eine
   thematisch völlig fremde Anfrage als „Treffer" zurück (ChromaDB liefert
   immer die *nächsten* Nachbarn, unabhängig von der tatsächlichen Ähnlichkeit).
2. **SQL-Volltextsuche (Fallback)** – greift, wenn ChromaDB fehlt/nicht
   erreichbar ist, ODER wenn die Vektorsuche zwar lief, aber (nach dem
   Distanz-Filter) nichts Relevantes fand. Letzteres ist der häufigere Fall
   in der Praxis: kurze Rückfragen wie „Was war nochmal mein Plan?" teilen
   mit dem kleinen Embedding-Modell oft kaum Bedeutung mit der gemeinten
   Notiz, ein einzelnes Schlüsselwort daraus („Plan", z. B. als Tag gesetzt)
   findet sie trotzdem. Die Volltextsuche zerlegt die Anfrage dafür in
   einzelne Wörter (kurze Füll-/Fragewörter wie „was"/"mein"/"ist" werden
   verworfen) und sucht jedes davon in Titel, Inhalt UND Tags – nicht mehr
   die komplette Anfrage als einen einzigen Text-Block wie zuvor.

Kein installiertes ChromaDB oder ein fehlgeschlagener Modell-Download (kein
Internet, Firmen-Firewall) führt zu keinem Fehler – die Suche fällt einfach
automatisch auf reine Volltextsuche zurück, Aufrufer bemerken nur die
Trefferqualität, keinen Unterschied im Verhalten.

**Proaktives Wiederfinden:** Jeder Treffer (aus beiden Suchwegen) trägt
zusätzlich ein `age`-Feld ("heute", "vor 3 Wochen", "vor 2 Jahren" …) – macht
aus einem anonymen Suchtreffer sichtbar „das hattest du schon mal notiert".
Genutzt von `ConversationEngine._memory_context()`, `ReasoningEngine`
(Werkzeug „memory") und `KnowledgeEngine` (siehe unten).

### KnowledgeEngine (real)
Ausgelöst über `/wissen <Frage>`. Klassisches RAG (Retrieval-Augmented
Generation) ausschließlich über den eigenen Obsidian-Vault:

1. Fragt `memory.search` ab und zeigt die gefundenen Notizen sichtbar im
   Chat (Titel + Alter).
2. Ohne Treffer: ehrliche Absage statt einer erfundenen Antwort
   ("Dazu finde ich nichts im Vault …").
3. Mit Treffern, aber ohne `ANTHROPIC_API_KEY`: nur die Fundliste, keine
   Synthese – dasselbe Fallback-Prinzip wie bei Planning-/ReasoningEngine.
4. Mit Treffern und API-Key: lädt die **vollen Notiz-Texte von der Platte**
   (der Suchindex liefert bewusst nur Metadaten) und lässt Claude
   **ausschließlich** auf dieser Basis antworten, mit Quellenangabe.

Unterscheidet sich bewusst von den beiden bestehenden Vault-Nutzern:
`ConversationEngine` reicht Treffer nur als kurzen Kontext-Hinweis in den
System-Prompt (Hintergrundwissen, keine gezielte Anfrage);
`ReasoningEngine` wählt den Vault nur als eine von mehreren möglichen
Quellen. `KnowledgeEngine` durchsucht **immer** gezielt den Vault und
antwortet **ausschließlich** daraus – für den Fall „was habe ich mir dazu
notiert?" statt beiläufigem Kontext.

## Engines in Alpha 1.6 (erste Ausbaustufe: BrowserEngine, Werkzeug-Nutzung)

Alpha 1.6 „Developer & Office" umfasst laut `ROADMAP.md` vier Bausteine
(CodingEngine, BrowserEngine, Office-Integration, VS-Code-Integration) – hier
zunächst die **BrowserEngine**, die übrigen drei bleiben vorerst Stubs.
Zusätzlich kann Claude jetzt selbst über Claudes **Tool-Use-API** entscheiden,
ob eine normale Chat-Nachricht ein Werkzeug braucht (siehe unten).

### ConversationEngine – Werkzeug-Nutzung (erweitert)
Bisher lösten Werkzeuge NUR explizite Slash-Befehle aus (`/wissen`, `/oeffne`
…, serverseitig per Text-Präfix erkannt, siehe `_SLASH_COMMANDS` in
`server.py`). Jetzt kann Claude über die offizielle
[Tool-Use-API](https://docs.claude.com/en/docs/agents-and-tools/tool-use/overview)
selbst entscheiden, ob eine ganz normal formulierte Nachricht ein Werkzeug
braucht – "öffne mal Spotify" löst dieselbe `automation.request` aus wie
`/oeffne Spotify`, ganz ohne dass der Nutzer den Befehl kennen muss.

- `_TOOLS` (in `conversation_engine.py`) deklariert ein Werkzeug pro
  bestehender Fähigkeit: `search_vault` (→ KnowledgeEngine), `create_plan`
  (→ PlanningEngine), `run_powershell`/`open_app`/`close_app`/`delete_path`/
  `list_downloads` (→ AutomationEngine), `analyze_screen`/`read_screen_text`/
  `find_screen_error` (→ VisionEngine), `browse_page` (→ BrowserEngine).
- Entscheidet sich Claude für ein Werkzeug (`stop_reason == "tool_use"`),
  übersetzt `_tool_call_to_event()` den Aufruf 1:1 in dasselbe
  Topic/Datenformat, das auch der passende Slash-Befehl erzeugen würde –
  **dieselbe** Ziel-Engine übernimmt danach komplett (eigene
  SecurityGate-Bestätigung, eigenes Streaming, eigenes `chat.response`).
  Kein Duplikat der Ausführungslogik.
- Bei riskanten Aktionen (`run_powershell`, `open_app`, `close_app`,
  `delete_path`) bleibt die Bestätigung über das SecurityGate **Pflicht** –
  daran ändert die Werkzeug-Auswahl durch die KI nichts; es ist derselbe
  Bestätigungsdialog, den auch ein Slash-Befehl auslösen würde.
- Streamt Claude ausnahmsweise Text VOR dem Werkzeug-Aufruf (der System-Prompt
  weist an, das zu vermeiden), wird dieser Text als eigene, abgeschlossene
  Antwort behandelt und der Werkzeug-Aufruf bekommt eine neue Nachrichten-ID
  – sonst könnte das spätere `chat.token` der Ziel-Engine an eine bereits
  abgeschlossene Sprechblase angehängt werden oder mit ihr kollidieren.
- **Bewusst NICHT als Werkzeug:** `/denke` (ReasoningEngine) – dessen Sinn
  ist die für den Nutzer sichtbare, explizit angeforderte Analyse mit
  Zwischenschritten; als von Claude selbst gewähltes Werkzeug würde es nur
  an ein zweites Modell delegieren, ohne die Zwischenschritte zu zeigen.
- **Bewusst NICHT in dieser ersten Ausbaustufe:** Werkzeug-Aufrufe landen
  nicht im persistenten Gesprächsverlauf (`_remember_turn`) – das
  tatsächliche Ergebnis entsteht asynchron in einer anderen Engine und ist
  von der ConversationEngine aus nicht ohne Weiteres einzusammeln. Ein
  Folge-„und, hat's geklappt?" hat dadurch keinen Kontext zur vorherigen
  Aktion.
- Nur ein Werkzeug pro Nachricht (der erste `tool_use`-Block einer Antwort) –
  parallele Mehrfach-Aufrufe unterstützt diese erste Ausbaustufe nicht.

### BrowserEngine (real, erste Ausbaustufe)
Liest Webseiten über einen echten, Playwright-gesteuerten Chromium – Details,
Einrichtung und Bus-Schnittstelle in [`docs/browser.md`](./browser.md).
Kurzfassung:

- `/browse <URL> [Frage]` – öffnet die Seite, extrahiert Titel + sichtbaren
  Text; mit `ANTHROPIC_API_KEY` beantwortet Claude die Frage (bzw. fasst
  zusammen) ausschließlich anhand dieses Inhalts, ohne Key gibt es nur den
  rohen Seitentext.
- Fehlt im ersten Wort der Anfrage eine erkennbare URL (Heuristik: enthält
  einen Punkt, keine Leerzeichen), kommt eine klare Fehlermeldung statt
  eines Rateversuchs – APHELIOS sucht nicht selbstständig im Web.
- **Jede** Anfrage läuft über das SecurityGate (CONFIRM) – APHELIOS öffnet
  dabei eine beliebige externe Seite und lädt deren Inhalt im Namen des
  Nutzers.
- Läuft nativ asynchron über Playwrights `async_api` (kein
  `asyncio.to_thread` nötig, anders als bei den synchronen mss/pytesseract-
  Aufrufen der `VisionEngine`).
- Standardmäßig headless (unsichtbar); `APHELIOS_BROWSER_HEADLESS=false`
  zeigt ein echtes Browser-Fenster auf dem Desktop (JARVIS-Effekt).
- **Bewusst NICHT in dieser ersten Ausbaustufe:** Interaktion (Klicken,
  Formulare, Login-Flows) – nur lesend, siehe `docs/browser.md` für die
  Sicherheitsabwägung. Ebenso keine Websuche (Nutzer muss eine konkrete URL
  angeben) und keine Cookie-/Session-Persistenz zwischen Aufrufen.
