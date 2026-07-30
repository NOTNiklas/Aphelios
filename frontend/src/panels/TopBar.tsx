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
    <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3 sm:px-6">
      <div className="flex items-center gap-2 sm:gap-3">
        <span className="font-display text-lg tracking-[0.4em] text-hud-neon text-glow">⬡</span>
        <span className="font-display text-xs tracking-[0.5em] text-hud-neon-dim">APHELIOS</span>
        <span className="hidden rounded border border-hud-neon/30 px-2 py-0.5 font-hud text-[10px] tracking-[0.3em] text-hud-neon/60 sm:inline-block">
          ALPHA 1.6
        </span>
      </div>

      <div className="flex items-center gap-3 sm:gap-6">
        <button
          type="button"
          onClick={() => useHud.getState().setTradingOpen(true)}
          className="rounded border border-hud-neon/30 px-2.5 py-1 font-hud text-[11px] tracking-[0.25em] text-hud-neon/70 hover:border-hud-neon/60 hover:text-hud-neon"
          title="Trading-Dashboard öffnen"
        >
          TRADING
        </button>
        <a
          href="/dashboard"
          className="rounded border border-hud-neon/30 px-2.5 py-1 font-hud text-[11px] tracking-[0.25em] text-hud-neon/70 hover:border-hud-neon/60 hover:text-hud-neon"
          title="Web-Dashboard (Agenten-Überwachung) öffnen"
        >
          DASHBOARD
        </a>
        <span className="hidden font-hud text-[11px] tracking-[0.3em] text-hud-neon/60 md:inline">
          AI: {ai === "claude" ? "CLAUDE" : "FALLBACK"}
        </span>
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 shrink-0 rounded-full ${
              link === "online" ? "bg-hud-neon animate-pulse-soft" : "bg-hud-danger"
            }`}
          />
          <span className="hidden font-hud text-[11px] tracking-[0.3em] text-hud-neon-dim sm:inline">
            {link.toUpperCase()}
          </span>
        </div>
        <div className="text-right">
          <div className="font-display text-lg tabular-nums text-hud-neon text-glow sm:text-xl">
            {time}
          </div>
          <div className="hidden font-hud text-[11px] tracking-[0.2em] text-hud-neon/50 sm:block">
            {date}
          </div>
        </div>
      </div>
    </header>
  );
}
