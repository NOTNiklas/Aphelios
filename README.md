<div align="center">

# ⬡ APHELIOS

### Ein J.A.R.V.I.S.-inspirierter Desktop-AI-Betriebssystem-Assistent

**Version:** Alpha 1.0 · **Status:** MVP-Grundgerüst · **Ziel-Plattform:** Windows (Desktop via Tauri)

`Kein Chatbot. Ein zweites Gehirn.`

</div>

---

APHELIOS ist kein weiteres Chat-Fenster, sondern ein modularer, ereignisgesteuerter
AI-Assistent, der langfristig den kompletten PC verwaltet – mit einem holografischen
Iron-Man-HUD, mehreren unabhängigen AI-Engines, einem Obsidian-basierten Langzeitgedächtnis,
Sprachaktivierung und Automatisierung.

Dieses Repository enthält das **Alpha-1.0-Grundgerüst**: eine saubere, dokumentierte
Architektur plus einen **lauffähigen MVP** (HUD-Oberfläche, echte System-Statistiken,
AI-Konsole, Sprachaktivierungs-Grundlage). Alle weiteren Module (Vision, Automation,
Browser, Office, Smart Home …) sind als Schnittstellen vorbereitet und lassen sich
später einfach ergänzen.

> Der vollständige Funktionsumfang aus der Vision ist ein **Langzeitziel**. Was in
> Alpha 1.0 bereits real funktioniert und was noch Stub ist, steht in [`ROADMAP.md`](./ROADMAP.md).

---

## ✦ Was in Alpha 1.0 funktioniert

| Bereich | Status | Beschreibung |
|---|---|---|
| **HUD-Oberfläche** | ✅ Real | Rotierender Core, System-Gauges, Info-Panels, animierte AI-Konsole |
| **System-Monitoring** | ✅ Real | CPU / RAM / Disk / Netzwerk / Temperatur / Akku via `psutil` |
| **AI-Konsole** | ✅ Real | Konversation über Claude API (mit Fallback ohne API-Key) |
| **Memory / Second Brain** | ✅ Real | Schreibt Obsidian-Markdown mit Tags & Backlinks + SQLite-Index |
| **Sprachaktivierung** | ✅ Basis | Wake-Word „Aphelios" via Web Speech API (Browser) |
| **Event-Bus & Engine-Manager** | ✅ Real | Ereignisgesteuerte Kommunikation zwischen unabhängigen Engines |
| **Plugin-System** | ✅ Gerüst | Ordner-basierter Loader + Manifest-Schema |
| **Security-Gate** | ✅ Real | Gefährliche Aktionen erfordern Bestätigung |
| **Vision / Automation / Browser …** | 🔌 Stub | Schnittstellen vorbereitet, Implementierung folgt (siehe Roadmap) |

---

## ✦ Architektur auf einen Blick

```
┌──────────────────────────────────────────────────────────────┐
│                     FRONTEND  (HUD)                            │
│   React · TypeScript · Tailwind · Framer Motion · Vite         │
│   → optional als Windows-Desktop-App via Tauri-Shell           │
└───────────────▲───────────────────────────┬──────────────────┘
                │  WebSocket (/ws)           │  Chat (/chat)
                │  System-Stats & Events     │
┌───────────────┴───────────────────────────▼──────────────────┐
│                     BACKEND  (Python)                          │
│                                                                │
│   FastAPI + WebSocket  ◀──▶  EventBus  ◀──▶  EngineManager     │
│                                                │               │
│   ┌────────────┬──────────────┬───────────────┴────────────┐  │
│   │ System     │ Conversation │ Memory  │ Voice · Vision …  │  │
│   │ (psutil)   │ (Claude API) │(Obsidian)│  (Stubs)         │  │
│   └────────────┴──────────────┴───────────────────────────-┘  │
│                                                                │
│   SecurityGate  ·  PluginLoader  ·  Config                     │
└────────────────────────────────────────────────────────────---┘
```

Details in [`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## ✦ Schnellstart

### Voraussetzungen
- **Python** ≥ 3.10
- **Node.js** ≥ 18
- (Optional, für Desktop-Build) **Rust** + Tauri-Prerequisites auf Windows

### 1 · Backend starten

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
cp ../.env.example ../.env        # optional: ANTHROPIC_API_KEY eintragen
python -m aphelios
```

Das Backend läuft nun auf `http://127.0.0.1:8787`
(Health-Check: `curl http://127.0.0.1:8787/health`).

### 2 · Frontend starten

```bash
cd frontend
npm install
npm run dev
```

Öffne `http://localhost:5173` – das HUD verbindet sich automatisch mit dem Backend.
**Ohne laufendes Backend** zeigt das HUD realistische Mock-Daten an, ist also
eigenständig lauffähig.

### 3 · (Optional) Desktop-App auf Windows

```bash
cd frontend
npm run tauri build      # erzeugt eine native Windows-App
```

> Der Tauri-Build wird auf einem Windows-System durchgeführt. Siehe
> [`docs/design-system.md`](./docs/design-system.md) und die Tauri-Doku.

---

## ✦ Projektstruktur

```
aphelios/
├── frontend/          # HUD (React/TS/Tailwind/Framer Motion) + Tauri-Shell
├── backend/           # Python: Event-Bus, Engines, Plugin-Loader, API
├── plugins/           # Plugin-Kategorien (Manifest + README je Kategorie)
├── docs/              # Detail-Dokumentation je Teilsystem
├── ARCHITECTURE.md    # Systemarchitektur
├── ROADMAP.md         # Vollständige Vision → Meilensteine
└── README.md
```

---

## ✦ Persönlichkeit

APHELIOS spricht **ruhig, intelligent, präzise** und lösungsorientiert – mit dezentem,
trockenem Humor, wenn es passt. Niemals aufdringlich, niemals übertrieben. Er kennt deine
Projekte, merkt sich deine Arbeitsweise und schlägt proaktiv Optimierungen vor.

---

## ✦ Sicherheit

Gefährliche Aktionen (Dateien löschen, Registry ändern, Programme deinstallieren,
Systemdateien ändern, Passwörter anzeigen) werden vom **SecurityGate** abgefangen und
**erfordern immer eine ausdrückliche Bestätigung**. Details in
[`docs/security.md`](./docs/security.md).

---

<div align="center">
<sub>APHELIOS · Alpha 1.0 · „Oh ja, das hatten wir schon einmal."</sub>
</div>
