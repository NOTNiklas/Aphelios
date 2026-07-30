/** Trading-Dashboard – Popup über einen TopBar-Button (siehe TopBar.tsx).
 *
 * Zeigt eine Watchlist mit echten Kursen der Backend-``StockEngine`` (kein
 * API-Key nötig, Yahoo-Finance-Chart-Endpunkt) links und rechts einen
 * eingebetteten TradingView-Chart für das ausgewählte Symbol – TradingViews
 * offizielles, kostenloses Embed-Widget (kein eigener Key/Vertrag nötig),
 * dieselbe Datenquelle, die auch auf unzähligen anderen Finanz-Websites
 * läuft. Der Chart braucht KEIN Backend – das Widget lädt seine Daten
 * direkt von TradingView; nur die Watchlist-Zeilen und die Chat-Auskunft
 * ("/aktie <Symbol>", Claude-Werkzeug ``get_stock_quote``) kommen von der
 * StockEngine.
 *
 * Overlay-Muster identisch zu ``ConfirmDialog.tsx`` (absolute inset-0,
 * Glass-Karte), damit sich das HUD konsistent anfühlt.
 */
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { MOCK_STOCKS } from "../lib/mock";
import { useHud } from "../store/hud";
import { PreviewHint } from "./PreviewHint";

/** Injiziert TradingViews offizielles Advanced-Chart-Embed-Skript – das
 * Widget unterstützt keine Props-Updates, deshalb bei jedem Symbolwechsel
 * Container leeren und neu aufbauen (TradingViews eigenes, dokumentiertes
 * Einbettungsmuster: Container-Div + Script-Tag mit JSON-Konfiguration als
 * Textinhalt). */
function TradingViewChart({ symbol }: { symbol: string }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !symbol) return;
    container.innerHTML = "";

    const widgetDiv = document.createElement("div");
    widgetDiv.className = "tradingview-widget-container__widget";
    widgetDiv.style.height = "100%";
    widgetDiv.style.width = "100%";
    container.appendChild(widgetDiv);

    const script = document.createElement("script");
    script.type = "text/javascript";
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async = true;
    script.text = JSON.stringify({
      autosize: true,
      symbol,
      interval: "D",
      timezone: "Etc/UTC",
      theme: "dark",
      style: "1",
      locale: "de_DE",
      backgroundColor: "rgba(0, 0, 0, 1)",
      gridColor: "rgba(0, 255, 136, 0.06)",
      hide_top_toolbar: false,
      allow_symbol_change: true,
      support_host: "https://www.tradingview.com",
    });
    container.appendChild(script);

    return () => {
      container.innerHTML = "";
    };
  }, [symbol]);

  return <div className="tradingview-widget-container h-full w-full" ref={containerRef} />;
}

function ChangeBadge({ change, percent }: { change: number | null; percent: number | null }) {
  if (change == null || percent == null) {
    return <span className="font-mono text-[11px] text-hud-neon/40">n/a</span>;
  }
  const positive = change >= 0;
  return (
    <span className={`font-mono text-[11px] tabular-nums ${positive ? "text-hud-neon" : "text-hud-danger"}`}>
      {positive ? "+" : ""}
      {percent.toFixed(2)}%
    </span>
  );
}

export function TradingDashboard() {
  const tradingOpen = useHud((s) => s.tradingOpen);
  const setTradingOpen = useHud((s) => s.setTradingOpen);
  const stocks = useHud((s) => s.stocks);

  const quotes = stocks?.quotes && stocks.quotes.length > 0 ? stocks.quotes : MOCK_STOCKS;
  const isPreview = !stocks?.quotes || stocks.quotes.length === 0;

  const [activeSymbol, setActiveSymbol] = useState(quotes[0]?.symbol ?? "AAPL");
  const [searchInput, setSearchInput] = useState("");

  // Beim ersten echten Watchlist-Update (Preview -> real) auf das erste
  // ECHTE Symbol wechseln statt beim Preview-Platzhalter zu bleiben.
  useEffect(() => {
    if (stocks?.quotes && stocks.quotes.length > 0) {
      setActiveSymbol((current) =>
        stocks.quotes!.some((q) => q.symbol === current) ? current : stocks.quotes![0].symbol,
      );
    }
  }, [stocks?.quotes]);

  function submitSearch(e: React.FormEvent) {
    e.preventDefault();
    const symbol = searchInput.trim().toUpperCase();
    if (symbol) setActiveSymbol(symbol);
    setSearchInput("");
  }

  return (
    <AnimatePresence>
      {tradingOpen && (
        <motion.div
          className="absolute inset-0 z-50 grid place-items-center p-4"
          style={{ background: "rgba(0,0,0,0.65)", backdropFilter: "blur(2px)" }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={() => setTradingOpen(false)}
        >
          <motion.div
            initial={{ scale: 0.96, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.96, opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={(e) => e.stopPropagation()}
            className="glass flex h-[min(88vh,760px)] w-[min(96vw,1180px)] flex-col overflow-hidden rounded-lg shadow-glow"
          >
            {/* Kopfzeile */}
            <div className="flex items-center justify-between border-b border-hud-neon/15 px-5 py-3">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-hud-neon animate-pulse-soft" />
                <h2 className="font-display text-sm tracking-[0.25em] text-hud-neon text-glow">
                  TRADING DASHBOARD
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setTradingOpen(false)}
                className="rounded border border-hud-neon/30 px-3 py-1 font-hud text-xs tracking-widest text-hud-neon/70 hover:border-hud-neon/60 hover:text-hud-neon"
              >
                SCHLIESSEN ✕
              </button>
            </div>

            <div className="flex min-h-0 flex-1">
              {/* Watchlist */}
              <div className="flex w-64 shrink-0 flex-col border-r border-hud-neon/15">
                <form onSubmit={submitSearch} className="border-b border-hud-neon/15 p-3">
                  <input
                    value={searchInput}
                    onChange={(e) => setSearchInput(e.target.value)}
                    placeholder="Symbol, z. B. NVDA"
                    className="w-full rounded border border-hud-neon/25 bg-black/40 px-2 py-1.5 font-mono text-xs text-hud-neon placeholder:text-hud-neon/30 focus:border-hud-neon/60 focus:outline-none"
                  />
                </form>
                <div className="flex-1 overflow-y-auto p-2">
                  {quotes.map((q) => (
                    <button
                      key={q.symbol}
                      type="button"
                      onClick={() => setActiveSymbol(q.symbol)}
                      className={`mb-1 flex w-full flex-col rounded px-3 py-2 text-left transition-colors ${
                        activeSymbol === q.symbol
                          ? "border border-hud-neon/50 bg-hud-neon/10"
                          : "border border-transparent hover:bg-hud-neon/5"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-hud text-sm text-hud-neon">{q.symbol}</span>
                        <ChangeBadge change={q.change} percent={q.change_percent} />
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="truncate font-hud text-[11px] text-hud-neon/50">{q.name}</span>
                        <span className="font-mono text-[11px] tabular-nums text-hud-neon/80">
                          {q.price.toLocaleString("de-DE", { maximumFractionDigits: 2 })} {q.currency}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
                {stocks?.error && <p className="p-3 font-hud text-[11px] text-hud-danger">{stocks.error}</p>}
                {isPreview && (
                  <div className="p-3">
                    <PreviewHint>Vorschau — Backend liefert echte Kurse automatisch (kein Key nötig)</PreviewHint>
                  </div>
                )}
              </div>

              {/* Chart */}
              <div className="min-w-0 flex-1 bg-black">
                <TradingViewChart symbol={activeSymbol} />
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
