/** Sprachaktivierung „Aphelios" + Sprachausgabe über die Web Speech API.
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
 * Wichtig: Die Web Speech API läuft nur in Chromium-basierten Browsern
 * (Chrome/Edge) und nur in einem sicheren Kontext (``localhost`` oder HTTPS) –
 * NICHT über eine LAN-IP wie ``192.168.x.x``. In der späteren Tauri-Desktop-
 * App ersetzt die Backend-VoiceEngine diese Basis.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useHud } from "../store/hud";

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
}

export function useWakeWord(onCommand: (text: string) => void): VoiceApi {
  const [supported, setSupported] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const enabledRef = useRef(false);
  const cmdRef = useRef(onCommand);

  // onCommand stabil halten, ohne das Setup-Effect neu auszulösen.
  useEffect(() => {
    cmdRef.current = onCommand;
  }, [onCommand]);

  // -- Sprachausgabe (TTS) ---------------------------------------------------
  const speak = useCallback((text: string) => {
    if (!("speechSynthesis" in window) || !text.trim()) return;
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
        enabledRef.current &&
        last &&
        last.role === "aphelios" &&
        !last.streaming &&
        seenStreaming.has(last.id) &&
        !spoken.has(last.id)
      ) {
        spoken.add(last.id);
        speak(last.text);
      }
    });
  }, [speak]);

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

  return { supported, enabled, error, toggle };
}
