/** Rechte Spalte: Kalender, Mails, Aufgaben, Benachrichtigungen, Prozesse, Fenster.
 *
 * Kalender & Mails zeigen **echte Daten** (Google), sobald das Backend über
 * ``docs/integrations.md`` verbunden ist – ohne Verbindung erscheint eine
 * Vorschau mit Mock-Daten inkl. Hinweis, damit klar bleibt, was real ist und
 * was noch Beispieldaten sind. Die restlichen Panels sind für Alpha 1.0
 * bewusst noch Mock-Vorschauen (Roadmap: eigene Engines je Bereich).
 */
import { Panel } from "../hud/Panel";
import { MOCK_INFO } from "../lib/mock";
import { useHud } from "../store/hud";
import { Weather } from "./Weather";

function Item({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-center gap-2 py-0.5 font-hud text-[13px] text-hud-neon/85">
      <span className="h-1 w-1 shrink-0 rounded-full bg-hud-neon/60" />
      <span className="truncate">{children}</span>
    </li>
  );
}

/** Kleiner Hinweis unter Vorschau-Daten, die noch keine echte Verbindung haben. */
function PreviewHint({ children }: { children: React.ReactNode }) {
  return <p className="mt-1 font-hud text-[10px] text-hud-neon/35">{children}</p>;
}

/** Formatiert ISO-Zeiten der Google-Kalender-API fürs HUD (de-DE, kurz). */
function formatEventTime(iso: string): string {
  if (!iso) return "";
  if (!iso.includes("T")) return "Ganztägig"; // Ganztägige Termine: nur "YYYY-MM-DD"
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
}

export function InfoPanels() {
  const calendar = useHud((s) => s.calendar);
  const mail = useHud((s) => s.mail);

  return (
    <div className="flex w-64 flex-col gap-3">
      <Weather />

      <Panel title="Kalender" delay={0.05}>
        {calendar?.error ? (
          <p className="font-hud text-[12px] text-hud-danger">{calendar.error}</p>
        ) : calendar?.events ? (
          <ul>
            {calendar.events.length === 0 && (
              <p className="font-hud text-[12px] text-hud-neon/40">Keine kommenden Termine.</p>
            )}
            {calendar.events.map((e) => (
              <Item key={e.title + e.start}>
                <span className="mr-2 font-display text-xs text-hud-neon-dim">
                  {formatEventTime(e.start)}
                </span>
                {e.title}
              </Item>
            ))}
          </ul>
        ) : (
          <>
            <ul>
              {MOCK_INFO.kalender.map((e) => (
                <Item key={e.title}>
                  <span className="mr-2 font-display text-xs text-hud-neon-dim">{e.time}</span>
                  {e.title}
                </Item>
              ))}
            </ul>
            <PreviewHint>Vorschau — Google Kalender via docs/integrations.md verbinden</PreviewHint>
          </>
        )}
      </Panel>

      <Panel title="Mails" delay={0.1}>
        {mail?.error ? (
          <p className="font-hud text-[12px] text-hud-danger">{mail.error}</p>
        ) : mail?.emails ? (
          <ul>
            {mail.emails.length === 0 && (
              <p className="font-hud text-[12px] text-hud-neon/40">Keine ungelesenen Mails.</p>
            )}
            {mail.emails.map((m, i) => (
              <Item key={i}>
                <span className="mr-1 text-hud-neon-dim">{m.from}:</span>
                {m.subject}
              </Item>
            ))}
          </ul>
        ) : (
          <>
            <ul>
              {MOCK_INFO.mails.map((m) => (
                <Item key={m.subject}>
                  <span className="mr-1 text-hud-neon-dim">{m.from}:</span>
                  {m.subject}
                </Item>
              ))}
            </ul>
            <PreviewHint>Vorschau — Gmail via docs/integrations.md verbinden</PreviewHint>
          </>
        )}
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
