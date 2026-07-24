# APHELIOS – Roadmap

Diese Roadmap bildet die **vollständige Vision** auf konkrete Meilensteine ab, damit
jederzeit klar ist, was bereits real funktioniert und was noch aussteht.

Legende: ✅ fertig (real) · 🟡 teilweise / Basis · 🔌 Schnittstelle vorhanden (Stub) · ⬜ geplant

---

## Alpha 1.0 — MVP-Grundgerüst  *(dieser Stand)*

**Ziel:** Lauffähiges, sichtbares Gerüst mit sauberer, erweiterbarer Architektur.

- ✅ Monorepo-Struktur (frontend / backend / plugins / docs)
- ✅ Event-Bus + BaseEngine + EngineManager
- ✅ Config-System (`.env`)
- ✅ SecurityGate (Bestätigung für gefährliche Aktionen)
- ✅ Plugin-Loader + Manifest-Schema + Kategorie-Ordner
- ✅ **SystemEngine** – echte Telemetrie (CPU/RAM/Disk/Netz/Temp/Akku)
- ✅ **ConversationEngine** – Claude API mit Fallback
- ✅ **MemoryEngine** – Obsidian-Markdown (Tags, Backlinks) + SQLite-Index
- ✅ FastAPI + WebSocket-API
- ✅ **HUD-Frontend** – Core, Gauges, Panels, animierte Konsole, Effekte
- 🟡 **Voice** – Wake-Word „Aphelios" (Web Speech API im Browser)
- ✅ Tauri-Shell-Scaffold (Desktop-Build auf Windows)
- ✅ Dokumentation & Tests

---

## Alpha 1.1 — Reasoning & Planning

- ⬜ ReasoningEngine (mehrstufige Analyse, Werkzeug-Auswahl)
- ⬜ PlanningEngine (Aufgabe → Schritte → Ausführung)
- ⬜ Streaming-Antworten Ende-zu-Ende im HUD
- ⬜ Persistenter Konversationskontext über MemoryEngine

## Alpha 1.2 — Windows-Automation *(nur Windows)*

- ⬜ AutomationEngine: PowerShell-Ausführung (über SecurityGate)
- ⬜ Programme starten/schließen/installieren/deinstallieren
- ⬜ Datei-Operationen (suchen/erstellen/verschieben/löschen mit Bestätigung)
- ⬜ pywinauto-Fensterinteraktion
- ⬜ Explorer / Downloads organisieren

## Alpha 1.3 — Voice (vollwertig)

- ⬜ Whisper STT (lokal oder API)
- ⬜ Hochwertige TTS mit natürlicher, tiefer männlicher Stimme
- ⬜ Streaming-Sprachdialog mit geringer Latenz
- ⬜ Dauerhafter Zuhör-Modus bis „Stop / Danke Aphelios / Beenden / Ruhemodus"

## Alpha 1.4 — Computer Vision

- ⬜ Bildschirmaufnahme + OCR (Tesseract / Windows OCR)
- ⬜ Fenster-, Button-, Icon-Erkennung (OpenCV)
- ⬜ Fehlermeldungs-Erkennung + automatische Hilfestellung
- ⬜ Tabellen-/Diagramm-Verständnis

## Alpha 1.5 — Second Brain (fortgeschritten)

- ⬜ Vektorsuche (ChromaDB / Qdrant) über den Vault
- ⬜ Automatische Verlinkung & Graph-Aufbau
- ⬜ Proaktives Wiederfinden („Das hattest du vor 8 Monaten gelernt")
- ⬜ Knowledge-Engine (RAG über Dokumentation)

## Alpha 1.6 — Developer & Office

- ⬜ CodingEngine (schreiben/refactoren, Git/GitHub, Docker, WSL)
- ⬜ BrowserEngine (Playwright-Steuerung)
- ⬜ Office: Word/Excel/PowerPoint, PDF-Analyse
- ⬜ VS Code / Claude Code Integration

---

## Beta — Betriebssystem-Charakter

- ⬜ AgentEngine: mehrere parallele AI-Agenten
- ⬜ Music (Spotify), Calendar, Mail, Discord/Steam-Steuerung
- ⬜ Proaktive Routinevorschläge auf Basis der Arbeitsweise
- ⬜ Backups & Cloud-Sync

## Langfristige Vision

- ⬜ Smart Home / Home Assistant
- ⬜ Lokale LLMs als Standard
- ⬜ Handy-App + Web-Dashboard
- ⬜ Multi-PC-Synchronisation, NAS, Raspberry-Pi-Nodes
- ⬜ CAD-/3D-Unterstützung, KI-Code-Reviews, Trading-Dashboard

---

> Die Architektur ist bewusst so gebaut, dass jeder dieser Punkte als **neue Engine
> oder neues Plugin** ergänzt werden kann, ohne bestehende Module anzufassen.
