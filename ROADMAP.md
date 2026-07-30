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

## Alpha 1.3 — Voice (vollwertig)

- ✅ **Whisper STT (lokal)** – `voice.transcribe` über faster-whisper, an
  eine Push-to-Talk-Oberfläche im Frontend angebunden. Aktiv als
  automatischer Fallback in Browsern ohne `SpeechRecognition`
  (Firefox/Waterfox – Gecko implementiert dieses Web-Standard-API
  grundsätzlich nicht); die Wake-Word-Erkennung in Chromium (Chrome/Edge)
  nutzt unverändert die Web Speech API, siehe `docs/voice.md`
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

- ✅ **Bildschirmaufnahme + OCR** – `/lies` nimmt den Bildschirm auf (`mss`)
  und extrahiert sichtbaren Text rein lokal über Tesseract, kein API-Key
  nötig. Windows-OCR (statt Tesseract) bewusst nicht zusätzlich – zwei
  parallele OCR-Backends zu pflegen wäre ohne konkreten Zusatznutzen
  Mehraufwand ohne Gegenwert.
- ✅ **Fehlermeldungs-Erkennung + automatische Hilfestellung** – `/fehler`
  durchsucht den erkannten Text per Regex-Heuristik nach typischen
  Fehler-Mustern (deutsch + englisch) und lässt Claude die gefundene
  Meldung erklären + nächste Schritte vorschlagen (mit `ANTHROPIC_API_KEY`).
