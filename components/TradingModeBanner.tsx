"use client";

import { useQuery } from "@tanstack/react-query";

export function TradingModeBanner() {
  const { data } = useQuery({
    queryKey: ["system-health"],
    queryFn: () => fetch("/api/trading/system-health").then((r) => r.json()),
    refetchInterval: 30_000,
  });

  const mode = data?.mode || "paper";
  const isLive = mode === "live";

  return (
    <div
      className={`w-full py-1 px-4 text-center text-sm font-bold ${
        isLive
          ? "bg-red-600 text-white"
          : "bg-green-600 text-white"
      }`}
    >
      {isLive ? "LIVE TRADING — Real Money" : "PAPER TRADING — Simulated"}
    </div>
  );
}
