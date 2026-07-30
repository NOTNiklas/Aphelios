import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { Dashboard } from "./panels/Dashboard";
import "./index.css";

// Kein Router-Paket für eine einzelne zusätzliche Seite – ein simpler
// Pfad-Check reicht (siehe Dashboard.tsx). "/" bleibt weiterhin das
// normale HUD, unverändert für alle bestehenden Aufrufer (PWA-Icon etc.).
const isDashboard = window.location.pathname.replace(/\/+$/, "") === "/dashboard";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{isDashboard ? <Dashboard /> : <App />}</React.StrictMode>,
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
