/** Schalter für Web-Push-Benachrichtigungen (VAPID) – z. B. fürs
 * Morgen-Briefing. Zeigt den bestehenden Abo-Status beim Laden (kein
 * erneuter Berechtigungsdialog nötig, wenn schon abonniert) und meldet
 * sich bei fehlender Browser-Unterstützung/unsicherem Kontext klar ab statt
 * einfach nichts zu tun (siehe lib/push.ts).
 */
import { useEffect, useState } from "react";
import { currentPushSubscription, disablePush, enablePush, pushSupported } from "../lib/push";

export function PushControl() {
  const [enabled, setEnabled] = useState(false);
  const [supported, setSupported] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSupported(pushSupported());
    currentPushSubscription().then((sub) => setEnabled(sub !== null));
  }, []);

  async function toggle() {
    if (busy) return;
    setBusy(true);
    try {
      if (enabled) {
        await disablePush();
        setEnabled(false);
      } else {
        const status = await enablePush();
        setEnabled(status === "enabled");
      }
    } finally {
      setBusy(false);
    }
  }

  if (!supported) return null;

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      className={`rounded border px-2.5 py-1 font-hud text-[11px] tracking-[0.25em] disabled:opacity-50 ${
        enabled
          ? "border-hud-neon/60 bg-hud-neon/15 text-hud-neon"
          : "border-hud-neon/30 text-hud-neon/70 hover:border-hud-neon/60 hover:text-hud-neon"
      }`}
      title="Push-Benachrichtigungen (z. B. Morgen-Briefing) auf diesem Gerät"
    >
      {enabled ? "🔔 PUSH AN" : "🔕 PUSH AUS"}
    </button>
  );
}
