/** Sprachaktivierung „Aphelios" + Sprachausgabe.
 *
 * Ablauf (siehe docs/voice.md):
 *   1. Mikrofon-Button aktivieren → kontinuierliche Spracherkennung startet.
 *   2. Fällt das Wort „aphelios", wechselt das HUD in den aktiven Zuhör-Modus.
 *      Steht direkt danach ein Befehl („Aphelios, öffne Spotify"), wird dieser
 *      sofort ausgeführt.
 *   3. Weitere Sprache wird als Befehl an die AI-Konsole übergeben.
 *   4. Stopp-Kommandos ("stop", "danke aphelios", "beenden", "ruhemodus")
 *      beenden den Zuhör-Modus.
 *   5. Ist der Sprachmodus aktiv, liest APHELIOS seine Antworten vor (TTS) –
 *      solange spricht der Core-Kreis sichtbar mit (``speaking``-Zustand).
 *
 * **Sprachausgabe (Alpha 1.3):** ``speak()`` fragt zuerst die Backend-
 * VoiceEngine (Piper – natürliche, tiefe Stimme, siehe docs/voice.md). Antwortet
 * das Backend nicht rechtzeitig (kein Piper-Modell konfiguriert, Backend
 * offline, Timeout), fällt automatisch die Browser-``speechSynthesis``-Stimme
 * ein – das HUD bleibt also immer sprachfähig, nur eben mit unterschiedlicher
 * Qualität, je nachdem was verfügbar ist.
 *
 * Wichtig: Die Web-Speech-API-Spracherkennung (Wake-Word) läuft nur in
 * Chromium-basierten Browsern (Chrome/Edge) und nur in einem sicheren Kontext
 * (``localhost`` oder HTTPS) – NICHT über eine LAN-IP wie ``192.168.x.x``.
 * Firefox-basierte Browser (Firefox, **Waterfox**, LibreWolf, …) implementieren
 * ``SpeechRecognition`` grundsätzlich nicht (Gecko-Einschränkung, nicht von
 * APHELIOS aus behebbar) – kein Wake-Word, kein Dauer-Zuhören dort möglich.
 *
 * **Push-to-Talk (Alpha 1.3, Ausbaustufe):** Für genau diesen Fall (kein
 * ``SpeechRecognition``, aber ein Mikrofon vorhanden) gibt es eine
 * Push-to-Talk-Alternative über ``MediaRecorder`` + die bereits vorhandene
 * Backend-VoiceEngine (``voice.transcribe``, faster-whisper lokal) – braucht
 * keine Browser-Spracherkennung, funktioniert deshalb auch in Waterfox. Ohne
 * Wake-Word: ein Tastendruck startet die Aufnahme, ein zweiter beendet sie und
 * schickt sie zur Transkription; der erkannte Text geht direkt als Befehl an
 * dieselbe Pipeline wie ein Wake-Word-Kommando. Die nächste APHELIOS-Antwort
 * wird danach einmalig vorgelesen (ohne dauerhaften "Sprachmodus"-Zustand –
 * der ergibt bei Push-to-Talk keinen Sinn, da nichts kontinuierlich zuhört).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useBackend } from "../lib/ws";
import { useHud } from "../store/hud";

/** Dekodiert Backend-Audio (Base64-WAV) und spielt es ab. Löst auf, sobald
 * die Wiedergabe beendet ist (oder fehlschlägt) – Aufrufer kann darauf warten,
 * um den ``speaking``-Zustand exakt so lange wie die tatsächliche Wiedergabe zu halten. */
function playBase64Wav(base64: string): Promise<HTMLAudioElement> {
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  const blob = new Blob([bytes], { type: "audio/wav" });
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  audio.addEventListener("ended", () => URL.revokeObjectURL(url), { once: true });
  audio.addEventListener("error", () => URL.revokeObjectURL(url), { once: true });
  return audio.play().then(() => audio);
}

/** Liest einen Blob als Base64 (ohne den ``data:...;base64,``-Präfix) –
 * gebraucht, um eine MediaRecorder-Aufnahme an ``voice.transcribe`` zu
 * schicken (derselbe Bus-Kanal erwartet Base64, wie auch ``voice.audio``
 * eines liefert). */
function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = String(reader.result ?? "");
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

const WAKE = "aphelios";
const STOP_WORDS = ["danke aphelios", "ruhemodus", "beenden", "stop"];

