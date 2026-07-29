/** WebSocket-Client zum APHELIOS-Backend – mit Auto-Reconnect und Mock-Fallback.
 *
 * Ist das Backend erreichbar, streamt es ``system.stats`` und Chat-Antworten.
 * Fällt die Verbindung aus, speist der Client realistische Mock-Daten ein und
 * simuliert Chat-Antworten, damit das HUD eigenständig lauffähig bleibt.
 */

import { useEffect } from "react";
import { useHud } from "../store/hud";
import { mockReply, mockStatsMessage } from "./mock";
import type { BusMessage } from "./types";

const WS_URL = `ws://${location.hostname}:8787/ws`;
const RECONNECT_MS = 4000;
const MOCK_TICK_MS = 1500;

/** Ergebnis einer erfolgreichen Backend-Sprachsynthese (VoiceEngine/Piper). */
export interface VoiceAudioResult {
  audioBase64: string;
  sampleRate: number;
}

/** Ergebnis einer ``requestVoiceAudio``-Anfrage – im Fehlerfall inkl. Grund
 * (statt ihn stillschweigend zu verschlucken), damit der Aufrufer entscheiden
 * kann, ob/wie er den Nutzer informiert, bevor er auf die Browser-Stimme
 * zurückfällt. ``error: null`` bedeutet: kein Backend/Timeout (kein
 * konfigurationsrelevanter Fehler, einfach kein Server erreichbar). */
export type VoiceSpeakOutcome =
  | { ok: true; audioBase64: string; sampleRate: number }
  | { ok: false; error: string | null };

/** Ergebnis einer ``requestTranscription``-Anfrage (analog zu
 * ``VoiceSpeakOutcome``, nur für die Sprache-zu-Text-Richtung – gedacht für
 * Push-to-Talk in Browsern ohne Web-Speech-API-Spracherkennung, z. B.
 * Firefox/Waterfox, siehe docs/voice.md). */
export type VoiceTranscribeOutcome =
  | { ok: true; text: string }
  | { ok: false; error: string | null };

class Backend {
  private ws: WebSocket | null = null;
  private mockTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private started = false;
  // Offene "voice.speak"/"voice.transcribe"-Anfragen, auf ihre Antwort
  // wartend (id -> Resolver). Beide Richtungen teilen sich eine Map, weil
  // ``voice.error`` für beide gilt und IDs global eindeutig sind (crypto.
  // randomUUID) – der jeweilige Aufrufer interpretiert die Antwort selbst.
  private voiceWaiters = new Map<string, (msg: BusMessage) => void>();

  start(): void {
    if (this.started) return;
    this.started = true;
    this.connect();
  }

