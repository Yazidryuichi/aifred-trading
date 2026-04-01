"use client";

import { useEffect, useState } from "react";
import { StatCard } from "@/components/trading/StatCard";
import { TradeHistory } from "@/components/trading/TradeHistory";

interface SideStats {
  trades: number;
  winRate: number;
  totalPnl: number;
  avgPnl: number;
}

interface SymbolPerf {
  symbol: string;
  trades: number;
  winRate: number;
  pnl: number;
}

interface StatsData {
  success: boolean;
  totalTrades: number;
  winRate: number;
  totalPnl: number;
  profitFactor: number;
  plRatio: number;
  sharpeRatio: number;
  maxDrawdown: number;
  avgWin: number;
  avgLoss: number;
  netPnl: number;
  longStats: SideStats;
  shortStats: SideStats;
  symbolPerformance: SymbolPerf[];
}

interface Trade {
  id: number;
  asset: string;
  side: string;
  direction?: string;
  size: number;
  entry_price: number;
  exit_price: number;
  pnl: number;
  fees: number;
  entry_time: string;
  exit_time: string;
  [key: string]: unknown;
}

function fmt(n: number, decimals = 2): string {
  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function TradingStats() {
  const [stats, setStats] = useState<StatsData | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetch("/api/trading/stats").then((r) => r.json()),
      fetch("/api/trading").then((r) => r.json()),
    ])
      .then(([statsData, tradingData]) => {
        if (statsData.success) {
          setStats(statsData);
        } else {
          setError("Failed to load stats");
        }
        setTrades(tradingData.recentTrades ?? []);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-emerald-500/30 border-t-emerald-500 rounded-full animate-spin" />
          <span
            className="text-zinc-500 text-xs tracking-[0.3em]"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            COMPUTING STATS...
          </span>
        </div>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="flex items-center justify-center py-20">
        <span
          className="text-red-400 text-sm"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          ERROR: {error ?? "No data available"}
        </span>
      </div>
    );
  }

  const wins = Math.round(
    (stats.totalTrades * stats.winRate) / 100
  );
  const losses = stats.totalTrades - wins;
  const totalFees =
    stats.totalPnl - stats.netPnl > 0
      ? stats.totalPnl - stats.netPnl
      : 0;

  return (
    <div className="space-y-6">
      {/* Row 1: 5 stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatCard
          icon="📊"
          label="Total Trades"
          value={String(stats.totalTrades)}
          subtitle={`Win:${wins} / Loss:${losses}`}
          helpText="Total closed trades across all symbols and strategies."
        />
        <StatCard
          icon="🎯"
          label="Win Rate"
          value={`${fmt(stats.winRate, 1)}%`}
          subtitle={`${wins} winners`}
          color={stats.winRate >= 50 ? "green" : "red"}
          helpText="Percentage of trades closed with positive P&L."
        />
        <StatCard
          icon="💰"
          label="Total P&L"
          value={`${stats.totalPnl >= 0 ? "+" : ""}$${fmt(stats.totalPnl)}`}
          subtitle={totalFees > 0 ? `Fee: $${fmt(totalFees)}` : undefined}
          color={stats.totalPnl >= 0 ? "green" : "red"}
          helpText="Gross profit & loss before fees."
        />
        <StatCard
          icon="⚖️"
          label="Profit Factor"
          value={fmt(stats.profitFactor)}
          subtitle="Profit / Loss"
          color={stats.profitFactor >= 1 ? "green" : "red"}
          helpText="Ratio of gross profits to gross losses. Above 1.5 is good, above 2 is excellent."
        />
        <StatCard
          icon="📈"
          label="P/L Ratio"
          value={fmt(stats.plRatio)}
          subtitle="Avg Win / Avg Loss"
          color={stats.plRatio >= 1 ? "green" : "red"}
          helpText="Average winning trade divided by average losing trade."
        />
      </div>

      {/* Row 2: 5 stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatCard
          icon="📐"
          label="Sharpe Ratio"
          value={fmt(stats.sharpeRatio)}
          subtitle="Annualized"
          color={stats.sharpeRatio >= 1 ? "green" : "red"}
          helpText="Risk-adjusted return. Above 1 is acceptable, above 2 is very good."
        />
        <StatCard
          icon="📉"
          label="Max Drawdown"
          value={`${fmt(stats.maxDrawdown, 1)}%`}
          subtitle="Peak to trough"
          color={stats.maxDrawdown <= 10 ? "green" : "red"}
          helpText="Maximum percentage decline from peak cumulative P&L."
        />
        <StatCard
          icon="✅"
          label="Avg Win"
          value={`+$${fmt(stats.avgWin)}`}
          color="green"
          helpText="Average profit on winning trades."
        />
        <StatCard
          icon="❌"
          label="Avg Loss"
          value={`-$${fmt(stats.avgLoss)}`}
          color="red"
          helpText="Average loss on losing trades."
        />
        <StatCard
          icon="💵"
          label="Net P&L"
          value={`${stats.netPnl >= 0 ? "+" : ""}$${fmt(stats.netPnl)}`}
          subtitle="After fees"
          color={stats.netPnl >= 0 ? "green" : "red"}
          helpText="Total P&L minus all trading fees and commissions."
        />
      </div>

      {/* Long / Short Breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <SideBreakdown
          title="LONG"
          icon="📈"
          stats={stats.longStats}
          accentColor="emerald"
        />
        <SideBreakdown
          title="SHORT"
          icon="📉"
          stats={stats.shortStats}
          accentColor="red"
        />
      </div>

      {/* Symbol Performance */}
      {stats.symbolPerformance.length > 0 && (
        <div className="bg-white/[0.03] border border-white/[0.06] rounded-2xl p-4 md:p-6 backdrop-blur-sm">
          <h3
            className="text-sm font-semibold text-white tracking-wider uppercase mb-4"
            style={{ fontFamily: "Outfit, sans-serif" }}
          >
            Symbol Performance
          </h3>
          <div className="space-y-2">
            {stats.symbolPerformance.map((sp) => (
              <div
                key={sp.symbol}
                className="flex items-center justify-between py-2.5 px-3 rounded-lg bg-white/[0.02] hover:bg-white/[0.04] transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span
                    className="text-xs font-semibold text-zinc-200 min-w-[80px]"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {sp.symbol}
                  </span>
                  <span
                    className="text-[10px] text-zinc-500"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {sp.trades} trades
                  </span>
                </div>
                <div className="flex items-center gap-4">
                  {/* Win rate bar */}
                  <div className="flex items-center gap-2">
                    <span
                      className="text-[10px] text-zinc-500"
                      style={{ fontFamily: "JetBrains Mono, monospace" }}
                    >
                      WR
                    </span>
                    <div className="w-16 h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          sp.winRate >= 50
                            ? "bg-emerald-500"
                            : "bg-red-500"
                        }`}
                        style={{ width: `${Math.min(sp.winRate, 100)}%` }}
                      />
                    </div>
                    <span
                      className={`text-[11px] font-medium min-w-[40px] text-right ${
                        sp.winRate >= 50
                          ? "text-emerald-400"
                          : "text-red-400"
                      }`}
                      style={{ fontFamily: "JetBrains Mono, monospace" }}
                    >
                      {fmt(sp.winRate, 1)}%
                    </span>
                  </div>
                  {/* P&L */}
                  <span
                    className={`text-[11px] font-semibold min-w-[80px] text-right ${
                      sp.pnl >= 0 ? "text-emerald-400" : "text-red-400"
                    }`}
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {sp.pnl >= 0 ? "+" : ""}${fmt(sp.pnl)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Trade History Table */}
      <TradeHistory trades={trades} />
    </div>
  );
}

/* ─── Side Breakdown Card ──────────────────────────────────── */

function SideBreakdown({
  title,
  icon,
  stats,
  accentColor,
}: {
  title: string;
  icon: string;
  stats: SideStats;
  accentColor: "emerald" | "red";
}) {
  const borderClass =
    accentColor === "emerald"
      ? "border-emerald-500/20"
      : "border-red-500/20";
  const bgClass =
    accentColor === "emerald"
      ? "bg-emerald-500/[0.03]"
      : "bg-red-500/[0.03]";
  const labelColor =
    accentColor === "emerald" ? "text-emerald-400" : "text-red-400";

  const rows = [
    { label: "Trades", value: String(stats.trades) },
    { label: "Win Rate", value: `${fmt(stats.winRate, 1)}%` },
    {
      label: "Total P&L",
      value: `${stats.totalPnl >= 0 ? "+" : ""}$${fmt(stats.totalPnl)}`,
    },
    {
      label: "Avg P&L",
      value: `${stats.avgPnl >= 0 ? "+" : ""}$${fmt(stats.avgPnl)}`,
    },
  ];

  return (
    <div
      className={`${bgClass} border ${borderClass} rounded-2xl p-4 md:p-5 backdrop-blur-sm`}
    >
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm">{icon}</span>
        <h3
          className={`text-xs font-bold tracking-widest uppercase ${labelColor}`}
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {title}
        </h3>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {rows.map((row) => (
          <div key={row.label}>
            <p
              className="text-[10px] text-zinc-600 uppercase tracking-wider mb-0.5"
              style={{ fontFamily: "Outfit, sans-serif" }}
            >
              {row.label}
            </p>
            <p
              className="text-sm font-semibold text-zinc-200"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              {row.value}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
