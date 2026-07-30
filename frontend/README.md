# APHELIOS – Frontend (HUD)

Das holografische Iron-Man-HUD von APHELIOS: React + TypeScript + Tailwind CSS +
Framer Motion, gebaut mit Vite. Läuft als Web-App **und** – über die Tauri-Shell
in [`src-tauri/`](./src-tauri) – als native Windows-Desktop-App.

## Schnellstart

```bash
cd frontend
npm install
npm run dev
```

Öffne `http://localhost:5173`. Das HUD verbindet sich automatisch mit dem Backend
(`ws://localhost:8787/ws`). **Ohne laufendes Backend** speist es realistische
Mock-Daten ein und ist damit eigenständig lauffähig.

## Sprachaktivierung

Klicke das Mikrofon-Symbol in der AI-Konsole und sage **„Aphelios"**. Danach hört
das HUD zu, bis ein Stopp-Kommando fällt („Stop", „Danke Aphelios", „Beenden",
„Ruhemodus"). Nutzt die Web Speech API (Chromium-basierte Browser).

## Struktur

```
src/
├── hud/       Wiederverwendbare HUD-Primitive (Core, Ring, Gauge, Panel, …)
├── panels/    Layout-Bausteine (SystemStats, InfoPanels, Console, …)
├── voice/     Wake-Word-Hook (Web Speech API)
├── lib/       WebSocket-Client, Mock-Daten, Typen
├── store/     Zustand-Store (Live-Zustand des HUD)
└── App.tsx    Startscreen
```

## Desktop-Build

Siehe [`src-tauri/README.md`](./src-tauri/README.md). Design-Details:
[`../docs/design-system.md`](../docs/design-system.md).
