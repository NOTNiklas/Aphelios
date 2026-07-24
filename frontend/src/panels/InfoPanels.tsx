/** Rechte Spalte: Kalender, Mails, Aufgaben, Benachrichtigungen, Prozesse, Fenster.
 *
 * In Alpha 1.0 aus Mock-Daten gespeist. Die Struktur ist so angelegt, dass die
 * Werte später über den Bus (Calendar-/Mail-/System-Engine) einfließen.
 */
import { Panel } from "../hud/Panel";
import { MOCK_INFO } from "../lib/mock";

function Item({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-center gap-2 py-0.5 font-hud text-[13px] text-hud-neon/85">
      <span className="h-1 w-1 shrink-0 rounded-full bg-hud-neon/60" />
      <span className="truncate">{children}</span>
    </li>
  );
}

export function InfoPanels() {
  return (
    <div className="flex w-64 flex-col gap-3">
      <Panel title="Kalender" delay={0.05}>
        <ul>
          {MOCK_INFO.kalender.map((e) => (
            <Item key={e.title}>
              <span className="mr-2 font-display text-xs text-hud-neon-dim">{e.time}</span>
              {e.title}
            </Item>
          ))}
        </ul>
      </Panel>

      <Panel title="Mails" delay={0.1}>
        <ul>
          {MOCK_INFO.mails.map((m) => (
            <Item key={m.subject}>
              <span className="mr-1 text-hud-neon-dim">{m.from}:</span>
              {m.subject}
            </Item>
          ))}
        </ul>
      </Panel>

      <Panel title="Aufgaben" delay={0.15}>
        <ul>
          {MOCK_INFO.aufgaben.map((t) => (
            <li
              key={t.title}
              className="flex items-center gap-2 py-0.5 font-hud text-[13px] text-hud-neon/85"
            >
              <span
                className={`grid h-3 w-3 shrink-0 place-items-center rounded-[3px] border ${
                  t.done ? "border-hud-neon bg-hud-neon/30" : "border-hud-neon/50"
                }`}
              >
                {t.done && <span className="text-[8px] leading-none text-hud-neon">✓</span>}
              </span>
              <span className={t.done ? "line-through opacity-60" : ""}>{t.title}</span>
            </li>
          ))}
        </ul>
      </Panel>

      <div className="flex gap-3">
        <Panel title="Prozesse" delay={0.2} className="flex-1">
          <ul>
            {MOCK_INFO.prozesse.map((p) => (
              <li
                key={p.name}
                className="flex items-center justify-between py-0.5 font-hud text-[13px] text-hud-neon/85"
              >
                <span className="truncate">{p.name}</span>
                <span className="font-display tabular-nums text-hud-neon-dim">{p.cpu}%</span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <Panel title="Offene Fenster" delay={0.25}>
        <ul>
          {MOCK_INFO.fenster.map((w) => (
            <Item key={w}>{w}</Item>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
