"use client";

import { useHyperliquidWithWallet } from "@/hooks/useHyperliquidWithWallet";
import { useQuery } from "@tanstack/react-query";
import { useViewMode } from "@/stores/viewMode";

function fmt(n: number, decimals = 2): string {
  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function HeroMetrics() {
  const { mode } = useViewMode();
  const hl = useHyperliquidWithWallet();

  const { data: performance } = useQuery({
    queryKey: ["performance"],
    queryFn: () => fetch("/api/trading/performance").then((r) => r.json()),
    refetchInterval: 10_000,
  });

  const hlData = hl.data;
  const hlAvailable = !!hlData && hlData.connected;
  const showLive = mode === "live" && hlAvailable;

  // LIVE data
  const liveEquity = hlData?.portfolioValue ?? 0;
  const liveAvailable = hlData?.availableBalance ?? 0;
  const livePnl = hlData?.positions.reduce((s, p) => s + p.unrealizedPnl, 0) ?? 0;
  const livePositions = hlData?.positions.length ?? 0;
  const liveMarginUsed = hlData?.marginUsed ?? 0;

  // DEMO data
  const demoEquity = performance?.summary?.currentEquity ?? 0;
  const demoPnl = performance?.summary?.totalPnl ?? 0;
  const demoPositions =
    typeof performance?.summary?.openPositions === "number"
      ? performance.summary.openPositions
      : Array.isArray(performance?.openPositions)
        ? performance.openPositions.length
        : 0;

  // Display values
  const equity = showLive ? liveEquity : demoEquity;
  const available = showLive ? liveAvailable : demoEquity;
  const totalPnl = showLive ? livePnl : demoPnl;
  const positions = showLive ? livePositions : demoPositions;
  const marginUsed = showLive ? liveMarginUsed : 0;

  const freePercent = equity > 0 ? (available / equity) * 100 : 100;
  const marginPercent = equity > 0 ? (marginUsed / equity) * 100 : 0;
  const startingEquity = equity - totalPnl;
  const pnlPercent = startingEquity > 0 ? (totalPnl / startingEquity) * 100 : 0;

  const isDemo = mode === "demo" || !hlAvailable;

  const cards = [
    {
      label: "TOTAL EQUITY",
      value: `$${fmt(equity)}`,
      subtitle: "USDC",
      accent: "text-white",
    },
    {
      label: "AVAILABLE",
      value: `$${fmt(available)}`,
      subtitle: `${fmt(freePercent, 0)}% Free`,
      accent: "text-white",
    },
    {
      label: "TOTAL P&L",
      value: `${totalPnl >= 0 ? "+" : ""}$${fmt(totalPnl)}`,
      subtitle: `${pnlPercent >= 0 ? "+" : ""}${fmt(pnlPercent, 1)}%`,
      accent: totalPnl >= 0 ? "text-emerald-400" : "text-red-400",
    },
    {
      label: "POSITIONS",
      value: String(positions),
      subtitle: `Margin: ${fmt(marginPercent, 0)}%`,
      accent: positions > 0 ? "text-emerald-400" : "text-zinc-400",
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {cards.map((card) => (
        <div
          key={card.label}
          className="relative bg-white/5 border border-white/10 rounded-xl p-5 backdrop-blur-sm"
        >
          {isDemo && (
            <span className="absolute top-2 right-2 text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 border border-amber-500/30">
              DEMO
            </span>
          )}
          <p
            className="text-[10px] text-zinc-500 tracking-widest uppercase mb-1"
            style={{ fontFamily: "Outfit, sans-serif" }}
          >
            {card.label}
          </p>
          <p
            className={`text-2xl font-bold ${card.accent}`}
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            {card.value}
          </p>
          <p
            className="text-xs text-zinc-500 mt-1"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            {card.subtitle}
          </p>
        </div>
      ))}
    </div>
  );
}
