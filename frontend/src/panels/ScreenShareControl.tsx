/** Bildschirmfreigabe – Ersatz/Ergänzung für die Einzel-Screenshot-Befehle
 * (VisionEngine): der Nutzer teilt aktiv einen Bildschirm/ein Fenster über
 * die Browser-Screen-Capture-API, ein Canvas komprimiert periodisch einen
 * Frame als JPEG und schickt ihn an die Backend-ScreenShareEngine. Kein
 * echtes Video an Claude – nur der jeweils letzte Frame wird gehalten.
 *
 * Analyse auf Zuruf über "/bildschirm <Frage>" im Chat (siehe Console.tsx,
 * unverändert – kein neuer Chat-Eingabeweg nötig). Der Schalter hier
 * steuert nur den optionalen PROAKTIVEN Modus (ScreenShareEngine prüft
 * dann selbstständig alle 10s und meldet sich nur bei etwas Auffälligem).
 */
import { useRef, useState } from "react";
import { useBackend } from "../lib/ws";

const FRAME_INTERVAL_MS = 3000;
const JPEG_QUALITY = 0.6;
//: Frames verkleinern spart Bandbreite/Tokens, ohne für die Analyse
//: relevante Details (Text, Fehlermeldungen) zu verlieren.
const MAX_WIDTH = 1280;

export function ScreenShareControl() {
  const { sendScreenFrame, stopScreenShare, setScreenProactive } = useBackend();
  const [sharing, setSharing] = useState(false);
  const [proactive, setProactive] = useState(false);
  const streamRef = useRef<MediaStream | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function captureFrame() {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.videoWidth === 0) return;
    const scale = Math.min(1, MAX_WIDTH / video.videoWidth);
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    sendScreenFrame(canvas.toDataURL("image/jpeg", JPEG_QUALITY));
  }

  function stop() {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    videoRef.current = null;
    setSharing(false);
    setProactive(false);
    stopScreenShare();
  }

  async function start() {
    if (!navigator.mediaDevices?.getDisplayMedia) return;
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
    } catch {
      return; // Nutzer hat den Freigabe-Dialog abgebrochen.
    }
    streamRef.current = stream;

    const video = document.createElement("video");
    video.srcObject = stream;
    video.muted = true;
    await video.play();
    videoRef.current = video;
    canvasRef.current = document.createElement("canvas");

    // Nutzer beendet die Freigabe über den BROWSER-eigenen Dialog/die
    // Toolbar (nicht nur über unseren Button) – dann trotzdem sauber stoppen.
    stream.getVideoTracks()[0].addEventListener("ended", stop);

    setSharing(true);
    captureFrame();
    intervalRef.current = setInterval(captureFrame, FRAME_INTERVAL_MS);
  }

  function toggleProactive() {
    const next = !proactive;
    setProactive(next);
    setScreenProactive(next);
  }

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={sharing ? stop : start}
        className={`rounded border px-2.5 py-1 font-hud text-[11px] tracking-[0.25em] ${
          sharing
            ? "border-hud-danger/60 bg-hud-danger/15 text-hud-danger"
            : "border-hud-neon/30 text-hud-neon/70 hover:border-hud-neon/60 hover:text-hud-neon"
        }`}
        title="Bildschirm mit APHELIOS teilen – Analyse per '/bildschirm <Frage>' im Chat"
      >
        {sharing ? "● TEILEN BEENDEN" : "BILDSCHIRM TEILEN"}
      </button>
      {sharing && (
        <label className="flex items-center gap-1.5 font-hud text-[11px] text-hud-neon/70">
          <input type="checkbox" checked={proactive} onChange={toggleProactive} className="accent-hud-neon" />
          Proaktiv
        </label>
      )}
    </div>
  );
}
