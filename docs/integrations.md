# App-Integrationen & Handy-Zugriff

Dieses Dokument beschreibt, wie externe Dienste (Wetter, Gmail, Kalender,
WhatsApp) an APHELIOS angebunden werden und wie du APHELIOS auf dem Handy
nutzt. Ehrlicher Grundsatz dieses Projekts: **lieber eine kleinere Funktion,
die wirklich echte Daten liefert, als eine große, die nur so aussieht.**

| Integration | Status | Braucht Zugangsdaten? |
|---|---|---|
| **Wetter** (Open-Meteo) | ✅ Real, sofort aktiv | Nein |
| **Gmail** (ungelesene Mails) | ✅ Real, optional | Ja – eigener Google-OAuth-Client |
| **Google Kalender** (kommende Termine) | ✅ Real, optional | Ja – derselbe Google-OAuth-Client |
| **Spotify** (Song lesen + Play/Pause/Skip/Lautstärke/Like) | ✅ Real, optional | Ja – eigene Spotify-App |
| **WhatsApp** | 🔌 Nur dokumentiert, kein Code | Ja – siehe Abwägung unten |
| **Handy-Zugriff (PWA)** | ✅ Real, heute nutzbar | Nein (gleiches WLAN) |
| **Native Handy-App** | ⬜ Geplant, eigenes Projekt | – |

---

## Wetter (bereits aktiv)

