/** Zentraler Zustand des HUD (Zustand-Store). */

import { create } from "zustand";
import type {
  BusMessage,
  CalendarData,
  ConfirmationRequest,
  ConsoleMessage,
  DashboardOverview,
  Link,
  MailData,
  MusicData,
  PlanData,
  StockData,
  SystemStats,
  WeatherData,
} from "../lib/types";

interface HudState {
  link: Link;
  stats: SystemStats | null;
  weather: WeatherData | null;
  mail: MailData | null;
  calendar: CalendarData | null;
  music: MusicData | null;
  stocks: StockData | null;
  dashboardOverview: DashboardOverview | null;
  /** Trading-Dashboard-Popup geöffnet? (TopBar-Button, siehe TradingDashboard.tsx). */
  tradingOpen: boolean;
  /** Aktueller Plan (PlanningEngine, ausgelöst über "/plan <Aufgabe>"). */
  plan: PlanData | null;
  engines: Record<string, string>;
  ai: "claude" | "fallback";
  messages: ConsoleMessage[];
  confirmations: ConfirmationRequest[];
  listening: boolean;
  /** Sprachausgabe (TTS) läuft gerade – für den pulsierenden Core relevant. */
  speaking: boolean;
  /** Lautsprecher-Button: liest APHELIOS Antworten IMMER vor, auch ohne
   * aktiven Sprachmodus (Wake-Word/Push-to-Talk) – unabhängiges, explizites
   * Ein/Aus zusätzlich zum impliziten "während des Sprachmodus sprechen". */
  speakerOn: boolean;

  // -- Aktionen (vom Transport / UI aufgerufen) --
  setLink: (link: Link) => void;
  setTradingOpen: (open: boolean) => void;
  setListening: (listening: boolean) => void;
  setSpeaking: (speaking: boolean) => void;
  setSpeakerOn: (on: boolean) => void;
  ingest: (msg: BusMessage) => void;
  addUserMessage: (id: string, text: string) => void;
  resolveConfirmation: (id: string) => void;
}

export const useHud = create<HudState>((set) => ({
  link: "connecting",
  stats: null,
  weather: null,
  mail: null,
  calendar: null,
  music: null,
  stocks: null,
  dashboardOverview: null,
  tradingOpen: false,
  plan: null,
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
  speaking: false,
  speakerOn: false,

  setLink: (link) => set({ link }),
  setTradingOpen: (open) => set({ tradingOpen: open }),
  setListening: (listening) => set({ listening }),
  setSpeaking: (speaking) => set({ speaking }),
  setSpeakerOn: (on) => set({ speakerOn: on }),

  addUserMessage: (id, text) =>
    set((s) => ({ messages: [...s.messages, { id, role: "user", text }] })),

  resolveConfirmation: (id) =>
    set((s) => ({ confirmations: s.confirmations.filter((c) => c.id !== id) })),

  ingest: (msg) =>
    set((state) => {
      switch (msg.topic) {
        case "system.stats":
          return { stats: msg.data as unknown as SystemStats };

        case "weather.update":
          return { weather: msg.data as unknown as WeatherData };

        case "mail.update":
          return { mail: msg.data as unknown as MailData };

        case "calendar.update":
          return { calendar: msg.data as unknown as CalendarData };

        case "music.update":
          return { music: msg.data as unknown as MusicData };

        case "stock.update":
          return { stocks: msg.data as unknown as StockData };

        case "dashboard.overview":
          return { dashboardOverview: msg.data as unknown as DashboardOverview };

        case "plan.update":
          return { plan: msg.data as unknown as PlanData };

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
