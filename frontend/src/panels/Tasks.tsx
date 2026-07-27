/** Eigenständiges Aufgaben-Panel – bewusst getrennt von den externen
 * Daten-Panels (Wetter/Kalender/Mails): zeigt den aktuellen Plan der
 * PlanningEngine (Alpha 1.1, ausgelöst über "/plan <Aufgabe>" im Chat),
 * nicht externe Dienste, sondern von APHELIOS selbst erzeugte Schritte.
 */
import { Panel } from "../hud/Panel";
import { MOCK_INFO } from "../lib/mock";
import { useBackend } from "../lib/ws";
import { useHud } from "../store/hud";
import { PreviewHint } from "./PreviewHint";

export function Tasks() {
  const plan = useHud((s) => s.plan);
  const { completeStep } = useBackend();

  return (
    <Panel title="Aufgaben" className="w-64" delay={0.15}>
      {plan ? (
        <>
          <p className="mb-1 truncate font-hud text-[11px] text-hud-neon/50">{plan.task}</p>
          <ul>
            {plan.steps.map((step) => (
              <li
                key={step.index}
                onClick={() => completeStep(step.index)}
                className="flex cursor-pointer items-center gap-2 py-0.5 font-hud text-[13px] text-hud-neon/85"
              >
                <span
                  className={`grid h-3 w-3 shrink-0 place-items-center rounded-[3px] border ${
                    step.done ? "border-hud-neon bg-hud-neon/30" : "border-hud-neon/50"
                  }`}
                >
                  {step.done && <span className="text-[8px] leading-none text-hud-neon">✓</span>}
                </span>
                <span className={step.done ? "line-through opacity-60" : ""}>{step.text}</span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <>
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
          <PreviewHint>Vorschau — "/plan Aufgabe" im Chat erstellt einen echten Plan</PreviewHint>
        </>
      )}
    </Panel>
  );
}