Nutzt [Open-Meteo](https://open-meteo.com/) – komplett kostenlos, kein Account,
kein Key. Standardmäßig für „Berlin" konfiguriert; eigene Stadt in der `.env`:

```bash
APHELIOS_WEATHER_CITY=München
```

Kein weiterer Schritt nötig – die `WeatherEngine` startet automatisch mit.

---

## Gmail & Kalender einrichten

Beide nutzen **eine gemeinsame** Google-Anmeldung (ein Consent-Vorgang deckt
alle Scopes ab). Seit Alpha 1.7 auch **schreibend**: `/mail-senden` und
`/termin-anlegen` (siehe `docs/engines.md`) – beide immer über das
SecurityGate bestätigungspflichtig (`docs/security.md`), APHELIOS sendet
nie eine Mail oder legt nie einen Termin an ohne explizite Bestätigung mit
sichtbarem Inhalt.

### 1 · Google-Cloud-Projekt anlegen

1. [console.cloud.google.com](https://console.cloud.google.com/) → neues Projekt erstellen (kostenlos).
2. **APIs & Dienste → Bibliothek** → aktivieren:
   - „Gmail API"
   - „Google Calendar API"
3. **APIs & Dienste → OAuth-Zustimmungsbildschirm**:
   - Nutzertyp „Extern" (für ein privates Google-Konto reicht das; Google
     zeigt dann eine „nicht verifizierte App"-Warnung – das ist normal für
     eigene Test-Apps und unbedenklich, solange nur du dich anmeldest).
   - Deine eigene Gmail-Adresse als Testnutzer eintragen.
4. **APIs & Dienste → Zugangsdaten → Zugangsdaten erstellen → OAuth-Client-ID**:
   - Anwendungstyp: **Desktop-App**
   - Nach dem Erstellen: **Client-ID** und **Client-Secret** kopieren.

### 2 · In APHELIOS eintragen

In der `.env` (siehe `.env.example`):

```bash
GOOGLE_CLIENT_ID=deine-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=dein-client-secret
```

### 3 · Einmalig anmelden

```bash
cd backend
pip install -e ".[google]"
python scripts/google_auth.py
```

Ein Browser-Fenster öffnet sich zur Google-Anmeldung. Nach der Bestätigung
liegt eine Token-Datei unter `./data/google_token.json` (Pfad über
`APHELIOS_GOOGLE_TOKEN_PATH` änderbar). Danach das Backend neu starten
(`python -m aphelios`) – „Mails" und „Kalender" im HUD zeigen ab jetzt echte
Daten statt der Vorschau.

> Die Token-Datei enthält ein Zugriffs-Refresh-Token – **nicht committen**
> (liegt standardmäßig unter `./data/`, das laut `.gitignore` ignoriert wird).

**Warum "Mails"/"Kalender" nach der Anmeldung trotzdem wieder auf
Mock-Vorschau zurückfallen können:** `APHELIOS_GOOGLE_TOKEN_PATH` ist relativ
(`./data/google_token.json`) und wird fest gegen den `backend`-Ordner
verankert – unabhängig davon, aus welchem Arbeitsverzeichnis `python -m
aphelios` bzw. `run.bat` tatsächlich gestartet wird. Ein absoluter Pfad in
der `.env` (z. B. `C:\Users\<Name>\Aphelios\backend\data\google_token.json`)
funktioniert wie gehabt unverändert.

> **Bereits vor Alpha 1.7 angemeldet?** Das gespeicherte Token kennt dann nur
> die alten, rein lesenden Scopes – `/mail-senden`/`/termin-anlegen`
> schlagen mit einem Berechtigungsfehler fehl (die Fehlermeldung weist
> darauf explizit hin). Einmalig erneut ausführen:
> `python scripts/google_auth.py` (Schritt 3 oben) – ein neuer
> Consent-Bildschirm fragt dann zusätzlich nach den Schreib-Berechtigungen
> ("Mails senden", "Termine verwalten"), die Token-Datei wird dabei überschrieben.

### Mails senden & Termine anlegen (Alpha 1.7)

```
/mail-senden max@example.com | Update | Das Projekt ist fertig.
/termin-anlegen Team-Meeting | 2026-08-01 15:00 | 60
```

Beide Befehle erwarten ihre Felder **Pipe-getrennt** (`|`) – bewusst keine
Freitext-Erkennung wie bei URLs/Dateipfaden in Browser-/OfficeEngine: eine
Mail hat drei gleichwertig lange Freitextfelder ohne zuverlässigen
natürlichsprachlichen Trenner, und ein Datum ("morgen um 15 Uhr") bräuchte
eine eigene Sprachverarbeitung mit vielen Zeitzonen-/Sonderfällen. Der
Start-Zeitpunkt für Termine ist `JJJJ-MM-TT HH:MM` in **lokaler Systemzeit**.

Claude kann beide Aktionen auch selbst über die Tool-Use-API auslösen (z. B.
"schreib eine Mail an max@example.com, dass ich später komme") – siehe
`docs/engines.md`, Abschnitt „ConversationEngine – Werkzeug-Nutzung". In
beiden Fällen (Slash-Befehl oder KI-Auswahl) zeigt APHELIOS **immer** eine
Bestätigung mit dem vollständigen Inhalt, bevor etwas gesendet/angelegt wird
– eine gesendete Mail lässt sich nicht zurückholen, ein Termin ist für
andere Teilnehmer sichtbar.

---

## Spotify einrichten

Zeigt den aktuell laufenden Song im HUD (Titel, Interpret, Cover, Fortschritt)
und steuert die Wiedergabe – Play/Pause/Skip/Lautstärke/„Gefällt mir". Anders
als Wetter braucht Spotify zwingend eine eigene App-Anmeldung: Spotifys
öffentlicher Client-Credentials-Zugang erlaubt nur Katalogdaten, keine
Wiedergabesteuerung.

> **Play/Pause/Skip/Lautstärke setzen Spotify Premium voraus** (Spotify-
> API-Einschränkung, keine APHELIOS-Einschränkung). Der aktuelle Song wird
> auch mit einem Free-Account angezeigt.

### 1 · Spotify-App anlegen

1. [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
   → mit dem eigenen Spotify-Account anmelden → **Create app**.
2. Beliebiger Name/Beschreibung. **Redirect URI** muss exakt sein:
   ```
   http://127.0.0.1:8898/callback
   ```
3. API/SDK: „Web API" ankreuzen, speichern.
4. In den App-Einstellungen **Client ID** und **Client Secret** kopieren.

### 2 · In APHELIOS eintragen

In der `.env` (siehe `.env.example`):

```bash
SPOTIFY_CLIENT_ID=deine-client-id
SPOTIFY_CLIENT_SECRET=dein-client-secret
```

### 3 · Einmalig anmelden

```bash
cd backend
python scripts/spotify_auth.py
```

Ein Browser-Fenster öffnet sich zur Spotify-Anmeldung (keine zusätzliche
Abhängigkeit nötig – nutzt `httpx`, das APHELIOS ohnehin mitbringt). Nach der
Bestätigung liegt eine Token-Datei unter dem in
`APHELIOS_SPOTIFY_TOKEN_PATH` konfigurierten Pfad (Standard:
`./data/spotify_token.json`, wie beim Google-Token relativ zum
`backend`-Ordner verankert, nicht zum Arbeitsverzeichnis). Backend neu
starten (`python -m aphelios`) – das Musik-Panel zeigt ab jetzt echte Daten
statt der Vorschau.

> Die Token-Datei enthält ein Zugriffs-Refresh-Token – **nicht committen**
> (liegt standardmäßig unter `./data/`, das laut `.gitignore` ignoriert wird).

**Läuft nichts?** Das Panel zeigt „Kein Song aktiv – starte Spotify auf einem
Gerät" – Spotify braucht ein aktives Gerät (Desktop-App, Handy, Web Player),
sonst weiß die API nicht, wohin ein Play-Befehl gehen soll.

---

## WhatsApp — bewusst (noch) ohne Code

Für WhatsApp gibt es **keinen** Weg, der „einfach nur einen Key einträgt" wie
bei Wetter oder Gmail. Zwei echte Optionen, beide mit Kompromissen:

1. **Offizielle WhatsApp Business Cloud API (Meta).**
   Für Unternehmen gedacht, die mit Kunden kommunizieren, die zuerst
   Kontakt aufgenommen haben – **nicht** dafür gemacht, dein privates
   WhatsApp-Postfach gesamt gebündelt zu lesen/verwalten. Erfordert ein
   Meta-Entwicklerkonto, eine Geschäfts-Verifizierung und eine eigene
   Telefonnummer für den Business-Account (nicht deine private Nummer).
2. **Inoffizielle Bibliotheken** (z. B. Web-Automatisierung deiner
   WhatsApp-Web-Sitzung). Funktioniert oft technisch, verstößt aber gegen
   WhatsApps Nutzungsbedingungen und kann zur Sperrung deines Kontos führen –
   deshalb baut APHELIOS das nicht standardmäßig ein.

**Wenn du trotzdem einen Weg willst:** Sag mir, welche der beiden Optionen du
bevorzugst (Business-API mit eigener Zweitnummer, oder das ToS-Risiko der
inoffiziellen Variante bewusst in Kauf nehmen) – dann bauen wir gezielt genau
diesen Weg, statt etwas Kaputtes oder Riskantes vorab einzubauen.

---

## APHELIOS auf dem Handy

### Heute: als PWA installieren (funktioniert bereits)

Das HUD ist eine Progressive Web App – lässt sich ohne separaten Code auf dem
Handy „installieren" und wie eine echte App öffnen (eigenes Fenster, eigenes
Icon, kein Browser-Rahmen):

1. PC und Handy im **selben WLAN**.
2. Backend + Frontend auf dem PC starten (siehe `README.md`).
3. Die **lokale Netzwerk-IP** deines PCs herausfinden (Windows:
   `ipconfig` → „IPv4-Adresse", z. B. `192.168.1.23`).
4. Auf dem Handy im Browser öffnen: `http://<IPv4-Adresse>:5173`
5. Chrome/Edge (Android): Menü → „Zum Startbildschirm hinzufügen" /
   „App installieren". Safari (iOS): Teilen-Symbol → „Zum Home-Bildschirm".

**Einschränkung:** Sprachaktivierung (Wake-Word/TTS) benötigt einen
„sicheren Kontext" (HTTPS oder `localhost`) – über eine reine LAN-IP ohne
HTTPS blendet das HUD den Mikrofon-Button automatisch aus (kein Fehler, nur
nicht verfügbar). Alles andere (Stats, Chat, Wetter, Mail, Kalender) läuft
auch so.

### Geplant: native App

„Kalender/Gmail/WhatsApp direkt vom Handy aus **verwalten**" (nicht nur
ansehen) – inkl. Termine anlegen, Mails schreiben, Push-Benachrichtigungen
im Hintergrund – ist ein **eigenständiges Mobil-Projekt** (z. B. React
Native oder Flutter), kein Nebeneffekt der bestehenden Web-HUD-Codebasis.
Das ist bewusst nicht in Alpha 1.0 enthalten; siehe `ROADMAP.md`.
