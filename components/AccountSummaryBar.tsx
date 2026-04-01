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

  const balance = performance?.summary?.currentEquity ?? 0;
  const totalPnl = performance?.summary?.totalPnl ?? 0;
  const startingEquity = balance - totalPnl;
  const totalPnlPct = startingEquity > 0 ? (totalPnl / startingEquity) * 100 : 0;
  const openPositionsArr = Array.isArray(performance?.openPositions)
    ? performance.openPositions
    : [];
  const openExposure = openPositionsArr.reduce(
    (sum: number, p: { size?: number; entry_price?: number }) =>
      sum + (p.size ?? 0) * (p.entry_price ?? 0),
    0,
  );
  const openPositions = typeof performance?.summary?.openPositions === "number"
    ? performance.summary.openPositions
    : openPositionsArr.length;
  const maxPositions = performance?.maxPositions ?? 5;
  const regime = performance?.regime ?? health?.regime ?? "unknown";
  const botStatus = health?.kill_switch_active ? "killed" : health?.status ?? "unknown";
  const exchangeConnected = health?.components?.some(
    (c: { name: string; status: string }) =>
      c.name.includes("Hyperliquid") && c.status === "healthy"
  ) ?? false;

  const botLabel = botStatus === "not_configured" ? "STANDALONE" : botStatus.toUpperCase();
  const botColor =
    botStatus === "running" ? "text-green-400" :
    botStatus === "killed" ? "text-red-400" :
    botStatus === "not_configured" ? "text-amber-400" :
    "text-yellow-400";

  return (
    <div className="w-full px-4 py-2 bg-white/5 border-b border-white/10 flex items-center gap-6 text-sm overflow-x-auto">
      <div>
        <span className="text-gray-400">Balance: </span>
        <span className="text-white font-mono font-bold">${balance.toFixed(2)}</span>
      </div>
      <div>
        <span className="text-gray-400">Total P&L: </span>
        <span className={`font-mono font-bold ${totalPnl >= 0 ? "text-green-400" : "text-red-400"}`}>
          {totalPnl >= 0 ? "+" : ""}${totalPnl.toFixed(2)} ({totalPnlPct >= 0 ? "+" : ""}{totalPnlPct.toFixed(1)}%)
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
        <span className={`font-bold ${botColor}`}>
          {botLabel}
        </span>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="text-gray-400">Exchange: </span>
        <span className={`inline-block w-1.5 h-1.5 rounded-full ${exchangeConnected ? "bg-green-400" : "bg-red-400"}`} />
        <span className="text-white">Hyperliquid</span>
      </div>
    </div>
  );
}
