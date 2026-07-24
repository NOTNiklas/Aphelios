/** Schmale Kopfzeile mit Uhrzeit, Datum und Verbindungsstatus. */
import { useEffect, useState } from "react";
import { useHud } from "../store/hud";

export function TopBar() {
  const [now, setNow] = useState(new Date());
  const link = useHud((s) => s.link);
  const ai = useHud((s) => s.ai);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const time = now.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const date = now.toLocaleDateString("de-DE", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  });

  return (
    <header className="flex items-center justify-between px-6 py-3">
      <div className="flex items-center gap-3">
        <span className="font-display text-lg tracking-[0.4em] text-hud-neon text-glow">⬡</span>
        <span className="font-display text-xs tracking-[0.5em] text-hud-neon-dim">APHELIOS</span>
        <span className="rounded border border-hud-neon/30 px-2 py-0.5 font-hud text-[10px] tracking-[0.3em] text-hud-neon/60">
          ALPHA 1.0
        </span>
      </div>

      <div className="flex items-center gap-6">
        <span className="font-hud text-[11px] tracking-[0.3em] text-hud-neon/60">
          AI: {ai === "claude" ? "CLAUDE" : "FALLBACK"}
        </span>
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${
              link === "online" ? "bg-hud-neon animate-pulse-soft" : "bg-hud-danger"
            }`}
          />
          <span className="font-hud text-[11px] tracking-[0.3em] text-hud-neon-dim">
            {link.toUpperCase()}
          </span>
        </div>
        <div className="text-right">
          <div className="font-display text-xl tabular-nums text-hud-neon text-glow">{time}</div>
          <div className="font-hud text-[11px] tracking-[0.2em] text-hud-neon/50">{date}</div>
        </div>
      </div>
    </header>
  );
}
