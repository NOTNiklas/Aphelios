/** Kleiner Hinweis unter Vorschau-Daten, die noch keine echte Verbindung haben. */
export function PreviewHint({ children }: { children: React.ReactNode }) {
  return <p className="mt-1 font-hud text-[10px] text-hud-neon/35">{children}</p>;
}
