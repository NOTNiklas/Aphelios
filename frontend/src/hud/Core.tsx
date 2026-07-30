/** Der animierte Kern-Kreis: pulsiert, während APHELIOS antwortet, spricht oder zuhört. */
import { motion, useReducedMotion } from "framer-motion";
import { Ring } from "./Ring";
import { useHud } from "../store/hud";

const TICKS = Array.from({ length: 60 });

export function Core() {
  const reduce = useReducedMotion();
  const listening = useHud((s) => s.listening);
  const speaking = useHud((s) => s.speaking);
  const link = useHud((s) => s.link);
  const answering = useHud((s) =>
    s.messages.some((m) => m.role === "aphelios" && m.streaming),
  );

  // "Aktiv" = APHELIOS tut gerade etwas Sichtbares/Hörbares.
  const active = answering || speaking || listening;

  const statusLabel = speaking
    ? "SPRICHT"
    : answering
      ? "ANTWORTET"
      : listening
        ? "HÖRT ZU"
        : link === "online"
          ? "ONLINE"
          : link === "connecting"
            ? "VERBINDE"
            : "OFFLINE";

  return (
    <div className="relative flex h-[min(60vh,540px)] w-[min(60vh,540px)] items-center justify-center">
      {/* Rotierende Ringe (verschiedene Geschwindigkeiten & Richtungen). */}
      <Ring size={520} duration={60} dash="2 14" width={1} opacity={0.35} />
      <Ring size={440} duration={40} reverse dash="60 24" width={2} opacity={active ? 0.8 : 0.55} />
      <Ring size={360} duration={28} dash="4 8" width={1.5} opacity={0.5} />
      <Ring size={300} duration={18} reverse dash="90 30" width={2.5} opacity={active ? 0.9 : 0.7} />

      {/* Tick-Skala (statisch). */}
      <svg className="absolute" width={490} height={490} viewBox="0 0 490 490">
        {TICKS.map((_, i) => {
          const angle = (i / TICKS.length) * Math.PI * 2;
          const long = i % 5 === 0;
          const outer = 240;
          const inner = outer - (long ? 12 : 6);
          const cx = 245;
          return (
            <line
              key={i}
              x1={cx + Math.cos(angle) * inner}
              y1={cx + Math.sin(angle) * inner}
              x2={cx + Math.cos(angle) * outer}
              y2={cx + Math.sin(angle) * outer}
              stroke="#00ff88"
              strokeWidth={long ? 1.6 : 0.8}
              opacity={long ? 0.7 : 0.35}
            />
          );
        })}
      </svg>

      {/* Expandierende Puls-Ringe, solange APHELIOS antwortet oder spricht. */}
      {(answering || speaking) && !reduce && (
        <>
          <motion.span
            className="absolute h-64 w-64 rounded-full border-2 border-hud-neon"
            initial={{ scale: 0.7, opacity: 0.55 }}
            animate={{ scale: 1.6, opacity: 0 }}
            transition={{ duration: 1.3, ease: "easeOut", repeat: Infinity }}
          />
          <motion.span
            className="absolute h-64 w-64 rounded-full border border-hud-neon/70"
            initial={{ scale: 0.7, opacity: 0.4 }}
            animate={{ scale: 1.6, opacity: 0 }}
            transition={{ duration: 1.3, ease: "easeOut", repeat: Infinity, delay: 0.65 }}
          />
        </>
      )}

      {/* Pulsierende innere Scheibe – Tempo & Amplitude je nach Zustand. */}
      <motion.div
        className="absolute h-56 w-56 rounded-full"
        style={{
          background:
            "radial-gradient(circle, rgba(0,255,136,0.16) 0%, rgba(0,61,43,0.10) 55%, transparent 72%)",
          boxShadow: "0 0 60px rgba(0,255,136,0.25) inset",
        }}
        animate={
          reduce
            ? undefined
            : {
                scale:
                  speaking || answering
                    ? [1, 1.1, 1]
                    : listening
                      ? [1, 1.06, 1]
                      : [1, 1.02, 1],
                opacity: active ? [0.85, 1, 0.85] : [0.8, 1, 0.8],
              }
        }
        transition={{
          duration: speaking || answering ? 0.7 : listening ? 1.1 : 2.6,
          ease: "easeInOut",
          repeat: Infinity,
        }}
      />

      {/* Zentraler Text. */}
      <div className="relative z-10 flex flex-col items-center">
        <h1 className="font-display text-4xl font-black tracking-[0.35em] text-hud-neon text-glow sm:text-5xl">
          APHELIOS
        </h1>
        <div className="mt-3 flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${
              link === "offline" ? "bg-hud-danger" : "bg-hud-neon animate-pulse-soft"
            }`}
          />
          <span
            className={`font-hud text-sm tracking-[0.5em] ${
              active ? "text-hud-neon text-glow" : "text-hud-neon-dim"
            }`}
          >
            {statusLabel}
          </span>
        </div>
      </div>
    </div>
  );
}
