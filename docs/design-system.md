# Design-System – Iron-Man-HUD

Das APHELIOS-Interface ist an das HUD aus Iron Man angelehnt: schwarz, holografisch,
neon-grün, extrem clean. Es soll aussehen wie aus einem Science-Fiction-Film – niemals
überladen.

## Farb-Tokens

| Token | Wert | Verwendung |
|---|---|---|
| `--hud-bg` | `#000000` | Hintergrund |
| `--hud-neon` | `#00ff88` | Primärakzent, Glow, Linien |
| `--hud-dark-green` | `#003d2b` | Flächen, Ränder, Tiefe |
| `--hud-neon-dim` | `rgba(0,255,136,.45)` | Sekundärtext, Skalen |
| `--hud-glass` | `rgba(0,40,28,.25)` | Glassmorphism-Panels |
| `--hud-danger` | `#ff3b5c` | Warnungen / kritische Werte |

## Effekte

- **Glassmorphism** – halbtransparente Panels mit `backdrop-filter: blur()`
- **Glow** – `box-shadow` / `text-shadow` in Neon-Grün
- **Rotierende Ringe** – langsame, endlose Rotation (Framer Motion)
- **Scan-Linien** – vertikal wandernde Lichtlinie
- **Partikel** – dezente, driftende Punkte im Hintergrund
- **Puls** – atmende Opazität für „lebendige" Elemente
- **Typewriter** – animierte, Token-weise erscheinende Konsolen-Antworten
- **Denk-Punkte** – drei nacheinander hüpfende Punkte in der AI-Konsole,
  solange auf das erste Antwort-Token gewartet wird (bevor der Typewriter
  überhaupt etwas zu zeigen hat) – macht die sonst stille Wartezeit sichtbar

## Typografie

Futuristische, technische Schrift. Alpha 1.0 bündelt **Orbitron** (Display) und
**Rajdhani** (Fließtext/HUD-Labels) **lokal** (kein externes CDN), mit
System-Monospace als Fallback. Technische Labels sind englisch und in Versalien
(`CPU`, `RAM`, `ONLINE`), die AI-Konsole spricht deutsch.

## Layout (Startscreen)

```
┌───────────────────────────────────────────────────────────┐
│  ⌁ scan line · particles · grid ················· HUD-Ringe │
│                                                            │
│  ┌── SYSTEM ──┐          ⬡  APHELIOS          ┌── INFO ──┐  │
│  │ CPU   ▓▓▓░ │        (rotierender Core)     │ Kalender │  │
│  │ RAM   ▓▓░░ │            ONLINE             │ Mails    │  │
│  │ GPU   ▓░░░ │                               │ Aufgaben │  │
│  │ …         │                               │ …        │  │
│  └───────────┘                               └──────────┘  │
│                                                            │
│  ┌────────────────── AI-CONSOLE ─────────────────────────┐ │
│  │ > … animierte Antwort …                       ◉ Voice │ │
│  └───────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────┘
```

## Prinzipien

1. **Clean vor voll** – lieber Weißraum als noch ein Datenfeld.
2. **Bewegung mit Bedeutung** – Animation zeigt Zustand, nicht Dekoration.
3. **Ein Akzent** – Neon-Grün trägt das Interface; andere Farben nur für Status.
4. **60 fps** – Animationen laufen GPU-beschleunigt (`transform`, `opacity`).

## Desktop-Build (Tauri)

Das Frontend läuft als Web-App **und** – über die Tauri-Shell in
`frontend/src-tauri/` – als native Windows-Desktop-App. Der Tauri-Build erfolgt auf
einem Windows-System mit installiertem Rust:

```bash
cd frontend
npm run tauri build
```