// Minimal-Typen für die (noch nicht überall standardisierte) Web Speech API.
type WindowWithSR = typeof window & {
  SpeechRecognition?: new () => SpeechRecognitionLike;
  webkitSpeechRecognition?: new () => SpeechRecognitionLike;
};
interface SpeechResultEvent {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
}
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: SpeechResultEvent) => void) | null;
  onerror: ((e: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

export interface VoiceApi {
  supported: boolean;
  enabled: boolean;
  error: string | null;
  toggle: () => void;
  /** Push-to-Talk-Alternative für Browser ohne ``SpeechRecognition``
   * (Firefox/Waterfox) – true, wenn Mikrofon-Aufnahme (MediaRecorder)
   * grundsätzlich verfügbar ist. */
  pushToTalkSupported: boolean;
  /** true während einer laufenden Push-to-Talk-Aufnahme. */
  recording: boolean;
  /** Startet/beendet eine Push-to-Talk-Aufnahme. */
  togglePushToTalk: () => void;
}

export function useWakeWord(onCommand: (text: string) => void): VoiceApi {
  const [supported, setSupported] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);

  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const enabledRef = useRef(false);
  const cmdRef = useRef(onCommand);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  // Nach einem per Push-to-Talk gesendeten Befehl soll GENAU die nächste
  // APHELIOS-Antwort vorgelesen werden, auch ohne dauerhaft aktiven
  // Sprachmodus (der bei Push-to-Talk keinen Sinn ergibt).
  const pendingSpokenReplyRef = useRef(false);
  const { requestVoiceAudio, requestTranscription } = useBackend();

  const pushToTalkSupported =
    typeof window !== "undefined" &&
    typeof MediaRecorder !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia;

  // onCommand stabil halten, ohne das Setup-Effect neu auszulösen.
  useEffect(() => {
    cmdRef.current = onCommand;
  }, [onCommand]);

  // -- Sprachausgabe: Browser-Stimme (Fallback ohne/bei fehlgeschlagenem Backend) --
  const speakBrowser = useCallback((text: string) => {
    if (!("speechSynthesis" in window)) {
      useHud.getState().setSpeaking(false);
      return;
    }
    const synth = window.speechSynthesis;
    synth.cancel(); // laufende Ausgabe abbrechen (kein Überlappen)

    const u = new SpeechSynthesisUtterance(text);
    u.lang = "de-DE";
    u.rate = 1.0;
    u.pitch = 0.85; // etwas tiefer, ruhiger
    const voices = synth.getVoices();
    const de =
      voices.find(
        (v) => /de[-_]/i.test(v.lang) && /male|männ|stefan|markus|conrad/i.test(v.name),
      ) ?? voices.find((v) => /de[-_]/i.test(v.lang));
    if (de) u.voice = de;

    u.onstart = () => useHud.getState().setSpeaking(true);
    u.onend = () => useHud.getState().setSpeaking(false);
    u.onerror = () => useHud.getState().setSpeaking(false);

    synth.speak(u);
  }, []);

  // -- Sprachausgabe: versucht zuerst die Backend-VoiceEngine (Piper) -----------
  const speak = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;

      // Laufende Wiedergabe (Backend-Audio ODER Browser-Stimme) abbrechen,
      // damit sich aufeinanderfolgende Antworten nicht überlappen.
      currentAudioRef.current?.pause();
      currentAudioRef.current = null;
      try {
        window.speechSynthesis?.cancel();
      } catch {
        /* egal */
      }

      requestVoiceAudio(trimmed).then((outcome) => {
        if (!outcome.ok) {
          // Ein echter Backend-Fehler (z. B. Piper-Modell konnte nicht
          // geladen werden) soll sichtbar sein, statt stillschweigend im
          // Browser-Fallback zu verschwinden – sonst bleibt für den Nutzer
          // für immer unklar, warum die konfigurierte Stimme nie erklingt.
          // `error: null` bedeutet dagegen nur "kein Backend/Timeout" – das
          // ist im Offline-Modus normal und keine Fehlermeldung wert.
          if (outcome.error) setError(`TTS: ${outcome.error}`);
          speakBrowser(trimmed);
          return;
        }
        useHud.getState().setSpeaking(true);
        playBase64Wav(outcome.audioBase64)
          .then((audio) => {
            currentAudioRef.current = audio;
            audio.addEventListener(
              "ended",
              () => {
                if (currentAudioRef.current === audio) currentAudioRef.current = null;
                useHud.getState().setSpeaking(false);
              },
              { once: true },
            );
          })
          .catch(() => {
            // Wiedergabe fehlgeschlagen (z. B. Autoplay-Policy) → Browser-Stimme.
            useHud.getState().setSpeaking(false);
            speakBrowser(trimmed);
          });
      });
    },
    [requestVoiceAudio, speakBrowser],
  );

  // -- Spracherkennung einrichten (einmalig) --------------------------------
  useEffect(() => {
    const w = window as WindowWithSR;
    const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
    if (!Ctor) {
      setSupported(false);
      return;
    }
    setSupported(true);

    const rec = new Ctor();
    rec.lang = "de-DE";
    rec.continuous = true;
    rec.interimResults = false;

    rec.onresult = (e) => {
      const last = e.results[e.results.length - 1];
      const raw = (last[0]?.transcript ?? "").trim();
      const t = raw.toLowerCase();
      if (!t) return;
      const state = useHud.getState();

      if (!state.listening) {
        const idx = t.indexOf(WAKE);
        if (idx === -1) return; // Wake-Word nicht gefallen
        state.setListening(true);
        setError(null);
        // Text direkt nach „aphelios" als sofortigen Befehl behandeln.
        const rest = raw
          .slice(idx + WAKE.length)
          .replace(/^[\s,.:!?–-]+/, "")
          .trim();
        if (rest.length >= 2) cmdRef.current(rest);
        else speak("Ja, Sir?");
        return;
      }

      // Bereits im Zuhör-Modus:
      if (STOP_WORDS.some((word) => t.includes(word))) {
        state.setListening(false);
        speak("Ruhemodus.");
        return;
      }
      cmdRef.current(raw);
    };

    rec.onerror = (ev) => {
      const err = ev?.error ?? "unknown";
      if (err === "no-speech" || err === "aborted") return; // harmlos → onend startet neu
      if (err === "not-allowed" || err === "service-not-allowed") {
        enabledRef.current = false;
        setEnabled(false);
        useHud.getState().setListening(false);
        setError("Mikrofon-Zugriff verweigert – bitte im Browser erlauben.");
      } else if (err === "network") {
        setError("Sprachdienst nicht erreichbar (Internetverbindung prüfen).");
      } else {
        setError(`Sprachfehler: ${err}`);
      }
    };

    // Kontinuierliches Zuhören: nach automatischem Ende neu starten.
    rec.onend = () => {
      if (enabledRef.current) {
        try {
          rec.start();
        } catch {
          /* bereits aktiv */
        }
      }
    };

    recRef.current = rec;
    return () => {
      rec.onresult = null;
      rec.onerror = null;
      rec.onend = null;
      try {
        rec.stop();
      } catch {
        /* egal */
      }
    };
  }, [speak]);

  // -- Antworten vorlesen, sobald sie fertig gestreamt sind -----------------
  useEffect(() => {
    const seenStreaming = new Set<string>();
    const spoken = new Set<string>();
    let prev = useHud.getState().messages;

    return useHud.subscribe((state) => {
      if (state.messages === prev) return;
      prev = state.messages;
      for (const m of state.messages) {
        if (m.role === "aphelios" && m.streaming) seenStreaming.add(m.id);
      }
      const last = state.messages[state.messages.length - 1];
      if (
        (enabledRef.current || pendingSpokenReplyRef.current) &&
        last &&
        last.role === "aphelios" &&
        !last.streaming &&
        seenStreaming.has(last.id) &&
        !spoken.has(last.id)
      ) {
        spoken.add(last.id);
        pendingSpokenReplyRef.current = false;
        speak(last.text);
      }
    });
  }, [speak]);

  // -- Push-to-Talk: Aufnahme über MediaRecorder + Backend-Whisper ----------
  // Alternative zu SpeechRecognition für Browser, die dieses API nicht
  // implementieren (Firefox/Waterfox) – kein Wake-Word, ein Tastendruck
  // startet/beendet die Aufnahme.
  const startPushToTalk = useCallback(async () => {
    if (!pushToTalkSupported || mediaRecorderRef.current) return;
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        useHud.getState().setListening(false);
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        blobToBase64(blob)
          .then((base64) => requestTranscription(base64))
          .then((outcome) => {
            if (outcome.ok && outcome.text.trim()) {
              pendingSpokenReplyRef.current = true;
              cmdRef.current(outcome.text.trim());
            } else if (!outcome.ok && outcome.error) {
              setError(`STT: ${outcome.error}`);
            }
          })
          .catch(() => setError("Transkription fehlgeschlagen."));
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
      useHud.getState().setListening(true);
    } catch {
      setError("Mikrofon-Zugriff verweigert – bitte im Browser erlauben.");
    }
  }, [pushToTalkSupported, requestTranscription]);

  const stopPushToTalk = useCallback(() => {
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current = null;
    setRecording(false);
  }, []);

  const togglePushToTalk = useCallback(() => {
    if (mediaRecorderRef.current) stopPushToTalk();
    else void startPushToTalk();
  }, [startPushToTalk, stopPushToTalk]);

  // -- An/Aus schalten (Seiteneffekte NICHT im State-Updater!) --------------
  const toggle = useCallback(() => {
    const rec = recRef.current;
    if (!rec) return;
    setError(null);
    if (enabledRef.current) {
      enabledRef.current = false;
      setEnabled(false);
      useHud.getState().setListening(false);
      try {
        rec.stop();
      } catch {
        /* egal */
      }
      try {
        window.speechSynthesis?.cancel();
      } catch {
        /* egal */
      }
      currentAudioRef.current?.pause();
      currentAudioRef.current = null;
      useHud.getState().setSpeaking(false);
    } else {
      enabledRef.current = true;
      setEnabled(true);
      try {
        rec.start();
      } catch {
        /* evtl. schon gestartet */
      }
    }
  }, []);

  return { supported, enabled, error, toggle, pushToTalkSupported, recording, togglePushToTalk };
}
