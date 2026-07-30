# Sprache – Wake-Word, Sprachausgabe (TTS) und Spracherkennung (STT)

## Ziel

Aktivierungswort **„Aphelios"**. Danach hört das Mikrofon dauerhaft zu, bis eines der
Stopp-Kommandos fällt: „Stop", „Danke Aphelios", „Beenden", „Ruhemodus".

Die Stimme soll natürlich, ruhig und leicht tief (männlich) klingen, mit klarer
Aussprache und geringer Latenz.

APHELIOS hat zwei getrennte Sprach-Bausteine, die zusammenspielen:

| Baustein | Läuft wo? | Technik | Braucht Einrichtung? |
|---|---|---|---|
| Wake-Word „Aphelios" + Dauer-Zuhören | Browser | Web Speech API (nur Chromium) | Nein – Mikrofon-Button klicken, fertig |
| Push-to-Talk (Alternative ohne Wake-Word) | Browser + Backend | `MediaRecorder` + faster-whisper | Nein in Chromium (Fallback), Pflicht in Firefox/Waterfox |
| Sprachausgabe (TTS) | Backend, Fallback im Browser | Piper (lokal) → Browser-Stimme | Optional (siehe unten) |
| Spracherkennung (STT) | Backend | faster-whisper (lokal) | Optional, kein manueller Download nötig |

**Grundsatz:** Ohne jede Einrichtung funktioniert alles wie in Alpha 1.0/1.1 –
Wake-Word (Chromium) bzw. Push-to-Talk (alle anderen) läuft im Browser,
Antworten werden mit der (robotischen) Browser-Stimme vorgelesen. Die
Ausbaustufen unten verbessern nur die **Qualität**, nichts wird dadurch
kaputter oder Pflicht.

---

## Browser-Kompatibilität: Chromium vs. Firefox/Waterfox

Die **Web Speech API** (`SpeechRecognition`, für das Wake-Word und
Dauer-Zuhören) ist nur in Chromium-basierten Browsern implementiert (Chrome,
Edge, Brave, Opera, …). **Firefox-basierte Browser (Firefox, Waterfox,
LibreWolf, …) implementieren dieses Web-Standard-API grundsätzlich nicht** –
das ist eine Einschränkung von Gecko/Firefox selbst, nicht etwas, das sich
von APHELIOS aus beheben lässt.

Damit Sprachein-/ausgabe trotzdem in jedem Browser mit Mikrofon funktioniert,
erkennt APHELIOS das automatisch und wechselt auf **Push-to-Talk** (siehe
unten) – kein Wake-Word dort, aber Sprachbefehle und Sprachausgabe
funktionieren genauso. Die Sprachausgabe (TTS, sowohl Piper als auch die
Browser-Stimme) ist davon ohnehin nicht betroffen und funktioniert in jedem
Browser identisch.

---

## Wake-Word & Dauer-Zuhören (Chrome/Edge, funktioniert ohne Einrichtung)

Die Wake-Word-Erkennung läuft im Browser über die **Web Speech API**
(`frontend/src/voice/useWakeWord.ts`):

1. Mikrofon-Button klicken, Freigabe erlauben → kontinuierliche
   Spracherkennung (`SpeechRecognition`) startet.
