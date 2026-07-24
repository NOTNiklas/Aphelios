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

class Backend {
  private ws: WebSocket | null = null;
  private mockTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private started = false;

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

  /** Beantwortet eine Sicherheitsabfrage. */
  respondConfirmation(id: string, approve: boolean): void {
    useHud.getState().resolveConfirmation(id);
    if (this.online) {
      this.ws!.send(
        JSON.stringify({ type: approve ? "confirmation.approve" : "confirmation.deny", id }),
      );
    }
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

/** React-Hook: startet die Backend-Verbindung einmalig. */
export function useBackend() {
  useEffect(() => {
    backend.start();
  }, []);
  return {
    sendChat: (text: string) => backend.sendChat(text),
    respondConfirmation: (id: string, approve: boolean) =>
      backend.respondConfirmation(id, approve),
  };
}
