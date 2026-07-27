/** Rechte Spalte: Wetter, Kalender, Mails – externe Datenquellen.
 *
 * Zeigen **echte Daten** (Google/Open-Meteo), sobald das Backend über
 * ``docs/integrations.md`` verbunden ist – ohne Verbindung erscheint eine
 * Vorschau mit Mock-Daten inkl. Hinweis, damit klar bleibt, was real ist und
 * was noch Beispieldaten sind. Das Aufgaben-Panel (von APHELIOS selbst
 * erzeugte Plan-Schritte, keine externe Quelle) sitzt bewusst getrennt in
 * der linken Spalte, siehe ``panels/Tasks.tsx`` und ``App.tsx``.
 */
import { Panel } from "../hud/Panel";
import { MOCK_INFO } from "../lib/mock";
import { useHud } from "../store/hud";
import { PreviewHint } from "./PreviewHint";
import { Weather } from "./Weather";

function Item({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-center gap-2 py-0.5 font-hud text-[13px] text-hud-neon/85">
      <span className="h-1 w-1 shrink-0 rounded-full bg-hud-neon/60" />
      <span className="truncate">{children}</span>
    </li>
  );
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
    </div>
  );
}
