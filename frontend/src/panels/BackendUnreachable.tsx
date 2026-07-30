/** "404"-Fehlerseite – gezeigt, wenn nach 30s Boot-Zeit (siehe Boot.tsx)
 * immer noch keine Backend-Verbindung steht. Kein klassisches "Seite
 * nicht gefunden", sondern bewusst als "Signal/Backend nicht gefunden"
 * im selben Iron-Man-HUD-Look interpretiert – derselbe Hintergrund wie
 * das echte HUD (Grid/Particles/ScanLines), nur mit Fehlerfarbe/-flackern.
 */
import { Grid } from "../hud/Grid";
import { Particles } from "../hud/Particles";
import { ScanLines } from "../hud/ScanLines";

const WS_URL = `ws://${location.hostname}:8787/ws`;

export function BackendUnreachable({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="relative flex h-dvh flex-col items-center justify-center overflow-hidden bg-black text-hud-neon">
      <Grid />
      <Particles />
      <ScanLines />

      <div className="relative z-10 flex max-w-lg flex-col items-center gap-4 px-6 text-center">
        <span
          className="animate-flicker font-display text-[7rem] font-black leading-none tracking-widest text-hud-danger sm:text-[9rem]"
          style={{ textShadow: "0 0 24px rgba(255,59,92,0.65), 0 0 60px rgba(255,59,92,0.25)" }}
        >
          404
        </span>
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-hud-danger animate-pulse-soft" />
          <h1 className="font-display text-base tracking-[0.35em] text-hud-neon">SIGNAL VERLOREN</h1>
          <span className="h-1.5 w-1.5 rounded-full bg-hud-danger animate-pulse-soft" />
        </div>
        <p className="font-hud text-sm text-hud-neon/70">
          Kein Kontakt zum APHELIOS-Backend nach 30 Sekunden.
          <br />
          <code className="text-hud-neon/50">{WS_URL}</code>
        </p>
        <p className="font-hud text-xs text-hud-neon/40">
          Läuft der Server? <code className="text-hud-neon/60">Start-APHELIOS.bat</code> bzw.{" "}
          <code className="text-hud-neon/60">python -m aphelios</code> im <code>backend</code>-Ordner
          ausführen.
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 rounded border border-hud-neon/40 px-6 py-2 font-hud text-xs tracking-[0.3em] text-hud-neon transition-colors hover:border-hud-neon hover:bg-hud-neon/10"
        >
          ERNEUT VERSUCHEN
        </button>
      </div>
    </div>
  );
}
