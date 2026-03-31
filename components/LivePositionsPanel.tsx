"use client";

import { useQuery } from "@tanstack/react-query";

interface Position {
  asset: string;
  side: string;
  entryPrice: number;
  currentPrice: number;
  size: number;
  unrealizedPnl: number;
  stopLoss: number;
  openedAt: string;
}

export function LivePositionsPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["live-positions"],
    queryFn: () => fetch("/api/trading/activity?type=positions").then((r) => r.json()),
    refetchInterval: 5_000,
  });

  const positions: Position[] = data?.positions ?? [];

  if (isLoading) {
    return (
      <div className="p-4 rounded-xl border border-white/10 bg-white/5">
        <h3 className="text-lg font-bold text-white mb-3">Open Positions</h3>
        <p className="text-gray-400 text-sm">Loading...</p>
      </div>
    );
  }

  return (
    <div className="p-4 rounded-xl border border-white/10 bg-white/5">
      <h3 className="text-lg font-bold text-white mb-3">Open Positions</h3>
      {positions.length === 0 ? (
        <p className="text-gray-500 text-sm">No open positions</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 text-left">
                <th className="pb-2">Asset</th>
                <th className="pb-2">Side</th>
                <th className="pb-2">Entry</th>
                <th className="pb-2">Current</th>
                <th className="pb-2">P&L</th>
                <th className="pb-2">Stop</th>
                <th className="pb-2">Time</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((pos) => {
                const held = timeSince(pos.openedAt);
                return (
                  <tr key={pos.asset} className="border-t border-white/5">
                    <td className="py-2 font-mono text-white">{pos.asset}</td>
                    <td className={pos.side === "long" ? "text-green-400" : "text-red-400"}>
                      {pos.side.toUpperCase()}
                    </td>
                    <td className="font-mono text-gray-300">${pos.entryPrice.toLocaleString()}</td>
                    <td className="font-mono text-white">${pos.currentPrice.toLocaleString()}</td>
                    <td className={`font-mono font-bold ${pos.unrealizedPnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {pos.unrealizedPnl >= 0 ? "+" : ""}${pos.unrealizedPnl.toFixed(2)}
                    </td>
                    <td className="font-mono text-red-400">${pos.stopLoss.toLocaleString()}</td>
                    <td className="text-gray-400">{held}</td>
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
