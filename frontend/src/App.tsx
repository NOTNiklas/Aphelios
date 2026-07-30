/** APHELIOS – HUD-Startscreen. Komponiert Hintergrund, Panels, Core und Konsole. */
import { useEffect } from "react";
import { Grid } from "./hud/Grid";
import { Particles } from "./hud/Particles";
import { ScanLines } from "./hud/ScanLines";
import { Core } from "./hud/Core";
import { SystemStats } from "./panels/SystemStats";
import { InfoPanels } from "./panels/InfoPanels";
import { Tasks } from "./panels/Tasks";
import { Console } from "./panels/Console";
import { ConfirmDialog } from "./panels/ConfirmDialog";
import { TradingDashboard } from "./panels/TradingDashboard";
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

          {/* Linke Spalte: System + Aufgaben (von APHELIOS selbst erzeugt,
              deshalb getrennt von den externen Datenquellen rechts).
              inset-y statt top-1/2/-translate-y-1/2, damit die Spalte auf die
              zwischen TopBar und Konsole verfügbare Höhe begrenzt bleibt: bei
              wenig Platz (kleine Fenster/Laptop-Displays) scrollt sie intern,
              statt TopBar/Konsole zu überlappen. Zentrierung über m-auto statt
              justify-center: justify-center würde bei zu großem Inhalt "unsafe"
              zentrieren und den oberen Teil über den Rand hinaus unerreichbar
              verschieben – m-auto zentriert nur, wenn Platz ist, und rutscht
              sonst sauber scrollbar nach oben. */}
          <div className="absolute inset-y-4 left-6 hidden overflow-y-auto lg:flex lg:flex-col">
            <div className="m-auto flex flex-col gap-3">
              <SystemStats />
              <Tasks />
            </div>
          </div>

          {/* Rechte Spalte: externe Datenquellen (gleiche Höhenbegrenzung wie links). */}
          <div className="absolute inset-y-4 right-6 hidden overflow-y-auto lg:flex lg:flex-col">
            <div className="m-auto">
              <InfoPanels />
            </div>
          </div>
        </main>

        {/* Untere Konsole */}
        <div className="px-4 pb-4">
          <Console />
        </div>
      </div>

      {/* Sicherheits-Bestätigungen */}
      <ConfirmDialog />

      {/* Trading-Dashboard-Popup */}
      <TradingDashboard />
    </div>
  );
}
