"use client";

import { useQuery } from "@tanstack/react-query";
import { useHyperliquidWithWallet } from "@/hooks/useHyperliquidWithWallet";

interface Position {
  asset: string;
  side: string;
  entryPrice: number;
  currentPrice: number;
  size: number;
  unrealizedPnl: number;
  stopLoss: number;
  openedAt: string;
  source: "live" | "demo";
}

export function LivePositionsPanel() {
  const hl = useHyperliquidWithWallet();

  // Fallback: internal API (reads from trading-data.json)
  const { data: fallbackData, isLoading: fallbackLoading } = useQuery({
    queryKey: ["live-positions"],
    queryFn: () => fetch("/api/trading").then((r) => r.json()),
    refetchInterval: 5_000,
    // Only fetch fallback when Hyperliquid is NOT available
    enabled: !hl.data,
  });

  const useHL = !!hl.data;
  const isLoading = useHL ? hl.isLoading : fallbackLoading;

  // Map Hyperliquid positions to the component interface
  const hlPositions: Position[] = (hl.data?.positions ?? []).map((p) => ({
    asset: p.coin,
    side: p.size > 0 ? "long" : "short",
    entryPrice: p.entryPx,
    currentPrice: p.entryPx, // Hyperliquid clearinghouseState doesn't include mark price
    size: Math.abs(p.size),
    unrealizedPnl: p.unrealizedPnl,
    stopLoss: 0,
    openedAt: "",
    source: "live" as const,
  }));

  const fallbackPositions: Position[] = (fallbackData?.openPositions ?? []).map(
    (p: Record<string, unknown>) => ({
      asset: (p.asset as string) ?? "",
      side: ((p.side as string) ?? "").toLowerCase(),
      entryPrice: (p.entry_price as number) ?? 0,
      currentPrice: (p.fill_price as number) ?? (p.entry_price as number) ?? 0,
      size: (p.size as number) ?? 0,
      unrealizedPnl: (p.pnl as number) ?? 0,
      stopLoss: (p.stop_loss as number) ?? 0,
      openedAt: (p.entry_time as string) ?? "",
      source: "demo" as const,
    }),
  );

  const positions = useHL ? hlPositions : fallbackPositions;

  if (isLoading && positions.length === 0) {
    return (
      <div className="p-4 rounded-xl border border-white/10 bg-white/5">
        <h3 className="text-lg font-bold text-white mb-3">Open Positions</h3>
        <p className="text-gray-400 text-sm">Loading...</p>
      </div>
    );
  }

  return (
    <div className="p-4 rounded-xl border border-white/10 bg-white/5">
      <div className="flex items-center gap-2 mb-3">
        <h3 className="text-lg font-bold text-white">Open Positions</h3>
        <span
          className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
            useHL
              ? "bg-emerald-500/20 text-emerald-400"
              : "bg-yellow-500/20 text-yellow-400"
          }`}
        >
          {useHL ? "LIVE" : "DEMO"}
        </span>
      </div>
      {positions.length === 0 ? (
        <p className="text-gray-500 text-sm">No open positions</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 text-left">
                <th className="pb-2">Asset</th>
                <th className="pb-2">Side</th>
                <th className="pb-2">Size</th>
                <th className="pb-2">Entry</th>
                <th className="pb-2">P&L</th>
                {!useHL && <th className="pb-2">Stop</th>}
                {!useHL && <th className="pb-2">Time</th>}
              </tr>
            </thead>
            <tbody>
              {positions.map((pos) => {
                const held = pos.openedAt ? timeSince(pos.openedAt) : "";
                return (
                  <tr key={pos.asset} className="border-t border-white/5">
                    <td className="py-2 font-mono text-white">{pos.asset}</td>
                    <td className={pos.side === "long" ? "text-green-400" : "text-red-400"}>
                      {pos.side.toUpperCase()}
                    </td>
                    <td className="font-mono text-gray-300">{pos.size.toFixed(4)}</td>
                    <td className="font-mono text-gray-300">${pos.entryPrice.toLocaleString()}</td>
                    <td className={`font-mono font-bold ${pos.unrealizedPnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {pos.unrealizedPnl >= 0 ? "+" : ""}${pos.unrealizedPnl.toFixed(2)}
                    </td>
                    {!useHL && (
                      <td className="font-mono text-red-400">${pos.stopLoss.toLocaleString()}</td>
                    )}
                    {!useHL && (
                      <td className="text-gray-400">{held}</td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function timeSince(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ${minutes % 60}m`;
  return `${Math.floor(hours / 24)}d ${hours % 24}h`;
}
