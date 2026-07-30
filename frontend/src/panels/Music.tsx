/** Musik-Panel – Spotify-Wiedergabe (Play/Pause/Skip/Lautstärke/Like).
 *
 * Zeigt **echte Daten** der Backend-``MusicEngine``, sobald Spotify über
 * ``docs/integrations.md`` verbunden ist – ohne Verbindung erscheint eine
 * Vorschau mit einem Beispiel-Song inkl. Hinweis, analog zu Kalender/Mails
 * in ``InfoPanels.tsx``. Kreisförmiger Player mit rotierendem Album-Cover
 * und Fortschritts-Ring statt des rechteckigen Listen-Layouts der übrigen
 * Info-Panels – an das vom Nutzer gelieferte Referenzdesign angelehnt,
 * aber ins Iron-Man-HUD-Farbschema (Neon-Grün, Glassmorphism) übersetzt.
 */
import { motion, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { Panel } from "../hud/Panel";
import { MOCK_MUSIC } from "../lib/mock";
import { useBackend } from "../lib/ws";
import { useHud } from "../store/hud";
import { PreviewHint } from "./PreviewHint";

const RING_SIZE = 152;
const STROKE = 3.5;
const RADIUS = RING_SIZE / 2 - STROKE * 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function formatMs(ms: number | null | undefined): string {
  if (ms == null || Number.isNaN(ms) || ms < 0) return "--:--";
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function PlayIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
      <path d="M8 5v14l11-7z" />
    </svg>
  );
}
function PauseIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
      <path d="M7 5h4v14H7zM13 5h4v14h-4z" />
    </svg>
  );
}
function SkipBackIcon() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor">
      <path d="M6 5h2v14H6zM20 5v14l-11-7z" />
    </svg>
  );
}
function SkipForwardIcon() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor">
      <path d="M16 5h2v14h-2zM4 5v14l11-7z" />
    </svg>
  );
}
function HeartIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="1.8"
    >
      <path d="M12 21s-7.5-4.6-10-9.3C.6 8.1 2.6 5 6 5c2 0 3.4 1 6 3.4C14.6 6 16 5 18 5c3.4 0 5.4 3.1 4 6.7C19.5 16.4 12 21 12 21z" />
    </svg>
  );
}
function NoteIcon() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor" className="text-hud-neon/40">
      <path d="M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM21 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z" />
    </svg>
  );
}

/** Lässt den Fortschritt zwischen den Backend-Updates (alle paar Sekunden,
 * siehe MusicEngine-Poll-Intervall) lokal weiterlaufen statt nur alle paar
 * Sekunden sichtbar zu springen – tickt alle 250ms neu gegen die seit dem
 * letzten Update vergangene Wall-Clock-Zeit, ohne eigene Server-Anfragen. */
function useSmoothProgress(
  anchorMs: number | null | undefined,
  anchorAtSec: number | null | undefined,
  isPlaying: boolean,
  durationMs: number | null | undefined,
): number | null | undefined {
  const [, forceTick] = useState(0);

  useEffect(() => {
    if (!isPlaying || anchorMs == null || anchorAtSec == null) return;
    const id = setInterval(() => forceTick((t) => t + 1), 250);
    return () => clearInterval(id);
  }, [isPlaying, anchorMs, anchorAtSec]);

  if (anchorMs == null || !isPlaying || anchorAtSec == null) return anchorMs;
  const elapsed = Math.max(0, Date.now() - anchorAtSec * 1000);
  const projected = anchorMs + elapsed;
  return durationMs != null ? Math.min(projected, durationMs) : projected;
}

/** Sofortiges lokales Feedback beim Ziehen, statt direkt an den
 * Server-Wert gebunden zu sein (der erst nach Netzwerk-Roundtrip
 * nachkommt und den Regler sonst "zurückspringen" lässt). Sendet erst
 * ``debounceMs`` nach der letzten Änderung – sonst würde jeder
 * Zwischenschritt beim Ziehen einen eigenen Spotify-Aufruf auslösen. */
function useVolumeDraft(
  serverValue: number,
  send: (value: number) => void,
  debounceMs = 300,
): [number, (value: number) => void] {
  const [draft, setDraft] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (draft != null && draft === serverValue) setDraft(null);
  }, [serverValue, draft]);

  function onChange(value: number) {
    setDraft(value);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      send(value);
      timerRef.current = null;
    }, debounceMs);
  }

  return [draft ?? serverValue, onChange];
}

interface CircleButtonProps {
  onClick: () => void;
  children: React.ReactNode;
  big?: boolean;
  active?: boolean;
  title: string;
}
function CircleButton({ onClick, children, big, active, title }: CircleButtonProps) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={`flex shrink-0 items-center justify-center rounded-full border transition-colors ${
        big ? "h-10 w-10" : "h-7 w-7"
      } ${
        big
          ? "border-hud-neon bg-hud-neon text-black shadow-glow-sm hover:bg-white"
          : active
            ? "border-hud-neon/60 text-hud-neon"
            : "border-hud-neon/25 text-hud-neon/70 hover:border-hud-neon/60 hover:text-hud-neon"
      }`}
    >
      {children}
    </button>
  );
}

