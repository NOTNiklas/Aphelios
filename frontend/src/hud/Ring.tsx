/** Ein rotierender, gestrichelter HUD-Ring (SVG). Wiederverwendbar. */
import { motion, useReducedMotion } from "framer-motion";

interface RingProps {
  size: number;
  duration?: number;
  reverse?: boolean;
  dash?: string;
  width?: number;
  opacity?: number;
  color?: string;
}

export function Ring({
  size,
  duration = 24,
  reverse = false,
  dash = "6 10",
  width = 1.5,
  opacity = 0.6,
  color = "#00ff88",
}: RingProps) {
  const reduce = useReducedMotion();
  const r = size / 2 - width;
  return (
    <motion.svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="absolute"
      style={{ opacity }}
      animate={reduce ? undefined : { rotate: reverse ? -360 : 360 }}
      transition={{ duration, ease: "linear", repeat: Infinity }}
    >
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={width}
        strokeDasharray={dash}
        strokeLinecap="round"
      />
    </motion.svg>
  );
}
