/** Der animierte Kern-Kreis: „APHELIOS / ONLINE", langsam rotierend. */
import { motion, useReducedMotion } from "framer-motion";
import { Ring } from "./Ring";
import { useHud } from "../store/hud";

const TICKS = Array.from({ length: 60 });

export function Core() {
  const reduce = useReducedMotion();
  const listening = useHud((s) => s.listening);
  const link = useHud((s) => s.link);

  const statusLabel = link === "online" ? "ONLINE" : link === "connecting" ? "VERBINDE" : "OFFLINE";

  return (
    <div className="relative flex h-[min(60vh,540px)] w-[min(60vh,540px)] items-center justify-center">
      {/* Rotierende Ringe (verschiedene Geschwindigkeiten & Richtungen). */}
      <Ring size={520} duration={60} dash="2 14" width={1} opacity={0.35} />
      <Ring size={440} duration={40} reverse dash="60 24" width={2} opacity={0.55} />
      <Ring size={360} duration={28} dash="4 8" width={1.5} opacity={0.5} />
      <Ring size={300} duration={18} reverse dash="90 30" width={2.5} opacity={0.7} />

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

      {/* Pulsierende innere Scheibe. */}
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
            : { scale: listening ? [1, 1.06, 1] : [1, 1.02, 1], opacity: [0.8, 1, 0.8] }
        }
        transition={{ duration: listening ? 1.1 : 2.6, ease: "easeInOut", repeat: Infinity }}
      />

      {/* Zentraler Text. */}
      <div className="relative z-10 flex flex-col items-center">
        <h1 className="font-display text-4xl font-black tracking-[0.35em] text-hud-neon text-glow sm:text-5xl">
          APHELIOS
        </h1>
        <div className="mt-3 flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${
              link === "online" ? "bg-hud-neon animate-pulse-soft" : "bg-hud-danger"
            }`}
          />
          <span className="font-hud text-sm tracking-[0.5em] text-hud-neon-dim">
            {statusLabel}
          </span>
        </div>
      </div>
    </div>
  );
}
