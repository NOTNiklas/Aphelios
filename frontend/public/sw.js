// Minimaler Service Worker – macht APHELIOS auf dem Handy "installierbar"
// (Zum-Home-Bildschirm-hinzufügen, eigenes App-Fenster ohne Browserleiste).
//
// Cached bewusst NICHT aggressiv: Das HUD lebt von Live-Daten über
// WebSocket (System-Stats, Wetter, Mail, Kalender, Chat) – ein Offline-Cache
// würde hier nur veraltete Werte vortäuschen. Der Service Worker existiert
// nur, weil Browser einen registrierten fetch-Handler als Voraussetzung für
// die "Installierbar"-Erkennung verlangen.

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  event.respondWith(fetch(event.request));
});

// Web-Push: zeigt eine System-Benachrichtigung, auch wenn kein Tab offen ist
// (z. B. Morgen-Briefing, siehe lib/push.ts). Payload ist JSON
// ({title, body, url}) – ein Text-Fallback fängt Sonderfälle ab, in denen der
// Push-Dienst die Nutzdaten nicht wie erwartet zustellt.
self.addEventListener("push", (event) => {
  let payload = { title: "APHELIOS", body: "", url: "/" };
  try {
    if (event.data) payload = { ...payload, ...event.data.json() };
  } catch {
    if (event.data) payload.body = event.data.text();
  }
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      data: { url: payload.url || "/" },
    }),
  );
});

// Klick auf die Benachrichtigung: vorhandenen APHELIOS-Tab fokussieren statt
// blind einen neuen zu öffnen.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data?.url || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window" }).then((list) => {
      for (const client of list) {
        if ("focus" in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow(url);
      return undefined;
    }),
  );
});
