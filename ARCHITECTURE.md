# APHELIOS – Systemarchitektur

Dieses Dokument beschreibt, wie APHELIOS intern aufgebaut ist. Leitprinzipien:

1. **Ereignisgesteuert** – Engines kommunizieren ausschließlich über einen Event-Bus,
   niemals durch direkte Aufrufe. Das entkoppelt Module vollständig.
2. **Modular** – Jede Engine ist unabhängig, läuft in ihrem eigenen asyncio-Task und
   kann einzeln gestartet/gestoppt werden.
3. **Plugin-basiert** – Neue Fähigkeiten werden als Plugins in Kategorie-Ordnern ergänzt
   und automatisch entdeckt.
4. **Sicher per Voreinstellung** – Gefährliche Aktionen laufen zwingend über das
   SecurityGate und erfordern Bestätigung.

---

## 1 · Überblick

```
Frontend (HUD)  ──WebSocket──►  API-Server (FastAPI)
                ◄─Events───────       │
                                      │ publish/subscribe
                                      ▼
                                  EventBus
                                      ▲
                     ┌────────────────┼────────────────┐
                     │                │                │
                EngineManager    SecurityGate     PluginLoader
                     │
        ┌────────────┼─────────────┬───────────────┐
        ▼            ▼             ▼               ▼
   SystemEngine  Conversation   Memory      Voice, Vision,
   (psutil)      Engine         Engine      Automation … (Rest: Stubs)
```

---

## 2 · Kernkomponenten (`backend/aphelios/core/`)

### EventBus (`event_bus.py`)
Ein asynchrones Publish/Subscribe-System. Herzstück der Kommunikation.

- `subscribe(topic, callback)` – registriert einen (async) Handler für ein Topic.
  Topics unterstützen Wildcards (`system.*`, `*`).
- `await publish(Event)` – verteilt ein Event an alle passenden Subscriber.
- Ein `Event` hat `topic: str`, `data: dict` und `source: str`.

Beispiel-Topics: `system.stats`, `chat.request`, `chat.response`, `chat.token`,
`confirmation.request`, `confirmation.approve`, `memory.note`.

### BaseEngine (`engine.py`)
Abstrakte Basisklasse für alle Engines.

```python
class BaseEngine(ABC):
    name: str
    async def start(self) -> None: ...   # Ressourcen aufbauen, Loops starten
    async def stop(self)  -> None: ...   # sauber herunterfahren
    async def handle(self, event: Event) -> None: ...   # Event verarbeiten
```

Jede Engine bekommt beim Erstellen den EventBus injiziert und abonniert dort ihre Topics.

### EngineManager (`manager.py`)
Registriert Engines, startet/stoppt alle gemeinsam und überwacht ihre Tasks.

### Config (`config.py`)
Lädt Einstellungen aus Umgebungsvariablen / `.env` (Provider, API-Keys, Vault-Pfad,
Poll-Intervall, Modell-ID, API-Host/Port). Siehe `.env.example`. Relative
Pfade (Vault, SQLite-Index, Google-Token, Piper-Modell) werden fest gegen
`BACKEND_ROOT` (den `backend`-Ordner) verankert statt gegen das aktuelle
Arbeitsverzeichnis – das Backend lässt sich auf mehrere Arten starten
(Terminal, `run.bat`, IDE-Run-Konfiguration, …), jede mit potenziell anderem
cwd. Absolute Pfade bleiben davon unberührt.

### SecurityGate (`security.py`)
Klassifiziert Aktionen und blockiert gefährliche, bis eine Bestätigung vorliegt.
Details in [`docs/security.md`](./docs/security.md).

---

## 3 · Engines (`backend/aphelios/engines/`)

