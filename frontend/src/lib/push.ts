/** Web-Push-Anmeldung: fragt Berechtigung, abonniert über den Service Worker
 * (sw.js) und meldet die Subscription der Backend-PushEngine. Braucht einen
 * sicheren Kontext (HTTPS oder http://localhost) – über eine LAN-IP
 * (http://<IP>:5173, z. B. vom Handy) bietet der Browser `pushManager` gar
 * nicht erst an (siehe `pushSupported`).
 */
import { backend } from "./ws";

function urlBase64ToUint8Array(base64Url: string): Uint8Array {
  const padding = "=".repeat((4 - (base64Url.length % 4)) % 4);
  const base64 = (base64Url + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

export type PushStatus = "unsupported" | "denied" | "enabled" | "no-vapid-key";

export function pushSupported(): boolean {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

/** Liest ein bereits bestehendes Abo (z. B. um den Schalter-Zustand nach
 * einem Reload korrekt anzuzeigen), ohne erneut um Berechtigung zu fragen. */
export async function currentPushSubscription(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null;
  const reg = await navigator.serviceWorker.ready;
  return reg.pushManager.getSubscription();
}

export async function enablePush(): Promise<PushStatus> {
  if (!pushSupported()) return "unsupported";

  const permission = await Notification.requestPermission();
  if (permission !== "granted") return "denied";

  const res = await fetch(`http://${location.hostname}:8787/push/vapid-public-key`);
  const { key } = (await res.json()) as { key: string };
  if (!key) return "no-vapid-key"; // Backend hat pywebpush nicht installiert (siehe PushEngine).

  const reg = await navigator.serviceWorker.ready;
  const existing = await reg.pushManager.getSubscription();
  const sub =
    existing ??
    (await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(key) as BufferSource,
    }));
  backend.pushSubscribe(sub.toJSON() as PushSubscriptionJSON);
  return "enabled";
}

export async function disablePush(): Promise<void> {
  const sub = await currentPushSubscription();
  if (!sub) return;
  backend.pushUnsubscribe(sub.endpoint);
  await sub.unsubscribe();
}
