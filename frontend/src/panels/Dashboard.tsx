/** Web-Dashboard – eigene Seite (``/dashboard``) zur Überwachung des
 * Agenten: Engine-Status, System-Werte, zuletzt erzeugte Vault-Notizen.
 * Kein neuer Router – ``main.tsx`` prüft nur den Pfad und rendert diese
 * Seite statt der normalen HUD-``App`` (kein zusätzliches npm-Paket nötig
 * für eine einzelne zusätzliche Route).
 */
import { useEffect, useState } from "react";
import { Panel } from "../hud/Panel";
import { useBackend } from "../lib/ws";
import type { RecentNote } from "../lib/types";
import { useHud } from "../store/hud";
import { SystemStats } from "./SystemStats";

function timeAgo(unixSeconds: number): string {
  const diffMin = Math.round((Date.now() / 1000 - unixSeconds) / 60);
  if (diffMin < 1) return "gerade eben";
  if (diffMin < 60) return `vor ${diffMin} Min.`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `vor ${diffH} Std.`;
  return `vor ${Math.round(diffH / 24)} Tag(en)`;
}

function EngineGrid() {
  const overview = useHud((s) => s.dashboardOverview);
  const engines = overview?.engines ?? {};
  const names = Object.keys(engines).sort();

  return (
    <Panel title="Engines" delay={0}>
      {names.length === 0 ? (
        <p className="font-hud text-[13px] text-hud-neon/50">Warte auf Backend-Verbindung …</p>
      ) : (
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-3">
          {names.map((name) => {
            const online = engines[name] === "online";
            return (
              <div key={name} className="flex items-center gap-2">
                <span
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                    online ? "bg-hud-neon animate-pulse-soft" : "bg-hud-danger"
                  }`}
                />
                <span className="truncate font-hud text-[12px] text-hud-neon/85">{name}</span>
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

function ConnectionInfo() {
  const overview = useHud((s) => s.dashboardOverview);
  const link = useHud((s) => s.link);

  return (
    <Panel title="Verbindung" delay={0.05}>
      <div className="space-y-1.5 font-hud text-[13px] text-hud-neon/85">
        <div className="flex justify-between">
          <span className="text-hud-neon-dim">Status</span>
          <span>{link === "online" ? "ONLINE" : link.toUpperCase()}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-hud-neon-dim">KI-Modus</span>
          <span>{overview?.ai === "claude" ? "CLAUDE" : "FALLBACK"}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-hud-neon-dim">Verbundene Clients</span>
          <span>{overview?.clients ?? "–"}</span>
        </div>
      </div>
    </Panel>
  );
}

function ActivityFeed() {
  const { requestRecentNotes } = useBackend();
  const [notes, setNotes] = useState<RecentNote[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      requestRecentNotes(15).then((result) => {
        if (!cancelled) setNotes(result);
      });
    };
    load();
    const id = setInterval(load, 30000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [requestRecentNotes]);

  return (
    <Panel title="Aktivität (Vault)" delay={0.1} className="w-full">
      {notes == null ? (
        <p className="font-hud text-[13px] text-hud-neon/50">Lädt …</p>
      ) : notes.length === 0 ? (
        <p className="font-hud text-[13px] text-hud-neon/50">Noch keine Notizen im Vault.</p>
      ) : (
        <ul className="space-y-1.5">
          {notes.map((n, i) => (
            <li key={i} className="flex items-center justify-between gap-3 font-hud text-[13px]">
              <span className="truncate text-hud-neon/85">
                <span className="mr-2 rounded border border-hud-neon/25 px-1.5 py-0.5 font-hud text-[10px] tracking-widest text-hud-neon-dim">
                  {n.category}
                </span>
                {n.title}
              </span>
              <span className="shrink-0 font-mono text-[11px] text-hud-neon/50">{timeAgo(n.created_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export function Dashboard() {
  useBackend(); // startet die Backend-Verbindung (kein App.tsx auf dieser Route)

  return (
    <div className="min-h-dvh bg-black p-6 text-hud-neon">
      <header className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-display text-lg tracking-[0.4em] text-hud-neon text-glow">⬡</span>
          <span className="font-display text-xs tracking-[0.5em] text-hud-neon-dim">
            APHELIOS — DASHBOARD
          </span>
        </div>
        <a
          href="/"
          className="rounded border border-hud-neon/30 px-3 py-1 font-hud text-xs tracking-widest text-hud-neon/70 hover:border-hud-neon/60 hover:text-hud-neon"
        >
          ← ZUM HUD
        </a>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <EngineGrid />
        <SystemStats />
        <ConnectionInfo />
        <div className="lg:col-span-3">
          <ActivityFeed />
        </div>
      </div>
    </div>
  );
}