- 🟡 **Fenster-, Button-, Icon-Erkennung** – bewusst **nicht** über OpenCV/
  Template-Matching (bräuchte eine kuratierte Template-Bibliothek oder ein
  trainiertes Modell, beides eigenständige Projekte). Stattdessen deckt
  `/sieh <Frage>` denselben praktischen Fall über Claude Vision ab („Wo ist
  der Speichern-Button?") – funktional vorhanden, nur technisch anders
  gelöst als ursprünglich skizziert.
- 🟡 **Tabellen-/Diagramm-Verständnis** – ebenfalls über `/sieh` abgedeckt
  (Claude liest Tabellen/Diagramme aus einem Screenshot nativ mit), kein
  dedizierter Parser gebaut – wäre in den allermeisten Fällen redundant.
- ⬜ Mehrere Monitore – aktuell wird immer nur der primäre Bildschirm
  aufgenommen.
- ⬜ Proaktives/automatisches Monitoring – nur On-Demand über die drei
  Slash-Befehle, siehe `docs/vision.md` für die Abwägung.

Details, Einrichtung (Tesseract-Installation) und Bus-Schnittstelle in
[`docs/vision.md`](./docs/vision.md).

## Alpha 1.5 — Second Brain (fortgeschritten)

- ✅ Automatische Verlinkung & Graph-Aufbau (MemoryEngine, siehe oben)
- ✅ Automatisches Protokoll statt manuellem Merken – Automation (Alpha 1.2)
  und Planning (Alpha 1.1) schreiben ihre Aktionen/Projekte selbstständig in
  den Vault; die ConversationEngine liest ihn bereits als Kontext mit
  (Alpha 1.1). Bewusst NICHT automatisch protokolliert: einzelne
  Chat-Nachrichten – das würde die kuratierten Kategorien mit rohem
  Gesprächsverlauf zumüllen, für den es bereits einen eigenen,
  nicht-Obsidian-Speicher gibt (`memory.kv`, siehe ConversationEngine)
- ✅ **Vektorsuche (ChromaDB) über den Vault** – `memory.search` sucht zuerst
  semantisch (lokale Embeddings, kein API-Key), fällt automatisch auf eine
  wortweise SQL-Volltextsuche (Titel/Inhalt/Tags) zurück, wenn ChromaDB
  fehlt/nicht erreichbar ist ODER die Vektorsuche zwar lief, aber keinen
  ausreichend relevanten Treffer fand (Distanz-Schwelle) – bewusst KEIN
  Qdrant zusätzlich, ein lokaler, eingebetteter Vektorstore reicht für
  Alpha 1.5 aus, siehe `docs/engines.md`
- ✅ **Proaktives Wiederfinden** – jeder Vault-Treffer trägt ein `age`-Feld
  ("vor 3 Monaten"/"heute"), sichtbar in Chat- (ConversationEngine),
  Analyse- (ReasoningEngine) und Wissens-Antworten (KnowledgeEngine)
- ✅ **Knowledge-Engine (RAG) über den Vault** – `/wissen <Frage>`
  durchsucht den Vault, lädt die Volltexte der Treffer und lässt Claude
  ausschließlich auf dieser Basis antworten (mit Quellenangabe); ohne
  Treffer ehrliche Absage statt erfundener Antwort. Bewusst NICHT: RAG über
  beliebige externe Dokumentation (PDFs, Webseiten) – das ist eine spätere
  Ausbaustufe, aktuell nur der eigene Obsidian-Vault als Wissensquelle.

## Alpha 1.6 — Developer & Office *(dieser Stand)*

- ✅ **CodingEngine (schreiben/erklären, optional in eine Datei)** –
  `/code <Anfrage>` liefert vollständigen, lauffähigen Code + kurze
  Erklärung im Chat; `/code-datei <Pfad> <Anfrage>` speichert den ersten
  Code-Block zusätzlich in der Datei (immer mit SecurityGate-Bestätigung)
  – bereit zum Öffnen in VS Code. Bewusst NICHT: Datei-**Lesen** (bräuchte
  dieselbe Sensibilitäts-Abwägung wie bei der `OfficeEngine`, hier für
  beliebige Dateitypen, spätere Ausbaustufe) und kein dediziertes
  Git/Docker/WSL-Kommando (deckt `/run` bereits ab) – siehe
  `docs/engines.md`
- ✅ **BrowserEngine (Playwright-Steuerung)** – `/browse <URL> [Frage]`
  öffnet eine Seite in einem echten Chromium und beantwortet Fragen dazu
  (mit `ANTHROPIC_API_KEY`) bzw. liefert den rohen Seitentext (ohne Key);
  jede Anfrage über SecurityGate bestätigungspflichtig. Bewusst NICHT:
  Interaktion (Klicken, Formulare, Login-Flows) oder Websuche – siehe
  `docs/browser.md`
- ✅ **Office: Word/Excel/PowerPoint, PDF-Analyse** – `/dokument <Pfad>
  [Frage]` extrahiert Text (Word, Excel je Tabellenblatt, PowerPoint je
  Folie, PDF) und lässt Claude die Frage dazu beantworten (mit
  `ANTHROPIC_API_KEY`) bzw. liefert den rohen Text (ohne Key); jede
  Anfrage über SecurityGate bestätigungspflichtig. Bewusst NICHT:
  Dokumente erstellen/schreiben, Excel-Formeln neu berechnen, eingebettete
  Bilder/Diagramme, alte Binärformate (.doc/.xls/.ppt) – siehe
  `docs/office.md`
- ✅ **VS Code / Claude Code Integration** – der Umfang war beim Zuschnitt
  dieses Punkts stark auslegungsabhängig (bereits per `/oeffne` abgedeckt
  bis hin zu einer eigenständigen VS-Code-Extension als Get-Projekt); eine
  Rückfrage dazu blieb unbeantwortet, deshalb die proportionalste,
  begründbare Lesart umgesetzt: `/code-datei` (siehe oben) schreibt von
  Claude generierten Code direkt in eine Datei – der Nutzer öffnet sie
  danach selbst in VS Code (oder APHELIOS via `/oeffne`). Bewusst NICHT:
  eine eigene VS-Code-Extension mit Live-Anbindung ans Backend – das wäre
  ein eigenständiges, deutlich größeres Softwareprojekt (eigenes
  TypeScript-Repo, VS Code Extension API, eigenes Build/Package) und sollte
  nur mit explizitem Nutzer-Einverständnis begonnen werden.
- ✅ **KI-gesteuerte Werkzeug-Auswahl (Claude Tool-Use)** – nicht im
  ursprünglichen Alpha-1.6-Umfang, aber eng verwandt: die
  `ConversationEngine` kann jetzt selbst entscheiden, ob eine normal
  formulierte Chat-Nachricht ein Werkzeug braucht ("öffne Spotify" statt
  `/oeffne Spotify`), statt nur auf explizite Slash-Befehle zu reagieren.
  Nutzt dieselben Engines/SecurityGate-Bestätigungen wie die Slash-Befehle,
  siehe `docs/engines.md`

## Alpha 1.7 — Weitere App-Integrationen

- ✅ Wetter (Open-Meteo), Gmail + Google Kalender (lesend) – siehe
  `docs/integrations.md`
- ⬜ WhatsApp – bewusst noch ohne Code (offizielle Business-API ist für
  Unternehmen gedacht, inoffizielle Wege verletzen die Nutzungsbedingungen);
  Entscheidung liegt beim Nutzer, siehe `docs/integrations.md`
- ✅ **Schreibzugriff (Termine anlegen, Mails senden)** – `/mail-senden <An>
  | <Betreff> | <Text>` und `/termin-anlegen <Titel> | <Start> | <Dauer in
  Min.>` (auch über Claude Tool-Use auslösbar), beide immer über
  SecurityGate bestätigungspflichtig – siehe `docs/integrations.md`,
  `docs/engines.md`. Erweiterte Google-Scopes (`gmail.send`,
  `calendar.events`) – vor Alpha 1.7 angemeldete Nutzer müssen
  `python scripts/google_auth.py` einmalig erneut ausführen.
- ⬜ Discord, Steam, weitere Musik-Dienste – wie WhatsApp: brauchen jeweils
  eigene Entwickler-Zugangsdaten/OAuth-Einrichtung, die der Nutzer selbst
  anlegen müsste; Entscheidung, ob/welcher Dienst zuerst, liegt beim Nutzer

## Alpha 1.8 — Musik (Spotify)-Steuerung

- ✅ **MusicEngine** – zeigt den aktuell laufenden Song (Titel, Interpret,
  Album-Cover, Fortschritt) und steuert die Wiedergabe: Play/Pause/Skip/
  Lautstärke/„Gefällt mir" – kreisförmiges Musik-Panel im HUD (rotierendes
  Cover + Fortschritts-Ring), siehe `docs/integrations.md#spotify-einrichten`,
  `docs/engines.md`. Ursprünglich für Beta geplant, vorgezogen, weil die
  Grundarbeit (OAuth-Muster, Poll-Engine, Panel-Konventionen) durch
  Wetter/Gmail/Kalender bereits stand.
