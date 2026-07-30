/** Skeleton-Ladezustand – gezeigt, solange das Frontend auf die erste
 * Backend-Verbindung wartet (siehe Boot.tsx). Grobe Platzhalter in
 * derselben Anordnung wie App.tsx, damit der Übergang zum echten HUD
 * nicht ruckt, sobald die Verbindung steht.
 */
import { Grid } from "../hud/Grid";
import { Particles } from "../hud/Particles";
import { ScanLines } from "../hud/ScanLines";

function SkeletonBlock({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse-soft rounded-lg border border-hud-neon/15 bg-hud-neon/5 ${className}`}
    />
  );
}

export function SkeletonHud() {
  return (
    <div className="relative flex h-dvh flex-col overflow-hidden bg-black text-hud-neon">
      <Grid />
      <Particles />
      <ScanLines />

      <div className="relative z-10 flex h-full flex-col">
        <header className="flex items-center justify-between px-4 py-3 sm:px-6">
          <SkeletonBlock className="h-6 w-40" />
          <SkeletonBlock className="h-6 w-56" />
        </header>

        <main className="relative flex-1">
          <div className="absolute inset-0 flex items-center justify-center">
            <SkeletonBlock className="h-48 w-48 rounded-full" />
          </div>

          <div className="absolute inset-y-4 left-6 hidden w-64 flex-col gap-3 lg:flex">
            <SkeletonBlock className="h-40" />
            <SkeletonBlock className="h-32" />
          </div>

          <div className="absolute inset-y-4 right-6 hidden w-64 flex-col gap-3 lg:flex">
            <SkeletonBlock className="h-24" />
            <SkeletonBlock className="h-56" />
            <SkeletonBlock className="h-32" />
          </div>

          <div className="absolute inset-x-0 bottom-4 px-4">
            <div className="mx-auto w-full max-w-4xl">
              <SkeletonBlock className="h-32" />
            </div>
          </div>
        </main>
      </div>

      <div className="absolute inset-x-0 bottom-10 z-20 flex justify-center">
        <span className="animate-pulse-soft font-hud text-xs tracking-[0.35em] text-hud-neon-dim">
          VERBINDE MIT APHELIOS-BACKEND …
        </span>
      </div>
    </div>
  );
}
