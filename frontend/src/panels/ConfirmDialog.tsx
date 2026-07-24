/** Bestätigungsdialog für gefährliche Aktionen (SecurityGate). */
import { AnimatePresence, motion } from "framer-motion";
import { useHud } from "../store/hud";
import { useBackend } from "../lib/ws";

export function ConfirmDialog() {
  const confirmations = useHud((s) => s.confirmations);
  const { respondConfirmation } = useBackend();
  const current = confirmations[0];

  return (
    <AnimatePresence>
      {current && (
        <motion.div
          className="absolute inset-0 z-50 grid place-items-center"
          style={{ background: "rgba(0,0,0,0.55)", backdropFilter: "blur(2px)" }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.div
            initial={{ scale: 0.94, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.94, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="glass w-[min(90vw,440px)] rounded-lg border-hud-danger/50 p-5 shadow-glow"
          >
            <div className="mb-2 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-hud-danger animate-pulse-soft" />
              <h2 className="font-display text-sm tracking-[0.25em] text-hud-danger">
                BESTÄTIGUNG ERFORDERLICH
              </h2>
            </div>
            <p className="mb-1 font-hud text-base text-hud-neon">
              {current.action}
              {current.target && (
                <span className="ml-1 font-mono text-sm text-hud-neon/70">→ {current.target}</span>
              )}
            </p>
            {current.reason && (
              <p className="mb-4 font-hud text-sm text-hud-neon/70">{current.reason}</p>
            )}
            <div className="flex justify-end gap-3">
              <button
                onClick={() => respondConfirmation(current.id, false)}
                className="rounded border border-hud-neon/40 px-4 py-1.5 font-hud text-xs tracking-widest text-hud-neon/80 hover:bg-hud-neon/10"
              >
                ABLEHNEN
              </button>
              <button
                onClick={() => respondConfirmation(current.id, true)}
                className="rounded border border-hud-danger/60 bg-hud-danger/15 px-4 py-1.5 font-hud text-xs tracking-widest text-hud-danger hover:bg-hud-danger/25"
              >
                FREIGEBEN
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
