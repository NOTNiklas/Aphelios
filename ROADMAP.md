# APHELIOS – Roadmap

Diese Roadmap bildet die **vollständige Vision** auf konkrete Meilensteine ab, damit
jederzeit klar ist, was bereits real funktioniert und was noch aussteht.

Legende: ✅ fertig (real) · 🟡 teilweise / Basis · 🔌 Schnittstelle vorhanden (Stub) · ⬜ geplant

---

## Alpha 1.0 — MVP-Grundgerüst

**Ziel:** Lauffähiges, sichtbares Gerüst mit sauberer, erweiterbarer Architektur.

- ✅ Monorepo-Struktur (frontend / backend / plugins / docs)
- ✅ Event-Bus + BaseEngine + EngineManager
- ✅ Config-System (`.env`)
- ✅ SecurityGate (Bestätigung für gefährliche Aktionen)
- ✅ Plugin-Loader + Manifest-Schema + Kategorie-Ordner
- ✅ **SystemEngine** – echte Telemetrie (CPU/RAM/Disk/Netz/Temp/Akku)
- ✅ **ConversationEngine** – Claude API mit Fallback (mit klarer Fehlermeldung
  statt stillem Rückfall, wenn ein Key vorhanden, die Anfrage aber scheitert)
- ✅ **MemoryEngine** – Obsidian-Markdown (Tags, automatische Backlinks nach
  Kategorie/gemeinsamen Tags) + SQLite-Index → nativer Obsidian-Graph-View
  zeigt die Notizen als verbundenes Netz. Update-statt-Duplikat per
  Titel+Kategorie, damit andere Engines denselben Vorgang wiederholt
  protokollieren können, ohne den Vault zuzumüllen
- ✅ **WeatherEngine** – echtes Wetter via Open-Meteo, kein API-Key nötig
- ✅ **MailEngine** / **CalendarEngine** – echtes Gmail/Google-Kalender-Lesen,
  optional (eigener Google-OAuth-Client nötig, siehe `docs/integrations.md`)
- ✅ FastAPI + WebSocket-API
- ✅ **HUD-Frontend** – Core (pulsiert beim Antworten/Sprechen), Gauges,
  Panels, animierte Konsole, Effekte
- ✅ **Voice** – Wake-Word „Aphelios" + Sprachausgabe (Web Speech API im Browser)
- ✅ **PWA** – auf dem Handy als App installierbar (gleiches WLAN)
- ✅ Tauri-Shell-Scaffold (Desktop-Build auf Windows)
- ✅ Dokumentation & Tests

---

## Alpha 1.1 — Reasoning & Planning

- ✅ **ReasoningEngine** – mehrstufige Analyse mit sichtbarer Werkzeug-Auswahl
  (Vault-Suche / System-Werte / Aufgaben-Zerlegung / direkte Antwort),
  ausgelöst über `/denke <Frage>` im Chat
- ✅ **PlanningEngine** – zerlegt Aufgaben in Schritte (`/plan <Aufgabe>`),
  echte Anzeige + Abhaken im „Aufgaben"-Panel; automatische **Ausführung**
  der Schritte ist AutomationEngine (Alpha 1.2) – hier nur Zerlegung + Tracking.
  Jeder Plan wird zusätzlich als „Projekte"-Notiz im Obsidian-Vault geführt
  (Checkliste + Fortschritt, live aktualisiert) – abgeschlossene Projekte
  bleiben dort dauerhaft auffindbar, auch nachdem das Aufgaben-Panel den
  nächsten Plan zeigt
- ✅ Streaming-Antworten Ende-zu-Ende im HUD – bereits in Alpha 1.0 für die
  ConversationEngine gebaut, jetzt bestätigt auch für Reasoning/Planning über
  dieselbe `chat.token`/`chat.response`-Pipeline (keine Sonderlogik nötig)
- ✅ Persistenter Konversationskontext über MemoryEngine – Gesprächsverlauf
  übersteht einen Backend-Neustart (neuer `memory.kv.*`-Speicher), zusätzlich
  fließen thematisch passende Vault-Notizen automatisch in den Kontext ein

## Alpha 1.2 — Windows-Automation *(nur Windows)*

- ✅ **AutomationEngine: PowerShell-Ausführung** (über SecurityGate) –
  `/run <Befehl>`, Risiko-Einstufung erkennt zusätzlich besonders
  zerstörerische Muster (Registry, Formatierung, Deinstallation, Neustart …)
- 🟡 **Programme starten/schließen** – `/oeffne`, `/schliesse` (real,
  über SecurityGate). **Installieren/deinstallieren bewusst noch nicht**:
  der Mechanismus (winget? Allowlist? beliebige Installer?) ist eine echte
  Sicherheitsabwägung, die eine bewusste Entscheidung des Nutzers braucht –
  genau wie WhatsApp in `docs/integrations.md`.
- ✅ **Datei-Operationen** (suchen/erstellen/verschieben/löschen mit
  Bestätigung) – `list_dir`, `find_files`, `create_folder`, `create_file`,
  `move_file`, `delete_path` (`/loesche`)
- ⬜ pywinauto-Fensterinteraktion – erfordert eine echte, laufende
  Windows-Desktop-Sitzung zum Testen (UI Automation), die in der
  Entwicklungsumgebung (Linux, ohne Display) nicht verfügbar ist
