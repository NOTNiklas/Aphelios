<div align="center">

# ⬡ APHELIOS

### Ein J.A.R.V.I.S.-inspirierter Desktop-AI-Betriebssystem-Assistent

**Version:** Alpha 1.5 · **Status:** Second Brain (Vektorsuche, RAG, proaktives Wiederfinden) · **Ziel-Plattform:** Windows (Desktop via Tauri)

`Kein Chatbot. Ein zweites Gehirn.`

</div>

---

APHELIOS ist kein weiteres Chat-Fenster, sondern ein modularer, ereignisgesteuerter
AI-Assistent, der langfristig den kompletten PC verwaltet – mit einem holografischen
Iron-Man-HUD, mehreren unabhängigen AI-Engines, einem Obsidian-basierten Langzeitgedächtnis,
Sprachaktivierung und Automatisierung.

Dieses Repository enthält das **Alpha-1.5-Grundgerüst**: eine saubere, dokumentierte
Architektur plus einen **lauffähigen MVP** (HUD-Oberfläche, echte System-Statistiken,
AI-Konsole mit persistentem Gedächtnis, Reasoning & Planning, Windows-Automation,
lokale Sprachausgabe/-erkennung, Bildschirm-Verständnis, semantische Vault-Suche mit
RAG-Wissensabfragen). Alle weiteren Module
(Browser, Office, Smart Home …) sind als Schnittstellen vorbereitet und lassen
sich später einfach ergänzen.

> Der vollständige Funktionsumfang aus der Vision ist ein **Langzeitziel**. Was
> bereits real funktioniert und was noch Stub ist, steht in [`ROADMAP.md`](./ROADMAP.md).

**Slash-Befehle in der Chat-Konsole** (direkt im normalen Eingabefeld, keine
separate UI nötig):

| Befehl | Wirkung |
|---|---|
| `/plan <Aufgabe>` | Zerlegt eine Aufgabe in Schritte – echt im „Aufgaben"-Panel, abhakbar |
| `/denke <Frage>` | Zeigt APHELIOS' Analyse sichtbar (Werkzeug-Wahl → Kontext → Antwort) |
| `/wissen <Frage>` | Beantwortet NUR auf Basis des Obsidian-Vaults (RAG, mit Quellenangabe) |
| `/run <PowerShell-Befehl>` | Führt einen Befehl aus – **immer mit Bestätigungsdialog** |
| `/oeffne <Programm>` / `/schliesse <Programm>` | Startet/beendet ein Programm – mit Bestätigung |
| `/loesche <Pfad>` | Löscht eine Datei/einen Ordner – mit Bestätigung |
| `/downloads` | Listet den Downloads-Ordner (nur lesend) |
| `/sieh <Frage>` | Screenshot + Claude beschreibt/beantwortet – mit Bestätigung |
| `/lies` | Liest den sichtbaren Bildschirmtext (lokales OCR) – mit Bestätigung |
| `/fehler` | Sucht eine sichtbare Fehlermeldung und erklärt sie – mit Bestätigung |
| `/help` / `/hilfe` | Zeigt alle verfügbaren Befehle mit Kurzbeschreibung |

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
| **Memory / Second Brain** | ✅ Real (Alpha 1.5) | Schreibt Obsidian-Markdown mit Tags & Backlinks; semantische Suche über ChromaDB (lokal, kein API-Key) mit automatischem Volltext-Fallback; jeder Treffer mit „vor 3 Monaten"-Alter – Automation & Planning protokollieren ihre Aktionen/Projekte automatisch |
| **Knowledge (RAG)** | ✅ Real (Alpha 1.5) | `/wissen <Frage>` beantwortet ausschließlich auf Basis gefundener Vault-Notizen, mit Quellenangabe – ehrliche Absage ohne Treffer |
| **Sprachaktivierung** | ✅ Real | Wake-Word „Aphelios" + Dauer-Zuhören (Chrome/Edge); Push-to-Talk als Fallback in Firefox/Waterfox |
| **Sprachausgabe (TTS)** | ✅ Real, optional (Alpha 1.3) | Piper – natürliche, tiefe Stimme lokal, kein API-Key; Fallback auf Browser-Stimme – [`docs/voice.md`](./docs/voice.md) |
| **Spracherkennung (STT)** | ✅ Real, optional (Alpha 1.3) | faster-whisper lokal über Push-to-Talk – automatischer Fallback für Browser ohne Web-Speech-API (Firefox/Waterfox) – [`docs/voice.md`](./docs/voice.md) |
| **Vision (Bildschirm-Verständnis)** | ✅ Real, erste Ausbaustufe (Alpha 1.4) | Screenshot + Claude Vision (`/sieh`), lokales OCR (`/lies`), Fehlererkennung (`/fehler`) – immer mit Bestätigung – [`docs/vision.md`](./docs/vision.md) |
| **Wetter** | ✅ Real | Open-Meteo, kein API-Key nötig |
| **Gmail / Kalender** | ✅ Real, optional | Eigener Google-OAuth-Client nötig, siehe [`docs/integrations.md`](./docs/integrations.md) |
| **Handy-Zugriff** | ✅ Real (PWA) | HUD als App installierbar, gleiches WLAN – [`docs/integrations.md`](./docs/integrations.md) |
| **Event-Bus & Engine-Manager** | ✅ Real | Ereignisgesteuerte Kommunikation zwischen unabhängigen Engines |
| **Plugin-System** | ✅ Gerüst | Ordner-basierter Loader + Manifest-Schema |
| **Security-Gate** | ✅ Real | Gefährliche Aktionen erfordern Bestätigung |
| **WhatsApp** | 📄 Nur dokumentiert | Bewusst kein Code – Abwägung in [`docs/integrations.md`](./docs/integrations.md) |
| **Browser / Coding …** | 🔌 Stub | Schnittstellen vorbereitet, Implementierung folgt (siehe Roadmap) |

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
│      Vision · Automation · Voice (real) · Browser · Coding … (Stubs) │
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

> **Windows:** Nach der Einrichtung reicht künftig `run.bat` im `backend`-
> Ordner (Doppelklick oder `.\run.bat`) statt der letzten beiden Zeilen –
> aktiviert automatisch das `.venv` und startet dann. Das vermeidet den
> häufigsten Windows-Stolperstein: `python -m aphelios` **ohne** aktiviertes
> `.venv` startet stillschweigend mit dem globalen Python, dem die
> installierten Pakete (z. B. `piper-tts`) fehlen – Symptome dafür sind
> `ModuleNotFoundError`/`No module named …`, obwohl `pip install` vorher
> erfolgreich lief.

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

### 4 · Windows: alles auf einmal starten

Nach der einmaligen Einrichtung oben (Schritte 1 + 2) reicht künftig ein
Doppelklick auf **`Start-APHELIOS.bat`** im Projekt-Root – startet Backend
und Frontend je in einem eigenen Fenster (über `backend\run.bat` und
`frontend\run.bat`) und öffnet danach automatisch `http://localhost:5173`
im Standardbrowser. Beide Fenster offen lassen, während APHELIOS läuft;
ein Fenster schließen beendet nur den jeweiligen Server.

### 5 · (Optional) Gmail, Kalender & Handy-Zugriff

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
├── Start-APHELIOS.bat # Windows: Backend + Frontend + Browser in einem
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
<sub>APHELIOS · Alpha 1.5 · „Oh ja, das hatten wir schon einmal."</sub>
</div>