/** Rotierendes Album-Cover mit umlaufendem Fortschritts-Ring. */
function AlbumRing({
  albumArt,
  isPlaying,
  progressMs,
  durationMs,
}: {
  albumArt?: string | null;
  isPlaying: boolean;
  progressMs: number | null | undefined;
  durationMs: number | null | undefined;
}) {
  const reduce = useReducedMotion();
  const pct =
    durationMs && durationMs > 0 ? Math.max(0, Math.min(100, ((progressMs ?? 0) / durationMs) * 100)) : 0;
  const dashOffset = CIRCUMFERENCE * (1 - pct / 100);

  return (
    <div className="relative" style={{ width: RING_SIZE, height: RING_SIZE }}>
      <svg width={RING_SIZE} height={RING_SIZE} viewBox={`0 0 ${RING_SIZE} ${RING_SIZE}`} className="absolute inset-0">
        <circle
          cx={RING_SIZE / 2}
          cy={RING_SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke="rgba(0,255,136,0.15)"
          strokeWidth={STROKE}
        />
        <motion.circle
          cx={RING_SIZE / 2}
          cy={RING_SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke="#00ff88"
          strokeWidth={STROKE}
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          style={{ filter: "drop-shadow(0 0 4px rgba(0,255,136,0.7))" }}
          transform={`rotate(-90 ${RING_SIZE / 2} ${RING_SIZE / 2})`}
          initial={false}
          animate={{ strokeDashoffset: dashOffset }}
          transition={reduce ? { duration: 0 } : { duration: 0.25, ease: "linear" }}
        />
      </svg>
      <div
        className="absolute rounded-full bg-hud-dark-green"
        style={{ inset: STROKE * 3 }}
      >
        <motion.div
          className="h-full w-full overflow-hidden rounded-full border border-hud-neon/25"
          animate={reduce || !isPlaying ? undefined : { rotate: 360 }}
          transition={{ duration: 16, repeat: Infinity, ease: "linear" }}
        >
          {albumArt ? (
            <img src={albumArt} alt="" className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full w-full items-center justify-center">
              <NoteIcon />
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
}

export function Music() {
  const music = useHud((s) => s.music);
  const { musicPlay, musicPause, musicNext, musicPrevious, musicLike, musicVolume } = useBackend();

  // Abgeleitete Werte + Hooks IMMER unbedingt aufrufen (Rules of Hooks) –
  // erst danach je nach Zustand (Fehler/Idle/normal) verzweigen, welches
  // JSX zurückgegeben wird.
  const isPreview = !music?.track;
  const track = music?.track ?? MOCK_MUSIC.track;
  const artist = music?.artist ?? MOCK_MUSIC.artist;
  const albumArt = music?.album_art ?? null;
  const isPlaying = isPreview ? MOCK_MUSIC.is_playing : Boolean(music?.is_playing);
  const rawProgressMs = isPreview ? MOCK_MUSIC.progress_ms : music?.progress_ms;
  const durationMs = isPreview ? MOCK_MUSIC.duration_ms : music?.duration_ms;
  const liked = Boolean(music?.liked);
  const serverVolume = music?.volume ?? 70;

  const progressMs = useSmoothProgress(
    rawProgressMs,
    isPreview ? null : music?.updated_at,
    isPlaying,
    durationMs,
  );
  const [displayVolume, handleVolumeChange] = useVolumeDraft(serverVolume, musicVolume);

  if (music?.error) {
    return (
      <Panel title="Musik" delay={0.02}>
        <p className="font-hud text-[13px] text-hud-danger">{music.error}</p>
      </Panel>
    );
  }

  // Verbunden, aber gerade nichts aktiv (Spotify läuft nirgends).
  if (music && music.connected && !music.track) {
    return (
      <Panel title="Musik" delay={0.02}>
        <p className="font-hud text-[13px] text-hud-neon/50">
          Kein Song aktiv – starte Spotify auf einem Gerät.
        </p>
      </Panel>
    );
  }

  return (
    <Panel title="Musik" delay={0.02}>
      <div className="flex flex-col items-center gap-3">
        <AlbumRing albumArt={albumArt} isPlaying={isPlaying} progressMs={progressMs} durationMs={durationMs} />

        <div className="max-w-[200px] text-center">
          <div className="truncate font-display text-sm text-hud-neon text-glow">{track}</div>
          <div className="truncate font-hud text-xs text-hud-neon-dim">{artist}</div>
        </div>

        <div className="flex w-full max-w-[200px] items-center justify-between font-mono text-[10px] text-hud-neon/60">
          <span>{formatMs(progressMs)}</span>
          <span>{formatMs(durationMs)}</span>
        </div>

        <div className="flex items-center gap-3">
          <CircleButton title="Gefällt mir" active={liked} onClick={() => musicLike(!liked)}>
            <HeartIcon filled={liked} />
          </CircleButton>
          <CircleButton title="Zurück" onClick={musicPrevious}>
            <SkipBackIcon />
          </CircleButton>
          <CircleButton title={isPlaying ? "Pause" : "Play"} big onClick={isPlaying ? musicPause : musicPlay}>
            {isPlaying ? <PauseIcon /> : <PlayIcon />}
          </CircleButton>
          <CircleButton title="Weiter" onClick={musicNext}>
            <SkipForwardIcon />
          </CircleButton>
          <div className="w-7" />
        </div>

        <input
          type="range"
          min={0}
          max={100}
          value={displayVolume}
          onChange={(e) => handleVolumeChange(Number(e.target.value))}
          className="h-1 w-full max-w-[200px] accent-hud-neon"
          title={`Lautstärke: ${displayVolume}%`}
        />

        {isPreview && <PreviewHint>Vorschau — Spotify via docs/integrations.md verbinden</PreviewHint>}
      </div>
    </Panel>
  );
}
