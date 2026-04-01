"use client";

const TRADING_MODE = process.env.NEXT_PUBLIC_TRADING_MODE || "paper";

export function TradingModeBanner() {
  const isLive = TRADING_MODE === "live";

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