- Bewusst `RiskLevel.SAFE` statt `CONFIRM` – trivial reversible Aktionen
  ohne Konsequenz für Dritte, anders als eine gesendete Mail.
- Wiedergabesteuerung erfordert Spotify Premium (API-Einschränkung); der
  aktuelle Song wird auch mit einem Free-Account angezeigt.

## Alpha 1.9 — Investment-Committee & geplante Recherche (Research Agents)

- ✅ **ResearchEngine** – baut die rein analytische Investment-Committee-
  Idee aus dem extern angeschauten Projekt
  [Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) nativ im
  Aphelios-Stil nach (eigene Engine, kein übernommener Fremdcode, kein
  Order-Ausführen/keine Broker-Anbindung): `/aktien-analyse <Symbol>` bzw.
  Claude-Werkzeug `run_investment_committee` – drei parallele
  Bulle-/Bär-/Risiko-Perspektiven + zusammenfassendes Fazit, keine
  konkrete Kauf-/Verkaufsempfehlung, immer mit Disclaimer.
- ⬜ ~~Geplante Recherche (Scheduled Research)~~ – ursprünglich gebaut
  (automatischer täglicher Lauf über die Watchlist), aber wieder entfernt:
  lief bei jedem Backend-Neustart erneut (kein persistenter "letzter
  Lauf"-Zustand) und erzeugte dadurch unerwartet viele ungefragte
  Claude-Aufrufe/Vault-Notizen – auf Nutzerwunsch ausgebaut statt repariert.
- Bewusst NICHT übernommen aus Vibe-Trading: Broker-Anbindungen, Live-
  Order-Ausführung, Kill-Switch, 450+ Alpha-Faktoren, Multi-Provider-LLM-
  Adapter – das wäre ein eigenständiges, deutlich größeres Projekt mit
  echtem finanziellem Risiko, siehe `docs/engines.md`.

---

## Alpha 1.10 — Live-Bildschirmfreigabe (Ersatz für Einzel-Screenshots)

- ✅ **ScreenShareEngine** – Nutzer teilt aktiv einen Bildschirm/ein Fenster
  über die Browser-Screen-Capture-API (`getDisplayMedia`, Button in der
  TopBar); ein Canvas komprimiert alle 3s einen Frame als JPEG und sendet
  ihn ans Backend. Kein echtes Video an Claude (die API nimmt nur
  Einzelbilder) – nur der jeweils LETZTE Frame wird gehalten, kein Archiv.
  - **Auf Zuruf** – `/bildschirm <Frage>` analysiert den aktuellen Frame.
  - **Proaktiv (Schalter im HUD)** – prüft alle 10s automatisch und meldet
    sich nur bei etwas Auffälligem (Fehlermeldung, Absturz) – sonst
    lautlos, kein Spam.
- Ergänzt (ersetzt nicht) die VisionEngine – `/sieh` bleibt der Weg für
  einen einmaligen OS-Screenshot ohne aktive Freigabe.

## Beta — Betriebssystem-Charakter

- ⬜ AgentEngine: mehrere parallele AI-Agenten
- ⬜ Proaktive Routinevorschläge auf Basis der Arbeitsweise
- ⬜ Backups & Cloud-Sync

## Langfristige Vision

- ✅ Handy-Zugriff als PWA (heute nutzbar, gleiches WLAN – `docs/integrations.md`)
- ✅ **Trading-Dashboard** – Popup über den „TRADING"-Button: Watchlist mit
  echten Kursen (StockEngine, Yahoo Finance, kein Key nötig) + eingebetteter
  TradingView-Chart; `/aktie <Symbol>` bzw. Claude-Werkzeug beantworten
  Kursfragen im Chat. Vorgezogen aus dieser Liste, siehe `docs/engines.md`.
- ⬜ Native Handy-App (eigenständiges Projekt: Termine/Mails aktiv verwalten,
  Push-Benachrichtigungen, Hintergrund-Sync)
- ⬜ Smart Home / Home Assistant
- ⬜ Lokale LLMs als Standard
- ✅ **Web-Dashboard** – eigene Seite (`/dashboard`, Button in der TopBar):
  Engine-Status-Grid (live, alle 5s aktualisiert), System-Werte, zuletzt
  erzeugte Vault-Notizen als Aktivitäts-Feed. Kein neuer Router – simpler
  Pfad-Check in `main.tsx`.
- ⬜ Multi-PC-Synchronisation, NAS, Raspberry-Pi-Nodes
- ⬜ CAD-/3D-Unterstützung, KI-Code-Reviews

---

> Die Architektur ist bewusst so gebaut, dass jeder dieser Punkte als **neue Engine
> oder neues Plugin** ergänzt werden kann, ohne bestehende Module anzufassen.
