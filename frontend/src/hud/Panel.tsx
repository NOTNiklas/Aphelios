/** Glassmorphism-Panel mit Titelzeile und Eck-Markierungen. */
import { motion } from "framer-motion";
import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  children: ReactNode;
  className?: string;
  delay?: number;
}

export function Panel({ title, children, className = "", delay = 0 }: PanelProps) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay, ease: "easeOut" }}
      className={`glass relative rounded-lg p-3 shadow-glow-sm ${className}`}
    >
      {/* Eck-Winkel */}
      <span className="absolute left-0 top-0 h-3 w-3 border-l-2 border-t-2 border-hud-neon/60" />
      <span className="absolute right-0 top-0 h-3 w-3 border-r-2 border-t-2 border-hud-neon/60" />
      <span className="absolute bottom-0 left-0 h-3 w-3 border-b-2 border-l-2 border-hud-neon/60" />
      <span className="absolute bottom-0 right-0 h-3 w-3 border-b-2 border-r-2 border-hud-neon/60" />

      <header className="mb-2 flex items-center gap-2">
        <span className="h-1 w-1 rounded-full bg-hud-neon" />
        <h2 className="font-hud text-xs font-semibold tracking-[0.3em] text-hud-neon-dim">
          {title.toUpperCase()}
        </h2>
      </header>
      {children}
    </motion.section>
  );
}