  private connect(): void {
    useHud.getState().setLink("connecting");
    try {
      this.ws = new WebSocket(WS_URL);
    } catch {
      this.goOffline();
      return;
    }

    this.ws.onopen = () => {
      this.stopMock();
      useHud.getState().setLink("online");
    };
    this.ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as BusMessage;
        if (msg.topic === "voice.audio" || msg.topic === "voice.transcript" || msg.topic === "voice.error") {
          this.resolveVoiceWaiter(msg);
          return; // Antwort auf eine gezielte Anfrage, kein globaler Store-Zustand nötig.
        }
        useHud.getState().ingest(msg);
      } catch {
        /* ignoriere unparsbare Nachrichten */
      }
    };
    this.ws.onclose = () => this.goOffline();
    this.ws.onerror = () => this.ws?.close();
  }

  private goOffline(): void {
    useHud.getState().setLink("offline");
    this.startMock();
    if (!this.reconnectTimer) {
      this.reconnectTimer = setTimeout(() => {
        this.reconnectTimer = null;
        this.connect();
      }, RECONNECT_MS);
    }
  }

  private startMock(): void {
    if (this.mockTimer) return;
    const tick = () => useHud.getState().ingest(mockStatsMessage());
    tick();
    this.mockTimer = setInterval(tick, MOCK_TICK_MS);
  }

  private stopMock(): void {
    if (this.mockTimer) {
      clearInterval(this.mockTimer);
      this.mockTimer = null;
    }
  }

  private get online(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  /** Sendet eine Chat-Nachricht (oder simuliert eine Antwort im Offline-Modus). */
  sendChat(text: string): void {
    const id = crypto.randomUUID();
    useHud.getState().addUserMessage(id, text);
    const replyId = crypto.randomUUID();
    if (this.online) {
      this.ws!.send(JSON.stringify({ type: "chat", id: replyId, text }));
    } else {
      this.simulateReply(replyId, mockReply(text));
    }
  }

  /** Togglet einen Plan-Schritt (Checkbox im Aufgaben-Panel). Offline: no-op –
   * ohne Backend gibt es keine PlanningEngine, die den Zustand verwalten könnte. */
  completeStep(index: number): void {
    if (this.online) {
      this.ws!.send(JSON.stringify({ type: "plan.step.complete", index }));
    }
  }

  /** Spotify-Wiedergabesteuerung (Play/Pause/Skip/Lautstärke/Like) – reine
   * Buttons im Musik-Panel, kein Bestätigungsdialog nötig (SAFE-Risikostufe,
   * siehe MusicEngine). Offline: no-op, es gibt ohne Backend keine
   * MusicEngine, die reagieren könnte. */
  musicPlay(): void {
    if (this.online) this.ws!.send(JSON.stringify({ type: "music.play.request" }));
  }
  musicPause(): void {
    if (this.online) this.ws!.send(JSON.stringify({ type: "music.pause.request" }));
  }
  musicNext(): void {
    if (this.online) this.ws!.send(JSON.stringify({ type: "music.next.request" }));
  }
  musicPrevious(): void {
    if (this.online) this.ws!.send(JSON.stringify({ type: "music.previous.request" }));
  }
  musicVolume(level: number): void {
    if (this.online) this.ws!.send(JSON.stringify({ type: "music.volume.request", level }));
  }
  musicLike(liked: boolean): void {
    if (this.online) this.ws!.send(JSON.stringify({ type: "music.like.request", liked }));
  }

  /** Beantwortet eine Sicherheitsabfrage. */
  respondConfirmation(id: string, approve: boolean): void {
    useHud.getState().resolveConfirmation(id);
    if (this.online) {
      this.ws!.send(
        JSON.stringify({ type: approve ? "confirmation.approve" : "confirmation.deny", id }),
      );
    }
  }

  private resolveVoiceWaiter(msg: BusMessage): void {
    const id = String(msg.data.id ?? "");
    const resolve = this.voiceWaiters.get(id);
    if (!resolve) return;
    this.voiceWaiters.delete(id);
    resolve(msg);
  }

  /** Bittet die Backend-VoiceEngine (Piper) um Sprachsynthese. Bei keinem
   * Backend/keiner Antwort (Timeout `timeoutMs`) kommt ``{ok: false, error:
   * null}`` zurück – Aufrufer sollen dann still auf die Browser-Stimme
   * zurückfallen. Bei einem echten Backend-Fehler (z. B. Piper-Modell konnte
   * nicht geladen werden) enthält ``error`` den Grund. */
  requestVoiceAudio(text: string, timeoutMs = 6000): Promise<VoiceSpeakOutcome> {
    return new Promise((resolve) => {
      if (!this.online) {
        resolve({ ok: false, error: null });
        return;
      }
      const id = crypto.randomUUID();
      const timer = setTimeout(() => {
        this.voiceWaiters.delete(id);
        resolve({ ok: false, error: null });
      }, timeoutMs);
      this.voiceWaiters.set(id, (msg) => {
        clearTimeout(timer);
        if (msg.topic === "voice.audio") {
          resolve({
            ok: true,
            audioBase64: String(msg.data.audio_base64 ?? ""),
            sampleRate: Number(msg.data.sample_rate ?? 0),
          });
        } else {
          // voice.error – der Grund wird durchgereicht, statt ihn zu
          // verschlucken; der Aufrufer entscheidet, ob er ihn anzeigt,
          // bevor er auf die Browser-Stimme zurückfällt.
          resolve({ ok: false, error: msg.data.error != null ? String(msg.data.error) : null });
        }
      });
      this.ws!.send(JSON.stringify({ type: "voice.speak", id, text }));
    });
  }

  /** Bittet die Backend-VoiceEngine (faster-whisper) um Transkription einer
   * Audio-Aufnahme (Base64, beliebiges von ffmpeg/PyAV dekodierbares Format –
   * z. B. was `MediaRecorder` liefert). Gedacht als Push-to-Talk-Alternative
   * für Browser ohne Web-Speech-API-Spracherkennung (Firefox/Waterfox),
   * siehe `useWakeWord.ts`. Whisper-Inferenz kann mehrere Sekunden dauern,
   * daher ein spürbar längeres Timeout als bei der TTS-Anfrage. */
  requestTranscription(audioBase64: string, timeoutMs = 20000): Promise<VoiceTranscribeOutcome> {
    return new Promise((resolve) => {
      if (!this.online) {
        resolve({ ok: false, error: null });
        return;
      }
      const id = crypto.randomUUID();
      const timer = setTimeout(() => {
        this.voiceWaiters.delete(id);
        resolve({ ok: false, error: null });
      }, timeoutMs);
      this.voiceWaiters.set(id, (msg) => {
        clearTimeout(timer);
        if (msg.topic === "voice.transcript") {
          resolve({ ok: true, text: String(msg.data.text ?? "") });
        } else {
          resolve({ ok: false, error: msg.data.error != null ? String(msg.data.error) : null });
        }
      });
      this.ws!.send(JSON.stringify({ type: "voice.transcribe", id, audio_base64: audioBase64 }));
    });
  }

  private simulateReply(id: string, text: string): void {
    const words = text.split(" ");
    let i = 0;
    const step = () => {
      if (i >= words.length) {
        useHud.getState().ingest({ topic: "chat.response", data: { id, text }, source: "mock" });
        return;
      }
      useHud
        .getState()
        .ingest({ topic: "chat.token", data: { id, text: words[i] + " " }, source: "mock" });
      i += 1;
      setTimeout(step, 45);
    };
    step();
  }
}

