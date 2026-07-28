<div align="center">

# ⬡ APHELIOS

### Ein J.A.R.V.I.S.-inspirierter Desktop-AI-Betriebssystem-Assistent

**Version:** Alpha 1.3 · **Status:** Voice (Piper-TTS + Whisper-STT) · **Ziel-Plattform:** Windows (Desktop via Tauri)

`Kein Chatbot. Ein zweites Gehirn.`

</div>

---

APHELIOS ist kein weiteres Chat-Fenster, sondern ein modularer, ereignisgesteuerter
AI-Assistent, der langfristig den kompletten PC verwaltet – mit einem holografischen
Iron-Man-HUD, mehreren unabhängigen AI-Engines, einem Obsidian-basierten Langzeitgedächtnis,
Sprachaktivierung und Automatisierung.

Dieses Repository enthält das **Alpha-1.3-Grundgerüst**: eine saubere, dokumentierte
Architektur plus einen **lauffähigen MVP** (HUD-Oberfläche, echte System-Statistiken,
AI-Konsole mit persistentem Gedächtnis, Reasoning & Planning, Windows-Automation,
lokale Sprachausgabe/-erkennung). Alle weiteren Module (Vision, Browser, Office,
Smart Home …) sind als Schnittstellen vorbereitet und lassen sich später einfach
ergänzen.

> Der vollständige Funktionsumfang aus der Vision ist ein **Langzeitziel**. Was
> bereits real funktioniert und was noch Stub ist, steht in [`ROADMAP.md`](./ROADMAP.md).

**Slash-Befehle in der Chat-Konsole** (direkt im normalen Eingabefeld, keine
separate UI nötig):

| Befehl | Wirkung |
|---|---|
| `/plan <Aufgabe>` | Zerlegt eine Aufgabe in Schritte – echt im „Aufgaben"-Panel, abhakbar |
| `/denke <Frage>` | Zeigt APHELIOS' Analyse sichtbar (Werkzeug-Wahl → Kontext → Antwort) |
| `/run <PowerShell-Befehl>` | Führt einen Befehl aus – **immer mit Bestätigungsdialog** |
| `/oeffne <Programm>` / `/schliesse <Programm>` | Startet/beendet ein Programm – mit Bestätigung |
| `/loesche <Pfad>` | Löscht eine Datei/einen Ordner – mit Bestätigung |
| `/downloads` | Listet den Downloads-Ordner (nur lesend) |

Details in [`docs/engines.md`](./docs/engines.md).

---

## ✦ Was funktioniert

| Bereich | Status | Beschreibung |
|---|---|---|
| **HUD-Oberfläche** | ✅ Real | Rotierender Core, System-Gauges, Info-Panels, animierte AI-Konsole |
| **System-Monitoring** | ✅ Real | CPU / RAM / Disk / Netzwerk / Temperatur / Akku via `psutil` |
| **AI-Konsole** | ✅ Real | Konversation über Claude API (mit Fallback ohne API-Key), persistenter Kontext |
| **Reasoning** | ✅ Real (Alpha 1.1) | Mehrstufige Analyse mit sichtbarer Werkzeug-Auswahl – `/denke <Frage>` im Chat |
| **Planning** | ✅ Real (Alpha 1.1) | Aufgabe → Schritte, echtes Aufgaben-Panel – `/plan <Aufgabe>` im Chat |
| **Automation** | ✅ Real (Alpha 1.2, Windows) | PowerShell, Datei-Operationen, Programme starten/schließen – immer mit Bestätigung |
| **Memory / Second Brain** | ✅ Real | Schreibt Obsidian-Markdown mit Tags & Backlinks + SQLite-Index; Automation & Planning protokollieren ihre Aktionen/Projekte automatisch |
| **Sprachaktivierung** | ✅ Real | Wake-Word „Aphelios" + Dauer-Zuhören (Web Speech API, Browser) |
| **Sprachausgabe (TTS)** | ✅ Real, optional (Alpha 1.3) | Piper – natürliche, tiefe Stimme lokal, kein API-Key; Fallback auf Browser-Stimme – [`docs/voice.md`](./docs/voice.md) |
| **Spracherkennung (STT)** | 🟡 Backend fertig (Alpha 1.3) | faster-whisper lokal, noch nicht ans Frontend angebunden (Push-to-Talk fehlt) – [`docs/voice.md`](./docs/voice.md) |
| **Wetter** | ✅ Real | Open-Meteo, kein API-Key nötig |
| **Gmail / Kalender** | ✅ Real, optional | Eigener Google-OAuth-Client nötig, siehe [`docs/integrations.md`](./docs/integrations.md) |
| **Handy-Zugriff** | ✅ Real (PWA) | HUD als App installierbar, gleiches WLAN – [`docs/integrations.md`](./docs/integrations.md) |
| **Event-Bus & Engine-Manager** | ✅ Real | Ereignisgesteuerte Kommunikation zwischen unabhängigen Engines |
| **Plugin-System** | ✅ Gerüst | Ordner-basierter Loader + Manifest-Schema |
| **Security-Gate** | ✅ Real | Gefährliche Aktionen erfordern Bestätigung |
| **WhatsApp** | 📄 Nur dokumentiert | Bewusst kein Code – Abwägung in [`docs/integrations.md`](./docs/integrations.md) |
| **Vision / Browser / Coding …** | 🔌 Stub | Schnittstellen vorbereitet, Implementierung folgt (siehe Roadmap) |

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
│   ┌──────────┬────────────┬────────┬──────────┬─────────────┐ │
│   │ System   │Conversation│ Memory │ Weather  │ Mail/Kalender│ │
│   │ (psutil) │(Claude API)│(Obsidian)│(Open-Meteo)│ (Google, opt.)│
│   └──────────┴────────────┴────────┴──────────┴─────────────┘ │
│              Vision · Automation · Browser · … (Stubs)         │
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

### 4 · (Optional) Gmail, Kalender & Handy-Zugriff

Für echte Mail-/Kalender-Daten und um APHELIOS auf dem Handy zu installieren,
siehe die Schritt-für-Schritt-Anleitung: [`docs/integrations.md`](./docs/integrations.md).

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
<sub>APHELIOS · Alpha 1.3 · „Oh ja, das hatten wir schon einmal."</sub>
</div>
