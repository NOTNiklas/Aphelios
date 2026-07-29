/** Gemeinsame Typen für das HUD und die Bus-Nachrichten. */

export interface SystemStats {
  cpu: { percent: number; cores: number };
  ram: { percent: number; used_gb: number; total_gb: number };
  disk: { percent: number; used_gb: number; total_gb: number };
  gpu: { percent: number } | null;
  vram: { percent: number; used_gb: number; total_gb: number } | null;
  network: { up_kbps: number; down_kbps: number };
  temperature: number | null;
  battery: { percent: number; plugged: boolean } | null;
  timestamp: number;
}

export interface ConsoleMessage {
  id: string;
  role: "user" | "aphelios";
  text: string;
  streaming?: boolean;
}

/** Echte Wetterdaten von der WeatherEngine (Open-Meteo, kein API-Key nötig). */
export interface WeatherData {
  city?: string;
  temperature?: number;
  condition?: string;
  humidity?: number;
  wind_kmh?: number;
  error?: string;
  updated_at: number;
}

/** Echte Gmail-Daten von der MailEngine (optional, braucht Google-OAuth). */
export interface MailData {
  emails?: { from: string; subject: string; snippet: string }[];
  error?: string;
  updated_at: number;
}

/** Echte Termine von der CalendarEngine (optional, braucht Google-OAuth). */
export interface CalendarData {
  events?: { title: string; start: string; location?: string }[];
  error?: string;
  updated_at: number;
}

/** Ein Schritt eines von der PlanningEngine erstellten Plans (Alpha 1.1). */
export interface PlanStep {
  index: number;
  text: string;
  done: boolean;
}

/** Aktueller Plan – ausgelöst über "/plan <Aufgabe>" im Chat. */
export interface PlanData {
  id: string;
  task: string;
  steps: PlanStep[];
  created_at: number;
}

/** Echte Spotify-Wiedergabedaten von der MusicEngine (optional, braucht Spotify-OAuth). */
export interface MusicData {
  connected?: boolean;
  is_playing?: boolean;
  track?: string | null;
  artist?: string | null;
  album?: string | null;
  album_art?: string | null;
  duration_ms?: number | null;
  progress_ms?: number | null;
  volume?: number | null;
  liked?: boolean | null;
  error?: string;
  updated_at: number;
}

export interface ConfirmationRequest {
  id: string;
  action: string;
  level: number;
  level_name: string;
  target: string;
  reason: string;
}

/** Eine Bus-Nachricht, wie sie über den WebSocket eintrifft. */
export interface BusMessage {
  topic: string;
  data: Record<string, unknown>;
  source: string;
}

/** Verbindungszustand zum Backend. */
export type Link = "online" | "connecting" | "offline";
