import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

// PWA: registriert den Service Worker, damit APHELIOS auf dem Handy zum
// Home-Bildschirm hinzugefügt werden kann (siehe public/sw.js). Rein
// optional – schlägt die Registrierung fehl (z. B. kein HTTPS), läuft das
// HUD im Browser trotzdem normal weiter.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      /* PWA-Installierbarkeit ist ein Bonus, kein hartes Erfordernis */
    });
  });
}
