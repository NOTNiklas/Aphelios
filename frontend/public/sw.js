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
