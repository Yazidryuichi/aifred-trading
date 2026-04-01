"use client";

import { useQuery } from "@tanstack/react-query";

interface Trade {
  id: string;
  asset: string;
  side: string;
  entryPrice: number;
  exitPrice?: number;
  pnl?: number;
  signalTier: string;
  status: string;
  timestamp: string;
}

export function TradeFeed() {
  const { data } = useQuery({
    queryKey: ["trade-feed"],
    queryFn: () => fetch("/api/trading").then((r) => r.json()),
    refetchInterval: 5_000,
  });

  const trades: Trade[] = ((data?.recentTrades as Record<string, unknown>[]) ?? [])
    .slice(0, 20)
    .map((t) => ({
      id: String(t.id ?? ""),
      asset: (t.asset as string) ?? "",
      side: (t.side as string) ?? "",
      entryPrice: (t.entry_price as number) ?? 0,
      exitPrice: (t.exit_price as number) ?? undefined,
      pnl: (t.pnl as number) ?? undefined,
      signalTier: (t.tier as string) ?? "",
      status: t.exit_price ? "closed" : "filled",
      timestamp: (t.entry_time as string) ?? "",
    }));

  return (
    <div className="p-4 rounded-xl border border-white/10 bg-white/5">
      <div className="flex items-center gap-2 mb-3">
        <h3 className="text-lg font-bold text-white">Recent Trades</h3>
        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-yellow-500/20 text-yellow-400">
          DEMO
        </span>
      </div>
      {trades.length === 0 ? (
        <p className="text-gray-500 text-sm">No recent trades</p>
      ) : (
        <div className="space-y-2 max-h-80 overflow-y-auto">
          {trades.map((trade) => (
            <div
              key={trade.id}
              className="flex items-center justify-between px-3 py-2 rounded-lg bg-white/5 text-sm"
            >
              <div className="flex items-center gap-3">
                <span className="font-mono text-white">{trade.asset}</span>
                <span className={trade.side === "LONG" ? "text-green-400" : "text-red-400"}>
                  {trade.side}
                </span>
                <span className="text-xs px-1.5 py-0.5 rounded bg-white/10 text-gray-400">
                  {trade.signalTier}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <StatusBadge status={trade.status} />
                {trade.pnl !== undefined && (
                  <span className={`font-mono font-bold ${trade.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {trade.pnl >= 0 ? "+" : ""}${trade.pnl.toFixed(2)}
                  </span>
                )}
                <span className="text-gray-500 text-xs">
                  {new Date(trade.timestamp).toLocaleTimeString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    filled: "bg-green-500/20 text-green-400",
    "stopped-out": "bg-red-500/20 text-red-400",
    "take-profit": "bg-blue-500/20 text-blue-400",
    closed: "bg-gray-500/20 text-gray-400",
  };

  return (
    <span className={`text-xs px-1.5 py-0.5 rounded ${colors[status] ?? colors.closed}`}>
      {status}
    </span>
  );
}