- ✅ Explorer/Downloads organisieren – `/downloads` listet den
  Downloads-Ordner (nur lesend, weitere Organisation über die
  Datei-Operationen oben)
- ✅ Obsidian-Protokoll – jede erfolgreich ausgeführte, zustandsändernde
  Aktion (PowerShell, Programm starten/schließen, Datei-Operationen)
  schreibt eine Notiz in die Kategorie „Protokolle"; rein lesende Aktionen
  bewusst nicht

## Alpha 1.3 — Voice (vollwertig)  *(dieser Stand)*

- 🟡 **Whisper STT (lokal)** – `voice.transcribe` über faster-whisper ist
  real implementiert und getestet, aber noch nicht an eine
  Aufnahme-Oberfläche im Frontend angebunden (z. B. Push-to-Talk); die
  laufende Wake-Word-Erkennung nutzt weiterhin die bewährte Web Speech API,
  siehe `docs/voice.md`
- ✅ **Hochwertige TTS mit natürlicher, tiefer männlicher Stimme** – Piper
  läuft lokal (kein API-Key, keine Kosten), `speak()` im Frontend nutzt sie
  automatisch, sobald ein Modell konfiguriert ist; ohne Konfiguration
  fällt es auf die Browser-Stimme zurück statt zu scheitern
- ✅ Streaming-Sprachdialog mit geringer Latenz – Wake-Word-Erkennung und
  Chat-Antwort-Streaming liefen bereits vorher live; TTS-Antworten spielen
  jetzt ab, sobald das erste Audio-Paket da ist (kein Warten auf den
  gesamten Dialog)
- ✅ Dauerhafter Zuhör-Modus bis „Stop / Danke Aphelios / Beenden /
  Ruhemodus" – bereits seit Alpha 1.0/1.1 über die Web Speech API gebaut,
  hier nur bestätigt/unverändert

## Alpha 1.4 — Computer Vision

- ⬜ Bildschirmaufnahme + OCR (Tesseract / Windows OCR)
- ⬜ Fenster-, Button-, Icon-Erkennung (OpenCV)
- ⬜ Fehlermeldungs-Erkennung + automatische Hilfestellung
- ⬜ Tabellen-/Diagramm-Verständnis

## Alpha 1.5 — Second Brain (fortgeschritten)

- ✅ Automatische Verlinkung & Graph-Aufbau (MemoryEngine, siehe oben)
- ✅ Automatisches Protokoll statt manuellem Merken – Automation (Alpha 1.2)
  und Planning (Alpha 1.1) schreiben ihre Aktionen/Projekte selbstständig in
  den Vault; die ConversationEngine liest ihn bereits als Kontext mit
  (Alpha 1.1). Bewusst NICHT automatisch protokolliert: einzelne
  Chat-Nachrichten – das würde die kuratierten Kategorien mit rohem
  Gesprächsverlauf zumüllen, für den es bereits einen eigenen,
  nicht-Obsidian-Speicher gibt (`memory.kv`, siehe ConversationEngine)
- ⬜ Vektorsuche (ChromaDB / Qdrant) über den Vault
- ⬜ Proaktives Wiederfinden („Das hattest du vor 8 Monaten gelernt")
- ⬜ Knowledge-Engine (RAG über Dokumentation)

## Alpha 1.6 — Developer & Office

- ⬜ CodingEngine (schreiben/refactoren, Git/GitHub, Docker, WSL)
- ⬜ BrowserEngine (Playwright-Steuerung)
- ⬜ Office: Word/Excel/PowerPoint, PDF-Analyse
- ⬜ VS Code / Claude Code Integration

## Alpha 1.7 — Weitere App-Integrationen

- ✅ Wetter (Open-Meteo), Gmail + Google Kalender (lesend) – siehe
  `docs/integrations.md`
- ⬜ WhatsApp – bewusst noch ohne Code (offizielle Business-API ist für
  Unternehmen gedacht, inoffizielle Wege verletzen die Nutzungsbedingungen);
  Entscheidung liegt beim Nutzer, siehe `docs/integrations.md`
- ⬜ Schreibzugriff (Termine anlegen, Mails senden) – über SecurityGate
  bestätigungspflichtig
- ⬜ Discord, Steam, weitere Musik-Dienste

---

## Beta — Betriebssystem-Charakter

- ⬜ AgentEngine: mehrere parallele AI-Agenten
- ⬜ Music (Spotify)-Steuerung
- ⬜ Proaktive Routinevorschläge auf Basis der Arbeitsweise
- ⬜ Backups & Cloud-Sync

## Langfristige Vision

- ✅ Handy-Zugriff als PWA (heute nutzbar, gleiches WLAN – `docs/integrations.md`)
- ⬜ Native Handy-App (eigenständiges Projekt: Termine/Mails aktiv verwalten,
  Push-Benachrichtigungen, Hintergrund-Sync)
- ⬜ Smart Home / Home Assistant
- ⬜ Lokale LLMs als Standard
- ⬜ Web-Dashboard
- ⬜ Multi-PC-Synchronisation, NAS, Raspberry-Pi-Nodes
- ⬜ CAD-/3D-Unterstützung, KI-Code-Reviews, Trading-Dashboard

---

> Die Architektur ist bewusst so gebaut, dass jeder dieser Punkte als **neue Engine
> oder neues Plugin** ergänzt werden kann, ohne bestehende Module anzufassen.