export const backend = new Backend();

// Modul-Singleton statt pro Hook-Aufruf neu erzeugter Closures: hält die
// zurückgegebenen Funktionen über Re-Renders hinweg referenzstabil. Wichtig,
// weil z. B. useWakeWord.ts `requestVoiceAudio` in einer useCallback-
// Abhängigkeitsliste verwendet – bei einer neuen Funktionsidentität pro
// Render würde das den Spracherkennungs-Setup-Effect bei jedem Render neu
// auslösen (Recognition-Instanz unnötig ab-/wieder aufgebaut).
const backendApi = {
  sendChat: (text: string) => backend.sendChat(text),
  completeStep: (index: number) => backend.completeStep(index),
  musicPlay: () => backend.musicPlay(),
  musicPause: () => backend.musicPause(),
  musicNext: () => backend.musicNext(),
  musicPrevious: () => backend.musicPrevious(),
  musicVolume: (level: number) => backend.musicVolume(level),
  musicLike: (liked: boolean) => backend.musicLike(liked),
  respondConfirmation: (id: string, approve: boolean) => backend.respondConfirmation(id, approve),
  requestVoiceAudio: (text: string) => backend.requestVoiceAudio(text),
  requestTranscription: (audioBase64: string) => backend.requestTranscription(audioBase64),
};

/** React-Hook: startet die Backend-Verbindung einmalig. */
export function useBackend() {
  useEffect(() => {
    backend.start();
  }, []);
  return backendApi;
}
