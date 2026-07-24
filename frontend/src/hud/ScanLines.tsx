/** Scan-Animation: eine wandernde Lichtlinie plus feine horizontale Scanlines. */
export function ScanLines() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {/* Wandernde Lichtlinie (Top → Bottom). */}
      <div
        className="absolute inset-x-0 h-24 animate-scan"
        style={{
          background:
            "linear-gradient(to bottom, transparent, rgba(0,255,136,0.10), transparent)",
        }}
      />
      {/* Statische, sehr feine Scanlines für den CRT-Look. */}
      <div
        className="absolute inset-0 opacity-[0.06]"
        style={{
          backgroundImage:
            "repeating-linear-gradient(to bottom, rgba(0,255,136,0.6) 0px, rgba(0,255,136,0.6) 1px, transparent 1px, transparent 3px)",
        }}
      />
    </div>
  );
}
