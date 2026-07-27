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
Mail-Lesen + Kalender-Lesen ab). Rein lesend – APHELIOS legt keine Termine an
und verschickt keine Mails ohne separate, spätere Freigabe.

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
