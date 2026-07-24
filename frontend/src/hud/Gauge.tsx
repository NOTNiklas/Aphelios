/** Radiale Stat-Anzeige (270°-Bogen) mit Wert und Label. */
import { motion, useReducedMotion } from "framer-motion";

interface GaugeProps {
  label: string;
  value: number | null; // 0..100, oder null = n/a
  detail?: string;
  size?: number;
}

const START = 135; // Grad – offen nach unten
const SWEEP = 270;

function polar(cx: number, cy: number, r: number, deg: number) {
  const rad = ((deg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
  const s = polar(cx, cy, r, startDeg);
  const e = polar(cx, cy, r, endDeg);
  const large = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y}`;
}

export function Gauge({ label, value, detail, size = 72 }: GaugeProps) {
  const reduce = useReducedMotion();
  const r = size / 2 - 6;
  const cx = size / 2;
  const pct = value == null ? 0 : Math.max(0, Math.min(100, value));
  const endDeg = START + (SWEEP * pct) / 100;
  const danger = value != null && value >= 85;
  const color = danger ? "#ff3b5c" : "#00ff88";

  return (
    <div className="flex items-center gap-3">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          {/* Hintergrundbogen */}
          <path
            d={arcPath(cx, cx, r, START, START + SWEEP)}
            fill="none"
            stroke="rgba(0,255,136,0.15)"
            strokeWidth={4}
            strokeLinecap="round"
          />
          {/* Wertbogen */}
          {value != null && (
            <motion.path
              d={arcPath(cx, cx, r, START, endDeg)}
              fill="none"
              stroke={color}
              strokeWidth={4}
              strokeLinecap="round"
              style={{ filter: `drop-shadow(0 0 4px ${color})` }}
              initial={false}
              animate={{ d: arcPath(cx, cx, r, START, endDeg) }}
              transition={reduce ? { duration: 0 } : { duration: 0.5, ease: "easeOut" }}
            />
          )}
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="font-display text-sm tabular-nums text-hud-neon">
            {value == null ? "n/a" : `${Math.round(pct)}`}
          </span>
        </div>
      </div>
      <div className="min-w-0">
        <div className="font-hud text-xs tracking-[0.25em] text-hud-neon-dim">{label}</div>
        {detail && <div className="truncate font-mono text-[11px] text-hud-neon/70">{detail}</div>}
      </div>
    </div>
  );
}
