"use client";

import { useHyperliquidData } from "@/hooks/useHyperliquidData";

export function TradingModeBanner() {
  const hl = useHyperliquidData();

  // Determine mode from actual Hyperliquid state — not from system-health API
  const hlData = hl.data;
  const isLive = !!hlData && (hlData.equity > 0 || hlData.positions.length > 0);

  return (
    <div
      className={`w-full py-1 px-4 text-center text-sm font-bold ${
        isLive
          ? "bg-red-600 text-white"
          : "bg-green-600 text-white"
      }`}
    >
      {isLive
        ? "LIVE TRADING \u2014 Real Money"
        : hl.isLoading
          ? "CONNECTING\u2026"
          : "PAPER TRADING \u2014 Simulated"}
    </div>
  );
}
