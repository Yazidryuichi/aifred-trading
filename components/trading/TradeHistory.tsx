"use client";

import { useState, useMemo } from "react";
import { ChevronDown } from "lucide-react";

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

type SortOption = "latest" | "oldest" | "highest_pnl" | "lowest_pnl";

function formatDuration(entryTime: string, exitTime: string): string {
  const ms =
    new Date(exitTime).getTime() - new Date(entryTime).getTime();
  if (isNaN(ms) || ms <= 0) return "-";
  const totalMinutes = Math.floor(ms / 60000);
  if (totalMinutes < 60) return `${totalMinutes}m`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours < 24) return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
  const days = Math.floor(hours / 24);
  const remHours = hours % 24;
  return remHours > 0 ? `${days}d ${remHours}h` : `${days}d`;
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return "-";
  }
}

export function TradeHistory({ trades }: { trades: Trade[] }) {
  const [symbolFilter, setSymbolFilter] = useState<string>("ALL");
  const [sideFilter, setSideFilter] = useState<string>("ALL");
  const [sortBy, setSortBy] = useState<SortOption>("latest");

  const symbols = useMemo(() => {
    const set = new Set(trades.map((t) => t.asset));
    return Array.from(set).sort();
  }, [trades]);

  const filtered = useMemo(() => {
    let result = [...trades];

    if (symbolFilter !== "ALL") {
      result = result.filter((t) => t.asset === symbolFilter);
    }
    if (sideFilter !== "ALL") {
      result = result.filter(
        (t) =>
          (t.side ?? t.direction ?? "").toUpperCase() ===
          sideFilter.toUpperCase()
      );
    }

    switch (sortBy) {
      case "latest":
        result.sort(
          (a, b) =>
            new Date(b.exit_time).getTime() -
            new Date(a.exit_time).getTime()
        );
        break;
      case "oldest":
        result.sort(
          (a, b) =>
            new Date(a.exit_time).getTime() -
            new Date(b.exit_time).getTime()
        );
        break;
      case "highest_pnl":
        result.sort((a, b) => b.pnl - a.pnl);
        break;
      case "lowest_pnl":
        result.sort((a, b) => a.pnl - b.pnl);
        break;
    }

    return result;
  }, [trades, symbolFilter, sideFilter, sortBy]);

  const selectClass =
    "appearance-none bg-white/[0.04] border border-white/10 rounded-lg px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-emerald-500/40 cursor-pointer pr-7";

  return (
    <div className="bg-white/[0.03] border border-white/[0.06] rounded-2xl p-4 md:p-6 backdrop-blur-sm">
      {/* Header + Filters */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-4">
        <h3
          className="text-sm font-semibold text-white tracking-wider uppercase"
          style={{ fontFamily: "Outfit, sans-serif" }}
        >
          Trade History
        </h3>

        <div className="flex flex-wrap items-center gap-2">
          {/* Symbol filter */}
          <div className="relative">
            <select
              value={symbolFilter}
              onChange={(e) => setSymbolFilter(e.target.value)}
              className={selectClass}
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              <option value="ALL">All Symbols</option>
              {symbols.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-zinc-500 pointer-events-none" />
          </div>

          {/* Side toggle */}
          <div
            className="flex bg-white/[0.04] border border-white/10 rounded-lg p-0.5"
            role="group"
            aria-label="Filter by side"
          >
            {["ALL", "LONG", "SHORT"].map((side) => (
              <button
                key={side}
                onClick={() => setSideFilter(side)}
                className={`px-3 py-1 text-[10px] font-semibold rounded-md transition-all tracking-wider ${
                  sideFilter === side
                    ? side === "LONG"
                      ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                      : side === "SHORT"
                        ? "bg-red-500/20 text-red-400 border border-red-500/30"
                        : "bg-white/[0.08] text-white border border-white/10"
                    : "text-zinc-500 hover:text-zinc-300 border border-transparent"
                }`}
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {side}
              </button>
            ))}
          </div>

          {/* Sort */}
          <div className="relative">
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortOption)}
              className={selectClass}
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              <option value="latest">Latest First</option>
              <option value="oldest">Oldest First</option>
              <option value="highest_pnl">Highest P&L</option>
              <option value="lowest_pnl">Lowest P&L</option>
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-zinc-500 pointer-events-none" />
          </div>
        </div>
      </div>

      {/* Table header */}
      <div
        className="hidden md:grid grid-cols-[1fr_60px_80px_80px_60px_80px_56px_60px_90px] gap-2 px-3 py-2 text-[10px] text-zinc-600 uppercase tracking-wider border-b border-white/[0.06]"
        style={{ fontFamily: "JetBrains Mono, monospace" }}
      >
        <span>Symbol</span>
        <span>Side</span>
        <span className="text-right">Entry</span>
        <span className="text-right">Exit</span>
        <span className="text-right">Qty</span>
        <span className="text-right">P&L</span>
        <span className="text-right">Fee</span>
        <span className="text-right">Dur.</span>
        <span className="text-right">Closed</span>
      </div>

      {/* Rows */}
      <div className="max-h-[400px] overflow-y-auto custom-scrollbar">
        {filtered.length === 0 && (
          <div className="py-8 text-center text-zinc-600 text-xs">
            No trades match the current filters.
          </div>
        )}
        {filtered.map((trade) => {
          const pnl = trade.pnl ?? 0;
          const isWin = pnl > 0;
          const entryPrice = trade.entry_price ?? 0;
          const pnlPct =
            entryPrice > 0 && trade.size > 0
              ? (pnl / (entryPrice * trade.size)) * 100
              : 0;
          const side = (
            trade.side ??
            trade.direction ??
            ""
          ).toUpperCase();

          return (
            <div
              key={trade.id}
              className="grid grid-cols-2 md:grid-cols-[1fr_60px_80px_80px_60px_80px_56px_60px_90px] gap-2 px-3 py-2.5 border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors items-center"
            >
              {/* Symbol + side badge (mobile) */}
              <div className="flex items-center gap-2">
                <span
                  className="text-xs font-medium text-zinc-200"
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  {trade.asset}
                </span>
                <span
                  className={`md:hidden text-[9px] font-bold px-1.5 py-0.5 rounded ${
                    side === "LONG"
                      ? "bg-emerald-500/15 text-emerald-400"
                      : "bg-red-500/15 text-red-400"
                  }`}
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  {side}
                </span>
              </div>

              {/* Side (desktop) */}
              <span
                className={`hidden md:block text-[10px] font-bold ${
                  side === "LONG" ? "text-emerald-400" : "text-red-400"
                }`}
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {side}
              </span>

              {/* Entry */}
              <span
                className="hidden md:block text-[11px] text-zinc-400 text-right"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                ${entryPrice.toFixed(2)}
              </span>

              {/* Exit */}
              <span
                className="hidden md:block text-[11px] text-zinc-400 text-right"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                ${(trade.exit_price ?? 0).toFixed(2)}
              </span>

              {/* Qty */}
              <span
                className="hidden md:block text-[11px] text-zinc-400 text-right"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {trade.size?.toFixed(2)}
              </span>

              {/* P&L */}
              <div className="text-right">
                <span
                  className={`text-[11px] font-semibold ${
                    isWin ? "text-emerald-400" : "text-red-400"
                  }`}
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  {isWin ? "+" : ""}${pnl.toFixed(2)}
                </span>
                <span
                  className={`block md:inline md:ml-1 text-[9px] ${
                    isWin ? "text-emerald-500/60" : "text-red-500/60"
                  }`}
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  {pnlPct >= 0 ? "+" : ""}
                  {pnlPct.toFixed(1)}%
                </span>
              </div>

              {/* Fee */}
              <span
                className="hidden md:block text-[11px] text-zinc-500 text-right"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                ${(trade.fees ?? 0).toFixed(2)}
              </span>

              {/* Duration */}
              <span
                className="hidden md:block text-[11px] text-zinc-500 text-right"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {formatDuration(trade.entry_time, trade.exit_time)}
              </span>

              {/* Closed At */}
              <span
                className="hidden md:block text-[10px] text-zinc-600 text-right"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {formatDate(trade.exit_time)}
              </span>
            </div>
          );
        })}
      </div>

      {/* Summary row */}
      {filtered.length > 0 && (
        <div
          className="flex items-center justify-between px-3 pt-3 mt-2 border-t border-white/[0.06] text-[10px] text-zinc-500"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          <span>
            Showing {filtered.length} of {trades.length} trades
          </span>
          <span>
            Filtered P&L:{" "}
            <span
              className={
                filtered.reduce((s, t) => s + t.pnl, 0) >= 0
                  ? "text-emerald-400"
                  : "text-red-400"
              }
            >
              {filtered.reduce((s, t) => s + t.pnl, 0) >= 0 ? "+" : ""}$
              {filtered
                .reduce((s, t) => s + t.pnl, 0)
                .toFixed(2)}
            </span>
          </span>
        </div>
      )}
    </div>
  );
}
