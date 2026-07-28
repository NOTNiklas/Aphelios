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
ohne manuelles Verlinken.

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

Bus-Schnittstelle: `plan.request` (in) `{id, task}` · `plan.step.complete`
(in) `{index}` · `plan.update` (out, state-artig/replayable) `{id, task,
steps: [{index, text, done}], created_at}`.

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
