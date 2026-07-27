/** Untere AI-Konsole: animierte Antworten, Texteingabe, Sprach-Button & -Status. */
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useHud } from "../store/hud";
import { useBackend } from "../lib/ws";
import { useWakeWord } from "../voice/useWakeWord";

export function Console() {
  const messages = useHud((s) => s.messages);
  const listening = useHud((s) => s.listening);
  const speaking = useHud((s) => s.speaking);
  const { sendChat } = useBackend();
  const { supported, enabled, error, toggle } = useWakeWord((text) => sendChat(text));
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    sendChat(text);
    setInput("");
  };

  return (
    <div className="glass mx-auto w-full max-w-4xl rounded-lg p-3 shadow-glow-sm">
      <header className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="h-1 w-1 rounded-full bg-hud-neon animate-pulse-soft" />
          <span className="font-hud text-xs tracking-[0.3em] text-hud-neon-dim">AI-KONSOLE</span>
        </div>
        {error ? (
          <span className="font-hud text-[11px] tracking-[0.15em] text-hud-danger">{error}</span>
        ) : speaking ? (
          <span className="font-hud text-[11px] tracking-[0.3em] text-hud-neon animate-pulse-soft">
            ◉ SPRICHT
          </span>
        ) : listening ? (
          <span className="font-hud text-[11px] tracking-[0.3em] text-hud-neon animate-pulse-soft">
            ● HÖRT ZU
          </span>
        ) : enabled ? (
          <span className="font-hud text-[11px] tracking-[0.25em] text-hud-neon-dim">
            ◉ SPRACHE AKTIV — sag „Aphelios"
          </span>
        ) : null}
      </header>

      {/* Verlauf */}
      <div ref={scrollRef} className="mb-2 max-h-40 overflow-y-auto pr-1">
        <AnimatePresence initial={false}>
          {messages.map((m) => (
            <motion.div
              key={m.id + m.role}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25 }}
              className="mb-1.5 flex gap-2 font-hud text-sm"
            >
              <span
                className={`shrink-0 font-display text-xs tracking-widest ${
                  m.role === "user" ? "text-hud-neon-dim" : "text-hud-neon text-glow"
                }`}
              >
                {m.role === "user" ? "DU ›" : "APHELIOS ›"}
              </span>
              <span className="text-hud-neon/90">
                {m.text}
                {m.streaming && (
                  <span className="ml-0.5 inline-block h-3 w-1.5 translate-y-0.5 bg-hud-neon animate-pulse-soft" />
                )}
              </span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Eingabe */}
      <form onSubmit={submit} className="flex items-center gap-2">
        <span className="font-display text-hud-neon text-glow">›</span>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Frage eingeben … (oder /plan Aufgabe, /denke Frage)"
          className="flex-1 bg-transparent font-hud text-sm text-hud-neon placeholder:text-hud-neon/30 focus:outline-none"
          autoFocus
        />
        {supported ? (
          <button
            type="button"
            onClick={toggle}
            aria-label={enabled ? "Sprachaktivierung deaktivieren" : "Sprachaktivierung aktivieren"}
            title='Wake-Word: "Aphelios" — nur über localhost, Chrome/Edge, mit Mikrofon-Freigabe'
            className={`grid h-8 w-8 place-items-center rounded-full border transition-colors ${
              enabled
                ? "border-hud-neon bg-hud-neon/20 shadow-glow-sm"
                : "border-hud-neon/40 hover:border-hud-neon"
            }`}
          >
            <MicIcon active={enabled} />
          </button>
        ) : (
          <span
            className="font-hud text-[10px] tracking-widest text-hud-neon/40"
            title="Web Speech API benötigt Chrome oder Edge über http://localhost"
          >
            SPRACHE&nbsp;N/V
          </span>
        )}
        <button
          type="submit"
          className="rounded border border-hud-neon/50 px-3 py-1 font-hud text-xs tracking-widest text-hud-neon transition-colors hover:bg-hud-neon/15"
        >
          SENDEN
        </button>
      </form>
    </div>
  );
}

function MicIcon({ active }: { active: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke={active ? "#00ff88" : "rgba(0,255,136,0.7)"}
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0" />
      <line x1="12" y1="17" x2="12" y2="22" />
    </svg>
  );
}
