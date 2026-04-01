"use client";

import { useHyperliquidData } from "@/hooks/useHyperliquidData";

export function TradingModeBanner() {
  const hl = useHyperliquidData();

  const hlData = hl.data;
  const isLive = !!hlData && (hlData.portfolioValue > 0 || hlData.positions.length > 0);

  if (hl.isLoading) {
    return (
      <div className="w-full py-1 px-4 text-center text-sm font-bold bg-zinc-700 text-white">
        CONNECTING TO HYPERLIQUID&hellip;
      </div>
    );
  }

  return (
    <div
      className={`w-full py-1 px-4 text-center text-sm font-bold ${
        isLive ? "bg-red-600 text-white" : "bg-green-600 text-white"
      }`}
    >
      {isLive
        ? "LIVE TRADING \u2014 Real Money"
        : "PAPER TRADING \u2014 Simulated"}
    </div>
  );
}
