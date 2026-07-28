# Sprache – Wake-Word, Sprachausgabe (TTS) und Spracherkennung (STT)

## Ziel

Aktivierungswort **„Aphelios"**. Danach hört das Mikrofon dauerhaft zu, bis eines der
Stopp-Kommandos fällt: „Stop", „Danke Aphelios", „Beenden", „Ruhemodus".

Die Stimme soll natürlich, ruhig und leicht tief (männlich) klingen, mit klarer
Aussprache und geringer Latenz.

APHELIOS hat zwei getrennte Sprach-Bausteine, die zusammenspielen:

| Baustein | Läuft wo? | Technik | Braucht Einrichtung? |
|---|---|---|---|
| Wake-Word „Aphelios" + Dauer-Zuhören | Browser | Web Speech API | Nein – Mikrofon-Button klicken, fertig |
| Sprachausgabe (TTS) | Backend, Fallback im Browser | Piper (lokal) → Browser-Stimme | Optional (siehe unten) |
| Spracherkennung (STT) | Backend | faster-whisper (lokal) | Optional, kein manueller Download nötig |

**Grundsatz:** Ohne jede Einrichtung funktioniert alles wie in Alpha 1.0/1.1 –
Wake-Word läuft im Browser, Antworten werden mit der (robotischen)
Browser-Stimme vorgelesen. Die Ausbaustufen unten verbessern nur die
**Qualität**, nichts wird dadurch kaputter oder Pflicht.

---

## Wake-Word & Dauer-Zuhören (funktioniert ohne Einrichtung)

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
5. Ist der Sprachmodus aktiv, liest APHELIOS Antworten vor (siehe TTS unten).

> Läuft nur in Chromium-basierten Browsern (Chrome/Edge) und nur in einem
> sicheren Kontext (`localhost` oder HTTPS) – NICHT über eine LAN-IP wie
> `192.168.x.x`.

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

**Alpha 1.3 (erste Ausbaustufe):** Die Backend-Transkription
(`voice.transcribe` über den Bus) ist fertig und getestet, aber noch **nicht**
an eine Aufnahme-Oberfläche im Frontend angebunden (z. B. ein
„Gedrückt-halten-zum-Sprechen"-Button) – die kontinuierliche
Wake-Word-Erkennung läuft weiterhin über die bewährte Web Speech API des
Browsers, um das bereits funktionierende Setup nicht zu riskieren. Die
Backend-Transkription steht damit als Baustein für eine spätere
Push-to-Talk-Oberfläche bereit.

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
- **Voice-Activity-Detection** für den Dauer-Zuhör-Modus (aktuell übernimmt
  das die Web Speech API selbst).
- **Push-to-Talk-Oberfläche** im Frontend für `voice.transcribe` (siehe oben).
