/** APHELIOS – HUD-Startscreen. Komponiert Hintergrund, Panels, Core und Konsole. */
import { useEffect } from "react";
import { Grid } from "./hud/Grid";
import { Particles } from "./hud/Particles";
import { ScanLines } from "./hud/ScanLines";
import { Core } from "./hud/Core";
import { SystemStats } from "./panels/SystemStats";
import { InfoPanels } from "./panels/InfoPanels";
import { Console } from "./panels/Console";
import { ConfirmDialog } from "./panels/ConfirmDialog";
import { TopBar } from "./panels/TopBar";
import { useHud } from "./store/hud";

export default function App() {
  // Einmaliger Health-Check: erkennt, ob das Backend mit Claude oder im
  // Fallback-Modus läuft (nur kosmetisch für die Kopfzeile).
  useEffect(() => {
    fetch(`http://${location.hostname}:8787/health`)
      .then((r) => r.json())
      .then((h) => useHud.setState({ ai: h.ai === "claude" ? "claude" : "fallback" }))
      .catch(() => {
        /* Backend offline – Standard bleibt "fallback" */
      });
  }, []);

  return (
    <div className="relative flex h-dvh flex-col overflow-hidden bg-black text-hud-neon">
      {/* Hintergrund-Ebenen */}
      <Grid />
      <Particles />
      <ScanLines />

      {/* Vordergrund */}
      <div className="relative z-10 flex h-full flex-col">
        <TopBar />

        <main className="relative flex-1">
          {/* Zentraler Core */}
          <div className="absolute inset-0 flex items-center justify-center">
            <Core />
          </div>

          {/* Linke Spalte: System */}
          <div className="absolute left-6 top-1/2 hidden -translate-y-1/2 lg:block">
            <SystemStats />
          </div>

          {/* Rechte Spalte: Info */}
          <div className="absolute right-6 top-1/2 hidden -translate-y-1/2 lg:block">
            <InfoPanels />
          </div>
        </main>

        {/* Untere Konsole */}
        <div className="px-4 pb-4">
          <Console />
        </div>
      </div>

      {/* Sicherheits-Bestätigungen */}
      <ConfirmDialog />
    </div>
  );
}
