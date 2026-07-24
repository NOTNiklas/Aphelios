/** Sprachaktivierung „Aphelios" über die Web Speech API (Browser).
 *
 * Ablauf (siehe docs/voice.md):
 *   1. Kontinuierliche Spracherkennung.
 *   2. Fällt das Wort „aphelios", wechselt das HUD in den aktiven Zuhör-Modus.
 *   3. Nachfolgende Sprache wird als Befehl an die AI-Konsole übergeben.
 *   4. Stopp-Kommandos ("stop", "danke aphelios", "beenden", "ruhemodus")
 *      beenden den Zuhör-Modus.
 *
 * Die Web Speech API wird von Chromium/Chrome-basierten Browsern unterstützt.
 * In der späteren Tauri-Desktop-App ersetzt die Backend-VoiceEngine diese Basis.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useHud } from "../store/hud";

const WAKE = "aphelios";
const STOP_WORDS = ["stop", "danke aphelios", "beenden", "ruhemodus"];

// Minimal-Typen für die (noch nicht überall standardisierte) Web Speech API.
type SR = typeof window & {
  SpeechRecognition?: new () => SpeechRecognitionLike;
  webkitSpeechRecognition?: new () => SpeechRecognitionLike;
};
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

export function useWakeWord(onCommand: (text: string) => void) {
  const [supported, setSupported] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const setListening = useHud((s) => s.setListening);

  const speak = useCallback((text: string) => {
    if (!("speechSynthesis" in window)) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "de-DE";
    u.rate = 0.98;
    u.pitch = 0.9; // etwas tiefer
    window.speechSynthesis.speak(u);
  }, []);

  useEffect(() => {
    const w = window as SR;
    const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
    if (!Ctor) return;
    setSupported(true);

    const rec = new Ctor();
    rec.lang = "de-DE";
    rec.continuous = true;
    rec.interimResults = false;

    rec.onresult = (e) => {
      const last = e.results[e.results.length - 1];
      const transcript = (last[0]?.transcript ?? "").trim().toLowerCase();
      if (!transcript) return;

      if (!useHud.getState().listening) {
        if (transcript.includes(WAKE)) {
          setListening(true);
          speak("Ja, Sir?");
        }
        return;
      }
      // Bereits im Zuhör-Modus:
      if (STOP_WORDS.some((w2) => transcript.includes(w2))) {
        setListening(false);
        speak("Ruhemodus.");
        return;
      }
      onCommand(transcript);
    };

    rec.onend = () => {
      // Neustart, solange aktiviert (kontinuierliches Zuhören).
      if (recRef.current && useHud.getState().listening !== undefined && enabledRef.current) {
        try {
          rec.start();
        } catch {
          /* bereits gestartet */
        }
      }
    };

    recRef.current = rec;
    return () => {
      rec.onresult = null;
      rec.onend = null;
      try {
        rec.stop();
      } catch {
        /* egal */
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Halte den aktuellen enabled-Wert für onend verfügbar.
  const enabledRef = useRef(enabled);
  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);

  const toggle = useCallback(() => {
    const rec = recRef.current;
    if (!rec) return;
    setEnabled((prev) => {
      const next = !prev;
      try {
        if (next) rec.start();
        else {
          rec.stop();
          setListening(false);
        }
      } catch {
        /* Start/Stop-Zustand ignorieren */
      }
      return next;
    });
  }, [setListening]);

  return { supported, enabled, toggle };
}
