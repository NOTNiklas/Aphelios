/** Linke Spalte: Live-System-Statistiken (CPU/RAM/GPU/VRAM/Netz/Internet/Temp/Akku). */
import { Panel } from "../hud/Panel";
import { Gauge } from "../hud/Gauge";
import { useHud } from "../store/hud";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="font-hud text-xs tracking-[0.25em] text-hud-neon-dim">{label}</span>
      <span className="font-display text-sm tabular-nums text-hud-neon text-glow">{children}</span>
    </div>
  );
}

export function SystemStats() {
  const stats = useHud((s) => s.stats);
  const link = useHud((s) => s.link);

  return (
    <Panel title="System" className="w-64" delay={0.05}>
      <div className="flex flex-col gap-2">
        <Gauge
          label="CPU"
          value={stats?.cpu.percent ?? null}
          detail={stats ? `${stats.cpu.cores} Kerne` : ""}
        />
        <Gauge
          label="RAM"
          value={stats?.ram.percent ?? null}
          detail={stats ? `${stats.ram.used_gb} / ${stats.ram.total_gb} GB` : ""}
        />
        <Gauge label="GPU" value={stats?.gpu?.percent ?? null} />
        <Gauge
          label="VRAM"
          value={stats?.vram?.percent ?? null}
          detail={stats?.vram ? `${stats.vram.used_gb} / ${stats.vram.total_gb} GB` : ""}
        />

        <div className="my-1 h-px bg-hud-neon/15" />

        <Row label="NETZWERK">
          {stats ? (
            <span className="text-xs">
              ↓ {stats.network.down_kbps} · ↑ {stats.network.up_kbps} kb/s
            </span>
          ) : (
            "n/a"
          )}
        </Row>
        <Row label="INTERNET">
          <span className={link === "offline" ? "text-hud-danger" : "text-hud-neon"}>
            {link === "online" ? "VERBUNDEN" : link === "connecting" ? "…" : "GETRENNT"}
          </span>
        </Row>
        <Row label="TEMPERATUR">
          {stats?.temperature != null ? `${stats.temperature} °C` : "n/a"}
        </Row>
        <Row label="AKKU">
          {stats?.battery
            ? `${stats.battery.percent}%${stats.battery.plugged ? " ⚡" : ""}`
            : "n/a"}
        </Row>
      </div>
    </Panel>
  );
}
