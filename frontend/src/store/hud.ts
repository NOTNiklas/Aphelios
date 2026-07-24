/** Zentraler Zustand des HUD (Zustand-Store). */

import { create } from "zustand";
import type {
  BusMessage,
  ConfirmationRequest,
  ConsoleMessage,
  Link,
  SystemStats,
} from "../lib/types";

interface HudState {
  link: Link;
  stats: SystemStats | null;
  engines: Record<string, string>;
  ai: "claude" | "fallback";
  messages: ConsoleMessage[];
  confirmations: ConfirmationRequest[];
  listening: boolean;

  // -- Aktionen (vom Transport / UI aufgerufen) --
  setLink: (link: Link) => void;
  setListening: (listening: boolean) => void;
  ingest: (msg: BusMessage) => void;
  addUserMessage: (id: string, text: string) => void;
  resolveConfirmation: (id: string) => void;
}

export const useHud = create<HudState>((set) => ({
  link: "connecting",
  stats: null,
  engines: {},
  ai: "fallback",
  messages: [
    {
      id: "boot",
      role: "aphelios",
      text: "APHELIOS initialisiert. Alle Systeme bereit, Sir.",
    },
  ],
  confirmations: [],
  listening: false,

  setLink: (link) => set({ link }),
  setListening: (listening) => set({ listening }),

  addUserMessage: (id, text) =>
    set((s) => ({ messages: [...s.messages, { id, role: "user", text }] })),

  resolveConfirmation: (id) =>
    set((s) => ({ confirmations: s.confirmations.filter((c) => c.id !== id) })),

  ingest: (msg) =>
    set((state) => {
      switch (msg.topic) {
        case "system.stats":
          return { stats: msg.data as unknown as SystemStats };

        case "engine.status":
          return { engines: msg.data as Record<string, string> };

        case "chat.token": {
          const id = String(msg.data.id ?? "");
          const chunk = String(msg.data.text ?? "");
          const messages = [...state.messages];
          const last = messages[messages.length - 1];
          if (last && last.role === "aphelios" && last.id === id && last.streaming) {
            messages[messages.length - 1] = { ...last, text: last.text + chunk };
          } else {
            messages.push({ id, role: "aphelios", text: chunk, streaming: true });
          }
          return { messages };
        }

        case "chat.response": {
          const id = String(msg.data.id ?? "");
          const text = String(msg.data.text ?? "");
          const messages = state.messages.map((m) =>
            m.id === id && m.role === "aphelios" ? { ...m, text, streaming: false } : m,
          );
          return { messages };
        }

        case "confirmation.request":
          return {
            confirmations: [
              ...state.confirmations,
              msg.data as unknown as ConfirmationRequest,
            ],
          };

        default:
          return {};
      }
    }),
}));