| Engine | Stand | Aufgabe |
|---|---|---|
| **SystemEngine** | ✅ real | System-Telemetrie via `psutil`, publisht `system.stats` |
| **ConversationEngine** | ✅ real | Dialog über Claude API (+ Fallback), persistenter Kontext über MemoryEngine |
| **MemoryEngine** | ✅ real (Vektorsuche seit Alpha 1.5) | Obsidian-Vault-Notizen mit automatischer Verlinkung; semantische Suche über ChromaDB mit automatischem Volltext-Fallback (Titel/Inhalt/Tags) + generischer KV-Store |
| **WeatherEngine** | ✅ real | Echtes Wetter via Open-Meteo (kein API-Key) |
| **MailEngine** | ✅ real, optional | Gmail lesen + senden (Alpha 1.7, `/mail-senden`), eigener Google-OAuth-Client nötig |
| **CalendarEngine** | ✅ real, optional | Google-Kalender-Termine lesen + anlegen (Alpha 1.7, `/termin-anlegen`), dieselbe Anmeldung |
| **ReasoningEngine** | ✅ real (Alpha 1.1) | Mehrstufige Analyse + sichtbare Werkzeug-Auswahl (`/denke`) |
| **PlanningEngine** | ✅ real (Alpha 1.1) | Aufgabe → Schritte, echtes Aufgaben-Panel (`/plan`) |
| **AutomationEngine** | ✅ real, erste Ausbaustufe (Alpha 1.2) | PowerShell, Datei-Operationen, Programme starten/schließen – alles über SecurityGate (`/run`, `/oeffne`, `/schliesse`, `/loesche`, `/downloads`) |
| **VoiceEngine** | ✅ real, optional (Alpha 1.3) | Piper-TTS + faster-whisper-STT lokal, `voice.speak`/`voice.transcribe` |
| **VisionEngine** | ✅ real, erste Ausbaustufe (Alpha 1.4) | Screenshot + OCR + Claude Vision, alles über SecurityGate (`/sieh`, `/lies`, `/fehler`) |
| **KnowledgeEngine** | ✅ real (Alpha 1.5) | RAG ausschließlich über den Obsidian-Vault, mit Quellenangabe (`/wissen`) |
| **BrowserEngine** | ✅ real, erste Ausbaustufe (Alpha 1.6) | Playwright-gesteuertes Lesen von Webseiten, über SecurityGate (`/browse`) |
| **CodingEngine** | ✅ real, erste Ausbaustufe (Alpha 1.6) | Code schreiben/erklären über Claude, nur im Chat (`/code`) |
| **OfficeEngine** | ✅ real, erste Ausbaustufe (Alpha 1.6) | Word/Excel/PowerPoint/PDF lesen, über SecurityGate (`/dokument`) |
| AgentEngine | 🔌 stub | mehrere parallele AI-Agenten |

Alle Stubs erben von `BaseEngine`, besitzen die vollständige Methoden-Signatur und
`TODO`-Hinweise – neue Funktionalität ist damit „drop-in".

---

## 4 · Plugin-System (`backend/aphelios/plugins/`)

- `base.py` – `Plugin`-Basisklasse + Manifest-Schema
  (`name`, `version`, `category`, `entrypoint`, `permissions`).
- `loader.py` – durchsucht `/plugins/<Kategorie>/`, validiert Manifeste, registriert Plugins.
- Kategorie-Ordner unter `/plugins/` entsprechen der Vision (Core, Voice, Memory, Browser,
  Windows, Developer, Office, AI, Automation, Security, Vision, Music, Calendar, Mail,
  HomeDesk, SmartHome).

Details in [`docs/plugins.md`](./docs/plugins.md).

---

## 5 · API-Server (`backend/aphelios/api/server.py`)

FastAPI-Anwendung, die das HUD mit dem Kern verbindet:

| Route | Typ | Zweck |
|---|---|---|
| `GET /health` | HTTP | Health-Check + Engine-Status |
| `WS /ws` | WebSocket | Live-Stream von `system.stats` & Engine-Events an das HUD |
| `POST /chat` | HTTP | Einzelne Chat-Anfrage → Antwort (nicht-streamend) |

Über den WebSocket kann das HUD auch Chat-Nachrichten senden (`{"type":"chat", ...}`)
und erhält Antwort-Token gestreamt zurück (`chat.token` → `chat.response`).

---

## 6 · Frontend (`frontend/`)

- **State**: Ein Zustand-Store hält die Live-Daten (Stats, Konsolen-Verlauf, Engine-Status).
- **Transport**: `lib/ws.ts` verbindet sich mit `/ws` (mit Auto-Reconnect). Fällt die
  Verbindung aus, speist `lib/mock.ts` realistische Mock-Daten ein – das HUD bleibt lauffähig.
- **HUD-Primitive** (`src/hud/`): wiederverwendbare Bausteine (Core, Ring, Gauge, Panel,
  ScanLines, Particles, Grid).
- **Panels** (`src/panels/`): SystemStats (links), InfoPanels (rechts), Console (unten).
- **Voice** (`src/voice/`): Wake-Word-Erkennung „Aphelios" via Web Speech API.

Details in [`docs/design-system.md`](./docs/design-system.md).

---

## 7 · Datenfluss (Beispiel: „Wie ist die CPU-Auslastung?")

```
Nutzer spricht/tippt  ─►  Console  ─►  WS {type:chat}  ─►  API-Server
   ─►  EventBus.publish("chat.request")  ─►  ConversationEngine
   ─►  (nutzt system.stats aus dem Kontext)  ─►  Antwort-Token
   ─►  EventBus.publish("chat.token"…)  ─►  API-Server  ─►  WS  ─►  Console (animiert)
```

Parallel läuft die SystemEngine im Hintergrund und publisht alle N Sekunden
`system.stats`, das der API-Server an alle verbundenen HUDs streamt.
