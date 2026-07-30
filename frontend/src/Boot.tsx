/** Boot-Ablauf beim ersten Laden des HUD: Skeleton-Ladezustand bis zu 30s,
 * dann entweder das echte App (sobald verbunden) oder eine 404-artige
 * Fehlerseite, falls das Backend gar nicht erreichbar ist.
 *
 * Bewusst ein EIGENER, fester 30s-Timer statt einfach auf `link` zu
 * schauen: `link` kippt schon nach dem ERSTEN gescheiterten
 * Verbindungsversuch (Millisekunden) auf "offline" und der WS-Client
 * versucht danach alle 4s automatisch erneut (siehe lib/ws.ts) – ohne
 * eigenen Timer würde die Fehlerseite viel zu früh erscheinen.
 */
import { useEffect, useState } from "react";
import App from "./App";
import { BackendUnreachable } from "./panels/BackendUnreachable";
import { SkeletonHud } from "./panels/SkeletonHud";
import { useBackend } from "./lib/ws";
import { useHud } from "./store/hud";

const BOOT_TIMEOUT_MS = 30000;

export function Boot() {
  useBackend(); // startet die WS-Verbindung
  const link = useHud((s) => s.link);
  const ready = link === "online";
  const [timedOut, setTimedOut] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (ready) return;
    setTimedOut(false);
    const timer = setTimeout(() => setTimedOut(true), BOOT_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [attempt, ready]);

  if (ready) return <App />;
  if (timedOut) return <BackendUnreachable onRetry={() => setAttempt((a) => a + 1)} />;
  return <SkeletonHud />;
}
