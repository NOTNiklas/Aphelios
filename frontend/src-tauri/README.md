# APHELIOS – Tauri-Shell (Windows-Desktop)

Dieses Verzeichnis macht aus dem HUD-Frontend eine native Windows-Desktop-App.
Der Build wird **auf einem Windows-System** durchgeführt und wurde in der
Linux-Cloud-Umgebung, in der das Grundgerüst entstand, bewusst nicht kompiliert.

## Voraussetzungen (Windows)

- [Rust](https://rustup.rs/)
- Microsoft Visual Studio C++ Build Tools
- WebView2 (auf Windows 11 vorinstalliert)
- Tauri CLI: `npm install -g @tauri-apps/cli` (oder als devDependency)

## Icons ergänzen

Vor dem ersten Build müssen App-Icons unter `src-tauri/icons/` liegen. Am
einfachsten per Tauri-CLI aus einem Quadrat-PNG generieren:

```bash
cd frontend
npx @tauri-apps/cli icon path/zu/aphelios-logo.png
```

## Entwicklung & Build

```bash
cd frontend
npm run tauri dev      # Desktop-Fenster mit Hot-Reload
npm run tauri build    # native Windows-App (.msi / .exe)
```

Das Fenster ist randlos und transparent konfiguriert (siehe `tauri.conf.json`),
passend zum holografischen HUD-Look.