2. Enthält das Transkript „aphelios", wechselt das HUD in den **aktiven
   Zuhör-Modus** (der Core pulsiert stärker). Steht direkt danach ein Befehl
   („Aphelios, öffne Spotify"), wird der sofort ausgeführt; sonst antwortet
   APHELIOS mit „Ja, Sir?" und hört weiter zu.
3. Nachfolgende Sprache wird als Text an die AI-Konsole übergeben.
4. Ein Stopp-Kommando beendet den Zuhör-Modus.
5. Ist der Sprachmodus aktiv, liest APHELIOS Antworten vor (siehe TTS unten
   und „Wann spricht APHELIOS?").

> Läuft nur in Chromium-basierten Browsern (Chrome/Edge) und nur in einem
> sicheren Kontext (`localhost` oder HTTPS) – NICHT über eine LAN-IP wie
> `192.168.x.x`.

---

## Push-to-Talk (Firefox/Waterfox – oder als Alternative überall)

Erkennt das HUD kein `SpeechRecognition` (z. B. in Firefox/Waterfox), wird
der Mikrofon-Button automatisch zu einem Push-to-Talk-Knopf statt eines
deaktivierten „SPRACHE N/V"-Hinweises:

1. Mikrofon-Button klicken, Freigabe erlauben → Aufnahme startet
   (`MediaRecorder`, Kopfzeile zeigt „● NIMMT AUF").
2. Sprechen, dann den Button erneut klicken → Aufnahme stoppt, wird als
   Base64-Audio an die Backend-VoiceEngine geschickt (`voice.transcribe`,
   faster-whisper).
3. Der erkannte Text geht direkt als Befehl an dieselbe Pipeline wie ein
   Wake-Word-Kommando – **kein** Wake-Word nötig, der Tastendruck selbst ist
   die Aktivierung.
4. Die nächste APHELIOS-Antwort wird einmalig vorgelesen (TTS wie gewohnt).

Braucht zwingend eine konfigurierte faster-whisper-Installation
(`pip install -e ".[voice]"`, siehe unten) – ohne sie erscheint eine rote
Fehlermeldung (`STT: ...`) mit dem genauen Grund, kein stiller Fehlschlag.

Kein Dauer-Zuhören und kein Wake-Word bei Push-to-Talk: jede Aufnahme ist ein
einzelner, bewusst gestarteter Befehl – technisch bräuchte kontinuierliches
Zuhören ohne Wake-Word entweder ein eigenes, lokales Wake-Word-Modell (z. B.
openWakeWord/Porcupine) oder Voice-Activity-Detection, beides bewusst noch
nicht umgesetzt (siehe „Noch nicht umgesetzt" unten).

---

## Wann spricht APHELIOS überhaupt? (Lautsprecher-Button)

APHELIOS liest Antworten standardmäßig **nur im Sprachmodus** vor – also
während Wake-Word aktiv ist, oder als einmalige Antwort direkt nach einem
Push-to-Talk-Befehl. Bei normal getippten Nachrichten antwortet APHELIOS nur
schriftlich, ohne ungefragt vorzulesen.

Zusätzlich gibt es in der AI-Konsole einen eigenen **Lautsprecher-Button**
(neben dem Mikrofon-Button) – ein Klick schaltet dauerhaft um, ob APHELIOS
*jede* Antwort vorliest, unabhängig vom Sprachmodus. So lässt sich
Sprachausgabe auch beim reinen Tippen nutzen, ohne jedes Mal den Sprachmodus
aktivieren zu müssen. Die Kopfzeile der Konsole zeigt „🔊 LAUTSPRECHER AN",
solange der Button aktiv ist. Zustand: `useHud().speakerOn` /
`setSpeakerOn()`.

---

## Sprachausgabe verbessern: Piper (natürliche, tiefe Stimme)

Ohne Einrichtung liest APHELIOS Antworten mit der Standard-Browserstimme vor
(robotisch, aber funktioniert). Mit [Piper](https://github.com/rhasspy/piper)
läuft eine echte neuronale Sprachsynthese **lokal auf deinem PC** – kein
Cloud-Dienst, kein API-Key, keine laufenden Kosten.

### 1 · Installieren

```bash
cd backend
pip install -e ".[voice]"
```

### 2 · Ein deutsches Stimmmodell herunterladen

Modelle liegen bei [rhasspy/piper-voices auf Hugging Face](
https://huggingface.co/rhasspy/piper-voices/tree/main/de/de_DE). Für eine
tiefe männliche Stimme z. B. **`de_DE-thorsten-medium`**:

- `de_DE-thorsten-medium.onnx`
- `de_DE-thorsten-medium.onnx.json`

Beide Dateien in denselben Ordner legen (z. B.
`C:\Users\<DeinBenutzername>\Aphelios\voices\`).

### 3 · In der `.env` eintragen

```bash
APHELIOS_PIPER_MODEL_PATH=C:\Users\<DeinBenutzername>\Aphelios\voices\de_DE-thorsten-medium.onnx
```

Backend neu starten. Die `.onnx.json`-Konfigurationsdatei muss **daneben**
liegen (gleicher Name, `.json` angehängt) – Piper findet sie automatisch.

Fertig: `speak()` im Frontend fragt jetzt zuerst das Backend; antwortet es
(innerhalb von 6 Sekunden) mit Audio, wird das abgespielt. Ohne Antwort
(kein Modell konfiguriert, Backend offline, Timeout) läuft automatisch die
bisherige Browser-Stimme weiter – kein Absturz, kein stummes APHELIOS.

**Fehlerdiagnose:** Meldet das Backend einen echten Fehler (`voice.error`,
z. B. weil der Pfad in `APHELIOS_PIPER_MODEL_PATH` nicht existiert, die
`.onnx.json` fehlt oder `piper-tts` nicht installiert ist), erscheint die
genaue Fehlermeldung rot in der AI-Konsole (Präfix `TTS:`) – zusätzlich zum
automatischen Rückfall auf die Browser-Stimme. Klingt die Stimme trotz
konfiguriertem Pfad weiterhin robotisch, zeigt dieser Text den tatsächlichen
Grund (falscher Pfad, fehlende Datei, Backend nicht neu gestartet nach der
`.env`-Änderung …), statt stumm zu scheitern.

**Häufigste Ursache für „No module named 'piper'" trotz erfolgreichem
`pip install -e ".[voice]"`:** Windows hat zwei verschiedene Python-
Installationen im Spiel – das globale Python und das Projekt-`.venv`. Landet
die Installation im `.venv`, `python -m aphelios` wird aber **ohne**
aktiviertes `.venv` gestartet, läuft der Server mit dem globalen Python, dem
das Paket fehlt. Am zuverlässigsten: `backend\run.bat` verwenden (aktiviert
das `.venv` automatisch, bevor es startet) statt `python -m aphelios` direkt
aufzurufen.

---

## Spracherkennung verbessern: faster-whisper

[faster-whisper](https://github.com/SYSTRAN/faster-whisper) transkribiert
Audio lokal, ohne Cloud-Dienst. Installation:

```bash
cd backend
pip install -e ".[voice]"
```

Kein manueller Modell-Download nötig – beim ersten Gebrauch lädt
faster-whisper das konfigurierte Modell automatisch von Hugging Face
herunter und speichert es lokal zwischen (Standard-Cache:
`~/.cache/huggingface`). Modellgröße über die `.env` wählen (Abwägung
Geschwindigkeit ↔ Genauigkeit):

```bash
APHELIOS_WHISPER_MODEL=base       # tiny/base/small/medium/large-v3
APHELIOS_WHISPER_DEVICE=cpu       # oder "cuda" mit passender NVIDIA-GPU
```

**Frontend-Anbindung:** Die Backend-Transkription (`voice.transcribe` über
den Bus) ist an die Push-to-Talk-Oberfläche angebunden (siehe oben) – aktiv
in jedem Browser ohne `SpeechRecognition` (Firefox/Waterfox), in Chromium
weiterhin nur die Chrome/Edge-eigene Spracherkennung, um das dort bereits
funktionierende Wake-Word-Setup nicht zu verändern.

---

## Bus-Schnittstelle (für eigene Erweiterungen)

* `voice.speak` (in) – `{id, text}` → `voice.audio` (out)
  `{id, audio_base64, sample_rate, format:"wav"}` oder `voice.error` (out)
  `{id, error}`, wenn kein Piper-Modell konfiguriert ist oder die Synthese
  fehlschlägt.
* `voice.transcribe` (in) – `{id, audio_base64}` (beliebiges, von
  PyAV/ffmpeg dekodierbares Format, z. B. was `MediaRecorder` im Browser
  liefert) → `voice.transcript` (out) `{id, text}` oder `voice.error` (out)
  `{id, error}`.

Beide Modelle werden **lazy** geladen (erst bei der ersten Anfrage), damit
ein Start ohne konfigurierte Sprachmodelle nicht durch mehrsekündiges
Modell-Laden verzögert wird.

## Noch nicht umgesetzt (Ausblick)

- **Barge-in**: Unterbrechen der laufenden Sprachausgabe durch neue Sprache.
- **Lokales Wake-Word-Modell für Firefox/Waterfox** (z. B. openWakeWord/
  Porcupine) – würde dort echtes Dauer-Zuhören ohne Tastendruck ermöglichen,
  ist aber ein eigenständiger, deutlich größerer Baustein als Push-to-Talk.
- **Voice-Activity-Detection** für den Dauer-Zuhör-Modus (aktuell übernimmt
  das in Chromium die Web Speech API selbst).
