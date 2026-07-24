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
