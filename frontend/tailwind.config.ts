import type { Config } from "tailwindcss";

/**
 * APHELIOS Design-Tokens (siehe docs/design-system.md).
 * Schwarz + Neon-Grün, Glassmorphism, Glow.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        hud: {
          bg: "#000000",
          neon: "#00ff88",
          "neon-dim": "rgba(0,255,136,0.45)",
          "dark-green": "#003d2b",
          glass: "rgba(0,40,28,0.25)",
          danger: "#ff3b5c",
        },
      },
      fontFamily: {
        display: ['"Orbitron"', '"Rajdhani"', "ui-monospace", "monospace"],
        hud: ['"Rajdhani"', '"Segoe UI"', "system-ui", "sans-serif"],
        mono: ['"Rajdhani"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        glow: "0 0 20px rgba(0,255,136,0.35), 0 0 40px rgba(0,255,136,0.15)",
        "glow-sm": "0 0 10px rgba(0,255,136,0.4)",
        "glow-strong":
          "0 0 30px rgba(0,255,136,0.6), 0 0 60px rgba(0,255,136,0.25)",
      },
      dropShadow: {
        neon: "0 0 6px rgba(0,255,136,0.7)",
      },
      keyframes: {
        scan: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100vh)" },
        },
        "pulse-soft": {
          "0%,100%": { opacity: "0.4" },
          "50%": { opacity: "1" },
        },
        flicker: {
          "0%,100%": { opacity: "1" },
          "48%": { opacity: "1" },
          "50%": { opacity: "0.7" },
          "52%": { opacity: "1" },
        },
      },
      animation: {
        scan: "scan 6s linear infinite",
        "pulse-soft": "pulse-soft 2.4s ease-in-out infinite",
        flicker: "flicker 4s steps(1) infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
