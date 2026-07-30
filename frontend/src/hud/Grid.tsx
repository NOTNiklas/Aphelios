/** Dezenter Hintergrund: Raster + radiale Vignette. Reines CSS, keine Animation. */
export function Grid() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="absolute inset-0 opacity-[0.12]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(0,255,136,0.35) 1px, transparent 1px)," +
            "linear-gradient(90deg, rgba(0,255,136,0.35) 1px, transparent 1px)",
          backgroundSize: "44px 44px",
        }}
      />
      {/* Vignette – lenkt den Blick zur Mitte. */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(circle at 50% 45%, transparent 30%, rgba(0,0,0,0.7) 75%, #000 100%)",
        }}
      />
    </div>
  );
}
