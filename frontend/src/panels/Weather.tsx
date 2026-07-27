/** Wetter-Panel – erste echte externe App-Integration (Open-Meteo, kein Key).
 *
 * Zeigt reale Daten der Backend-``WeatherEngine``. Anders als die übrigen
 * Info-Panels (noch Mock-Daten) ist dies eine tatsächlich funktionierende
 * Integration – deshalb bewusst ohne Fallback-Fantasiewerte: ohne Verbindung
 * oder bei einem Fehler wird das ehrlich angezeigt statt erfundener Zahlen.
 */
import { Panel } from "../hud/Panel";
import { useHud } from "../store/hud";

export function Weather() {
  const weather = useHud((s) => s.weather);
  const link = useHud((s) => s.link);

  return (
    <Panel title="Wetter" delay={0}>
      {!weather ? (
        <p className="font-hud text-[13px] text-hud-neon/50">
          {link === "online" ? "Lädt …" : "Keine Verbindung zum Backend."}
        </p>
      ) : weather.error ? (
        <p className="font-hud text-[13px] text-hud-danger">{weather.error}</p>
      ) : (
        <div className="flex items-center justify-between">
          <div>
            <div className="font-display text-2xl tabular-nums text-hud-neon text-glow">
              {weather.temperature != null ? `${Math.round(weather.temperature)}°C` : "n/a"}
            </div>
            <div className="font-hud text-[13px] text-hud-neon/80">{weather.condition}</div>
          </div>
          <div className="text-right">
            <div className="font-hud text-xs tracking-[0.2em] text-hud-neon-dim">
              {weather.city ?? "—"}
            </div>
            <div className="font-mono text-[11px] text-hud-neon/60">
              {weather.humidity != null && `${weather.humidity}% Luftf.`}
              {weather.wind_kmh != null && ` · ${Math.round(weather.wind_kmh)} km/h`}
            </div>
          </div>
        </div>
      )}
    </Panel>
  );
}
