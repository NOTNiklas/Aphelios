/** Realistische Mock-Daten, damit das HUD auch ohne Backend läuft. */

import type { BusMessage, SystemStats } from "./types";

// Ein sanft schwankender Zufallswert um eine Basis herum.
function wander(base: number, spread: number, min = 0, max = 100): number {
  const v = base + (Math.random() - 0.5) * spread;
  return Math.round(Math.max(min, Math.min(max, v)) * 10) / 10;
}

export function mockStats(): SystemStats {
  return {
    cpu: { percent: wander(28, 24), cores: 16 },
    ram: { percent: wander(46, 8), used_gb: wander(14.7, 2, 0, 32), total_gb: 32 },
    disk: { percent: 63.2, used_gb: 606, total_gb: 1000 },
    gpu: { percent: wander(35, 30) },
    vram: { percent: wander(41, 12), used_gb: wander(3.3, 1, 0, 8), total_gb: 8 },
    network: { up_kbps: wander(120, 220, 0, 5000), down_kbps: wander(880, 900, 0, 20000) },
    temperature: wander(52, 8, 30, 90),
    battery: { percent: wander(87, 2, 0, 100), plugged: true },
    timestamp: Date.now() / 1000,
  };
}

/** Mock-Info-Panels (rechte Spalte). */
export const MOCK_INFO = {
  kalender: [
    { time: "09:30", title: "Standup – Team Aphelios" },
    { time: "13:00", title: "Design Review" },
    { time: "16:15", title: "1:1 mit Niklas" },
  ],
  mails: [
    { from: "GitHub", subject: "PR #42 wartet auf Review" },
    { from: "Netlify", subject: "Deploy erfolgreich" },
  ],
  aufgaben: [
    { done: false, title: "Voice-Engine anbinden" },
    { done: false, title: "Vision-OCR testen" },
    { done: true, title: "HUD-Prototyp fertigstellen" },
  ],
  benachrichtigungen: [
    { title: "Backup abgeschlossen", level: "ok" },
    { title: "Update für Docker verfügbar", level: "info" },
  ],
};

/** Eine Fallback-Antwort, die zeichenweise „gestreamt" wird. */
export function mockReply(text: string): string {
  const t = text.toLowerCase();
  if (/(hallo|hi|hey|aphelios)/.test(t)) return "Systeme online. Ich bin bereit, Sir.";
  if (/cpu|auslastung|system/.test(t))
    return "Alle Systemwerte im grünen Bereich. Die CPU-Last ist stabil.";
  return (
    "Offline-Modus aktiv – es ist kein Backend verbunden. Starte das APHELIOS-" +
    "Backend (python -m aphelios), und ich verarbeite deine Anfragen live."
  );
}

/** Erzeugt einen Strom von Mock-Bus-Nachrichten (Stats) für den Fallback. */
export function mockStatsMessage(): BusMessage {
  return { topic: "system.stats", data: mockStats() as unknown as Record<string, unknown>, source: "mock" };
}
