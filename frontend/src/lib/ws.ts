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

class Backend {
  private ws: WebSocket | null = null;
  private mockTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private started = false;
  // Offene "/voice.speak"-Anfragen, auf ihre Antwort wartend (id -> Resolver).
  private voiceWaiters = new Map<string, (result: VoiceAudioResult | null) => void>();

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
        if (msg.topic === "voice.audio" || msg.topic === "voice.error") {
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
    if (msg.topic === "voice.audio") {
      resolve({
        audioBase64: String(msg.data.audio_base64 ?? ""),
        sampleRate: Number(msg.data.sample_rate ?? 0),
      });
    } else {
      resolve(null); // voice.error – Aufrufer fällt auf Browser-TTS zurück
    }
  }

  /** Bittet die Backend-VoiceEngine (Piper) um Sprachsynthese. Gibt ``null``
   * zurück, wenn kein Backend/keine Antwort/kein Piper-Modell verfügbar ist
   * (Timeout `timeoutMs`) – Aufrufer sollen dann auf die Browser-Stimme
   * zurückfallen, statt den Nutzer stumm zu lassen. */
  requestVoiceAudio(text: string, timeoutMs = 6000): Promise<VoiceAudioResult | null> {
    return new Promise((resolve) => {
      if (!this.online) {
        resolve(null);
        return;
      }
      const id = crypto.randomUUID();
      const timer = setTimeout(() => {
        this.voiceWaiters.delete(id);
        resolve(null);
      }, timeoutMs);
      this.voiceWaiters.set(id, (result) => {
        clearTimeout(timer);
        resolve(result);
      });
      this.ws!.send(JSON.stringify({ type: "voice.speak", id, text }));
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
  respondConfirmation: (id: string, approve: boolean) => backend.respondConfirmation(id, approve),
  requestVoiceAudio: (text: string) => backend.requestVoiceAudio(text),
};

/** React-Hook: startet die Backend-Verbindung einmalig. */
export function useBackend() {
  useEffect(() => {
    backend.start();
  }, []);
  return backendApi;
}
