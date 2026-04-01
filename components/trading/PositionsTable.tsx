"use client";

import { useHyperliquidWithWallet } from "@/hooks/useHyperliquidWithWallet";
import { useQuery } from "@tanstack/react-query";
import { useViewMode } from "@/stores/viewMode";

interface DisplayPosition {
  symbol: string;
  side: "LONG" | "SHORT";
  entryPx: number;
  markPx: number;
  qty: number;
  value: number;
  leverage: number;
  upnl: number;
  upnlPct: number;
  liqPrice: number | null;
  source: "live" | "demo";
}

function fmt(n: number, decimals = 2): string {
  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function PositionsTable() {
  const { mode } = useViewMode();
  const hl = useHyperliquidWithWallet();

  const { data: fallbackData } = useQuery({
    queryKey: ["live-positions"],
    queryFn: () => fetch("/api/trading").then((r) => r.json()),
    refetchInterval: 5_000,
    enabled: mode === "demo" || !hl.data,
  });

  const hlData = hl.data;
  const hlAvailable = !!hlData && hlData.connected;
  const showLive = mode === "live" && hlAvailable;

  // Map HL positions
  const hlPositions: DisplayPosition[] = (hlData?.positions ?? []).map((p) => {
    const value = Math.abs(p.size) * p.entryPx;
    const upnlPct = value > 0 ? (p.unrealizedPnl / value) * 100 : 0;
    return {
      symbol: p.coin,
      side: p.size > 0 ? "LONG" : "SHORT",
      entryPx: p.entryPx,
      markPx: p.entryPx, // HL clearinghouse doesn't return mark; entryPx as fallback
      qty: Math.abs(p.size),
      value,
      leverage: p.leverage,
      upnl: p.unrealizedPnl,
      upnlPct,
      liqPrice: null,
      source: "live",
    };
  });

  // Map demo positions
  const demoPositions: DisplayPosition[] = (fallbackData?.openPositions ?? []).map(
    (p: Record<string, unknown>) => {
      const size = (p.size as number) ?? 0;
      const entry = (p.entry_price as number) ?? 0;
      const fillPx = (p.fill_price as number) ?? entry;
      const pnl = (p.pnl as number) ?? 0;
      const value = size * entry;
      return {
        symbol: (p.asset as string) ?? "",
        side: ((p.side as string) ?? "").toUpperCase() as "LONG" | "SHORT",
        entryPx: entry,
        markPx: fillPx,
        qty: size,
        value,
        leverage: 1,
        upnl: pnl,
        upnlPct: value > 0 ? (pnl / value) * 100 : 0,
        liqPrice: null,
        source: "demo" as const,
      };
    },
  );

  const positions = showLive ? hlPositions : demoPositions;
  const isDemo = !showLive;
  const activeCount = positions.length;

  return (
    <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/5">
        <div className="flex items-center gap-3">
          <h3
            className="text-sm font-semibold text-zinc-300"
            style={{ fontFamily: "Outfit, sans-serif" }}
          >
            Current Positions
          </h3>
          <span
            className={`text-[10px] font-bold px-2 py-0.5 rounded-lg ${
              activeCount > 0
                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                : "bg-zinc-500/20 text-zinc-500 border border-zinc-500/30"
            }`}
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            {activeCount} Active
          </span>
          {isDemo && (
            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 border border-amber-500/30">
              DEMO
            </span>
          )}
        </div>
      </div>

      {/* Table */}
      {positions.length === 0 ? (
        <div className="px-5 py-8 text-center">
          <p className="text-zinc-600 text-sm">No open positions</p>
          <p className="text-zinc-700 text-xs mt-1">
            Positions will appear here when trades are executed
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] text-zinc-600 uppercase tracking-wider">
                <th className="text-left px-5 py-2">Symbol</th>
                <th className="text-left px-3 py-2">Side</th>
                <th className="text-right px-3 py-2">Entry</th>
                <th className="text-right px-3 py-2">Mark</th>
                <th className="text-right px-3 py-2">Qty</th>
                <th className="text-right px-3 py-2">Value</th>
                <th className="text-right px-3 py-2">Lev.</th>
                <th className="text-right px-3 py-2">UPNL</th>
                <th className="text-right px-3 py-2">Liq. Price</th>
                <th className="text-right px-5 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((pos) => (
                <tr
                  key={`${pos.symbol}-${pos.side}`}
                  className="border-t border-white/[0.04] hover:bg-white/[0.02] transition-colors"
                >
                  <td
                    className="px-5 py-3 font-bold text-white"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {pos.symbol}
                  </td>
                  <td className="px-3 py-3">
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                        pos.side === "LONG"
                          ? "bg-emerald-500/20 text-emerald-400"
                          : "bg-red-500/20 text-red-400"
                      }`}
                    >
                      {pos.side}
                    </span>
                  </td>
                  <td
                    className="px-3 py-3 text-right text-zinc-300"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    ${fmt(pos.entryPx)}
                  </td>
                  <td
                    className="px-3 py-3 text-right text-zinc-400"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    ${fmt(pos.markPx)}
                  </td>
                  <td
                    className="px-3 py-3 text-right text-zinc-300"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {fmt(pos.qty, 4)}
                  </td>
                  <td
                    className="px-3 py-3 text-right text-zinc-300"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    ${fmt(pos.value)}
                  </td>
                  <td
                    className="px-3 py-3 text-right text-zinc-400"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {pos.leverage}x
                  </td>
                  <td className="px-3 py-3 text-right">
                    <span
                      className={`font-bold ${pos.upnl >= 0 ? "text-emerald-400" : "text-red-400"}`}
                      style={{ fontFamily: "JetBrains Mono, monospace" }}
                    >
                      {pos.upnl >= 0 ? "+" : ""}${fmt(pos.upnl)}
                    </span>
                    <span
                      className={`ml-1 text-[10px] ${pos.upnl >= 0 ? "text-emerald-500/60" : "text-red-500/60"}`}
                    >
                      ({pos.upnlPct >= 0 ? "+" : ""}{fmt(pos.upnlPct, 1)}%)
                    </span>
                  </td>
                  <td
                    className="px-3 py-3 text-right text-zinc-500"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {pos.liqPrice != null ? `$${fmt(pos.liqPrice)}` : "--"}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <button
                      disabled
                      title="Coming soon"
                      className="text-[10px] px-2 py-1 rounded bg-white/5 text-zinc-600 border border-white/5 cursor-not-allowed"
                    >
                      Close
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
