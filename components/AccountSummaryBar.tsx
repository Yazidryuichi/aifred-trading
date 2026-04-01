"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useHyperliquidWithWallet } from "@/hooks/useHyperliquidWithWallet";

export function AccountSummaryBar() {
  const [viewMode, setViewMode] = useState<"live" | "demo">("live");
  const hl = useHyperliquidWithWallet();

  // Secondary data source — demo/backtest metrics
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

  const hlData = hl.data;
  const hlAvailable = !!hlData && hlData.connected;
  const showLive = viewMode === "live" && hlAvailable;

  // LIVE data from Hyperliquid
  const liveBalance = hlData?.portfolioValue ?? 0;
  const livePnl = hlData?.positions.reduce((sum, p) => sum + p.unrealizedPnl, 0) ?? 0;
  const livePositions = hlData?.positions.length ?? 0;
  const liveExposure = hlData?.positions.reduce((sum, p) => sum + Math.abs(p.size) * p.entryPx, 0) ?? 0;
  const liveSpot = hlData?.spotBalances?.map(b => `${b.total.toFixed(2)} ${b.coin}`).join(", ") ?? "";

  // DEMO data from trading-data.json
  const demoBalance = performance?.summary?.currentEquity ?? 0;
  const demoPnl = performance?.summary?.totalPnl ?? 0;
  const demoPositions = typeof performance?.summary?.openPositions === "number"
    ? performance.summary.openPositions
    : (Array.isArray(performance?.openPositions) ? performance.openPositions.length : 0);
  const demoExposure = Array.isArray(performance?.openPositions)
    ? performance.openPositions.reduce(
        (sum: number, p: { size?: number; entry_price?: number }) =>
          sum + (p.size ?? 0) * (p.entry_price ?? 0), 0)
    : 0;

  // Display values based on mode
  const balance = showLive ? liveBalance : demoBalance;
  const totalPnl = showLive ? livePnl : demoPnl;
  const openPositions = showLive ? livePositions : demoPositions;
  const openExposure = showLive ? liveExposure : demoExposure;

  const startingEquity = balance - totalPnl;
  const totalPnlPct = startingEquity > 0 ? (totalPnl / startingEquity) * 100 : 0;
  const maxPositions = performance?.maxPositions ?? 5;
  const regime = performance?.regime ?? health?.regime ?? "unknown";
  const botStatus = health?.kill_switch_active ? "killed" : health?.status ?? "unknown";
  const botLabel = botStatus === "not_configured" ? "STANDALONE" : botStatus.toUpperCase();
  const botColor =
    botStatus === "running" ? "text-green-400" :
    botStatus === "killed" ? "text-red-400" :
    botStatus === "not_configured" ? "text-amber-400" :
    "text-yellow-400";

  return (
    <div className="w-full px-4 py-2 bg-white/5 border-b border-white/10 flex items-center gap-6 text-sm overflow-x-auto">
      {/* Mode toggle */}
      <div className="flex items-center gap-1 flex-shrink-0">
        <button
          onClick={() => setViewMode("live")}
          className={`px-2 py-0.5 rounded text-[10px] font-bold transition-all ${
            viewMode === "live"
              ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
              : "text-zinc-500 hover:text-zinc-300"
          }`}
        >
          LIVE
        </button>
        <button
          onClick={() => setViewMode("demo")}
          className={`px-2 py-0.5 rounded text-[10px] font-bold transition-all ${
            viewMode === "demo"
              ? "bg-amber-500/20 text-amber-400 border border-amber-500/40"
              : "text-zinc-500 hover:text-zinc-300"
          }`}
        >
          DEMO
        </button>
      </div>

      <div>
        <span className="text-gray-400">Balance: </span>
        <span className="text-white font-mono font-bold">
          ${balance.toFixed(2)}
          {showLive && liveSpot && (
            <span className="ml-1 text-[10px] text-zinc-500 font-normal">({liveSpot})</span>
          )}
        </span>
      </div>
      <div>
        <span className="text-gray-400">{showLive ? "Unrealized P&L: " : "Total P&L: "}</span>
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
        <span className={`font-bold ${botColor}`}>{botLabel}</span>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="text-gray-400">Exchange: </span>
        <span className={`inline-block w-1.5 h-1.5 rounded-full ${hlAvailable ? "bg-green-400" : "bg-red-400"}`} />
        <span className="text-white">Hyperliquid</span>
      </div>
    </div>
  );
}
