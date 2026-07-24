# Voice-System

## Ziel

Aktivierungswort **„Aphelios"**. Danach hört das Mikrofon dauerhaft zu, bis eines der
Stopp-Kommandos fällt:

- „Stop"
- „Danke Aphelios"
- „Beenden"
- „Ruhemodus"

Die Stimme soll natürlich, ruhig und leicht tief (männlich) klingen, mit klarer
Aussprache und geringer Latenz.

## Alpha 1.0 (Basis)

Die Wake-Word-Erkennung läuft im Browser über die **Web Speech API**
(`frontend/src/voice/useWakeWord.ts`):

1. Kontinuierliche Spracherkennung (`SpeechRecognition`).
2. Enthält das Transkript „aphelios", wechselt das HUD in den **aktiven Zuhör-Modus**
   (der Core pulsiert stärker).
3. Nachfolgende Sprache wird als Text an die AI-Konsole übergeben.
4. Ein Stopp-Kommando beendet den Zuhör-Modus.
5. Antworten werden per `SpeechSynthesis` (Browser-TTS) vorgelesen – als Platzhalter
   für die spätere hochwertige Stimme.

> Die Web Speech API wird von Chromium/Chrome-basierten Browsern unterstützt. In der
> späteren Tauri-Desktop-App wird sie durch die native Voice-Pipeline ersetzt.

## Ausbaustufe (siehe Roadmap Alpha 1.3)

Der Backend-`VoiceEngine`-Stub (`backend/aphelios/engines/voice_engine.py`) definiert
bereits die Schnittstelle für:

- **STT**: Whisper (lokal oder API) für robuste Erkennung.
- **TTS**: hochwertige Engine mit natürlicher, tiefer männlicher Stimme, Betonung und
  Emotion, Streaming für geringe Latenz.
- **Barge-in**: Unterbrechen der Ausgabe durch neue Sprache.
- **Voice-Activity-Detection** für den Dauer-Zuhör-Modus.

Die Engine kommuniziert über den EventBus (`voice.transcript`, `voice.speak`), sodass
Frontend-Basis und späteres Backend-Voice austauschbar sind.
