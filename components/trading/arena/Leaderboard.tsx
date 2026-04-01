"use client";

import { motion } from "framer-motion";
import type { StrategyInfo } from "@/lib/arena-data";

const RANK_STYLES: Record<number, { border: string; bg: string; badge: string }> = {
  1: {
    border: "border-yellow-500/30",
    bg: "bg-yellow-500/[0.04]",
    badge: "bg-yellow-500/20 text-yellow-400",
  },
  2: {
    border: "border-zinc-400/20",
    bg: "bg-zinc-400/[0.03]",
    badge: "bg-zinc-400/15 text-zinc-300",
  },
  3: {
    border: "border-amber-700/25",
    bg: "bg-amber-700/[0.04]",
    badge: "bg-amber-700/20 text-amber-600",
  },
};

interface Props {
  strategies: StrategyInfo[];
}

export function Leaderboard({ strategies }: Props) {
  const sorted = [...strategies].sort((a, b) => b.pnlPercent - a.pnlPercent);

  return (
    <div className="flex flex-col h-full">
      {/* Header with LIVE badge */}
      <div className="flex items-center justify-between mb-4">
        <h3
          className="text-sm font-semibold text-zinc-300"
          style={{ fontFamily: "Outfit, sans-serif" }}
        >
          Leaderboard
        </h3>
        <div className="flex items-center gap-1.5">
          <div
            className="w-1.5 h-1.5 rounded-full bg-red-500"
            style={{ animation: "pulse-glow 1.5s ease-in-out infinite" }}
          />
          <span
            className="text-[9px] px-2 py-0.5 rounded-full bg-red-500/15 text-red-400 border border-red-500/25 font-bold tracking-widest"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            LIVE
          </span>
        </div>
      </div>

      {/* Entries */}
      <div className="flex flex-col gap-3 flex-1">
        {sorted.map((strategy, idx) => {
          const rank = idx + 1;
          const style = RANK_STYLES[rank] || {
            border: "border-white/[0.06]",
            bg: "bg-white/[0.02]",
            badge: "bg-white/10 text-zinc-400",
          };

          return (
            <motion.div
              key={strategy.id}
              initial={false}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.1 }}
              className={`rounded-xl border ${style.border} ${style.bg} p-3.5`}
              style={{ backdropFilter: "blur(8px)" }}
            >
              <div className="flex items-start gap-3">
                {/* Rank badge */}
                <div
                  className={`w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold ${style.badge}`}
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  #{rank}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm">{strategy.emoji}</span>
                    <span
                      className="text-sm font-semibold text-white truncate"
                      style={{ fontFamily: "Outfit, sans-serif" }}
                    >
                      {strategy.name}
                    </span>
                    {/* Status dot */}
                    <div
                      className={`w-2 h-2 rounded-full flex-shrink-0 ${
                        strategy.status === "active"
                          ? "bg-emerald-400"
                          : "bg-amber-400"
                      }`}
                      style={
                        strategy.status === "active"
                          ? { animation: "pulse-glow 2s ease-in-out infinite" }
                          : undefined
                      }
                    />
                  </div>
                  <div
                    className="text-[10px] text-zinc-500 mb-2"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {strategy.model}
                  </div>

                  {/* Stats row */}
                  <div className="grid grid-cols-3 gap-2">
                    <div>
                      <div
                        className="text-[9px] text-zinc-600 tracking-wider"
                        style={{ fontFamily: "JetBrains Mono, monospace" }}
                      >
                        EQUITY
                      </div>
                      <div
                        className="text-xs text-zinc-200 font-medium"
                        style={{ fontFamily: "JetBrains Mono, monospace" }}
                      >
                        ${strategy.equity.toLocaleString()}
                      </div>
                    </div>
                    <div>
                      <div
                        className="text-[9px] text-zinc-600 tracking-wider"
                        style={{ fontFamily: "JetBrains Mono, monospace" }}
                      >
                        P&L
                      </div>
                      <div
                        className={`text-xs font-bold ${
                          strategy.pnlPercent >= 0
                            ? "text-emerald-400"
                            : "text-red-400"
                        }`}
                        style={{ fontFamily: "JetBrains Mono, monospace" }}
                      >
                        {strategy.pnlPercent >= 0 ? "+" : ""}
                        {strategy.pnlPercent}%
                      </div>
                    </div>
                    <div>
                      <div
                        className="text-[9px] text-zinc-600 tracking-wider"
                        style={{ fontFamily: "JetBrains Mono, monospace" }}
                      >
                        POSITIONS
                      </div>
                      <div
                        className="text-xs text-zinc-200 font-medium"
                        style={{ fontFamily: "JetBrains Mono, monospace" }}
                      >
                        {strategy.positions}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
