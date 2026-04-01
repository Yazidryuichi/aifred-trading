"use client";

import { useQuery } from "@tanstack/react-query";

export function AccountSummaryBar() {
  const { data: performance } = useQuery({
    queryKey: ["performance"],
    queryFn: () => fetch("/api/trading/performance").then((r) => r.json()),
    refetchInterval: 10_000,
  });

  const { data: health } = useQuery({
    queryKey: ["system-health"],
    queryFn: () => fetch("/api/trading/system-health").then((r) => r.json()),
    refetchInterval: 30_000,
  });

  const balance = performance?.totalBalance ?? 0;
  const dailyPnl = performance?.dailyPnl ?? 0;
  const dailyPnlPct = performance?.dailyPnlPct ?? 0;
  const openExposure = performance?.openExposure ?? 0;
  const openPositions = typeof performance?.openPositions === "number"
    ? performance.openPositions
    : (performance?.summary?.openPositions ?? 0);
  const maxPositions = performance?.maxPositions ?? 2;
  const regime = health?.regime ?? "unknown";
  const botStatus = health?.kill_switch_active ? "killed" : health?.status ?? "unknown";

  return (
    <div className="w-full px-4 py-2 bg-white/5 border-b border-white/10 flex items-center gap-6 text-sm overflow-x-auto">
      <div>
        <span className="text-gray-400">Balance: </span>
        <span className="text-white font-mono font-bold">${balance.toFixed(2)}</span>
      </div>
      <div>
        <span className="text-gray-400">Daily P&L: </span>
        <span className={`font-mono font-bold ${dailyPnl >= 0 ? "text-green-400" : "text-red-400"}`}>
          {dailyPnl >= 0 ? "+" : ""}${dailyPnl.toFixed(2)} ({dailyPnlPct >= 0 ? "+" : ""}{dailyPnlPct.toFixed(1)}%)
        </span>
      </div>
      <div>
        <span className="text-gray-400">Exposure: </span>
        <span className="text-white font-mono">${openExposure.toFixed(2)}</span>
      </div>
      <div>
        <span className="text-gray-400">Positions: </span>
        <span className="text-white font-mono">{openPositions}/{maxPositions}</span>
      </div>
      <div>
        <span className="text-gray-400">Regime: </span>
        <span className="text-white capitalize">{regime}</span>
      </div>
      <div>
        <span className="text-gray-400">Bot: </span>
        <span className={`font-bold ${
          botStatus === "running" ? "text-green-400" :
          botStatus === "killed" ? "text-red-400" : "text-yellow-400"
        }`}>
          {botStatus.toUpperCase()}
        </span>
      </div>
    </div>
  );
}
