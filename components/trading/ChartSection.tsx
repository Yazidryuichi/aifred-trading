"use client";

import { useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { SymbolSelector } from "@/components/trading/SymbolSelector";
import { TimeframeSelector } from "@/components/trading/TimeframeSelector";

// Dynamic import with SSR disabled — the TradingView widget injects scripts
// into the DOM and cannot run server-side.
const MarketChart = dynamic(
  () =>
    import("@/components/trading/MarketChart").then((mod) => mod.MarketChart),
  { ssr: false }
);

type ChartTab = "equity" | "market";

export function ChartSection() {
  const [activeTab, setActiveTab] = useState<ChartTab>("market");
  const [symbol, setSymbol] = useState("BINANCE:BTCUSDT");
  const [interval, setInterval] = useState("60");

  const handleSymbolChange = useCallback((s: string) => setSymbol(s), []);
  const handleIntervalChange = useCallback((i: string) => setInterval(i), []);

  return (
    <div className="bg-white/5 border border-white/10 rounded-2xl p-4">
      {/* Tab bar */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-1">
          <button
            onClick={() => setActiveTab("equity")}
            className={`px-4 py-1.5 text-sm font-medium rounded-lg transition-colors ${
              activeTab === "equity"
                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            Account Equity Curve
          </button>
          <button
            onClick={() => setActiveTab("market")}
            className={`px-4 py-1.5 text-sm font-medium rounded-lg transition-colors ${
              activeTab === "market"
                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            Market Chart
          </button>
        </div>

        {/* Selectors (only visible on Market tab) */}
        {activeTab === "market" && (
          <div className="flex items-center gap-3 flex-wrap">
            <TimeframeSelector value={interval} onChange={handleIntervalChange} />
          </div>
        )}
      </div>

      {/* Symbol selector row (only on Market tab) */}
      {activeTab === "market" && (
        <div className="mb-3">
          <SymbolSelector value={symbol} onChange={handleSymbolChange} />
        </div>
      )}

      {/* Tab content */}
      {activeTab === "equity" ? (
        <div className="flex items-center justify-center rounded-xl border border-white/10 bg-[#06060a] h-[400px]">
          <p className="text-zinc-500 text-sm">
            Equity curve coming soon&hellip;
          </p>
        </div>
      ) : (
        <MarketChart symbol={symbol} interval={interval} theme="dark" height={400} />
      )}
    </div>
  );
}
