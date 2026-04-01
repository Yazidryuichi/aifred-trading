"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import { Trophy, Swords, TrendingUp } from "lucide-react";
import { getArenaData } from "@/lib/arena-data";
import { PerformanceChart } from "@/components/trading/arena/PerformanceChart";
import { Leaderboard } from "@/components/trading/arena/Leaderboard";
import { HeadToHead } from "@/components/trading/arena/HeadToHead";

export default function ArenaPanel() {
  const { strategies, performanceData } = useMemo(() => getArenaData(), []);

  return (
    <div
      className="min-h-screen bg-[#06060a] text-white relative overflow-hidden"
      style={{ fontFamily: "Outfit, sans-serif" }}
    >
      {/* Ambient glow */}
      <div className="fixed inset-0 pointer-events-none">
        <div
          className="absolute top-0 left-1/3 w-[700px] h-[700px] rounded-full opacity-[0.035]"
          style={{
            background:
              "radial-gradient(circle, rgba(16,185,129,1) 0%, transparent 70%)",
          }}
        />
        <div
          className="absolute bottom-0 right-1/4 w-[500px] h-[500px] rounded-full opacity-[0.025]"
          style={{
            background:
              "radial-gradient(circle, rgba(99,102,241,1) 0%, transparent 70%)",
          }}
        />
        <div
          className="absolute top-1/2 right-0 w-[400px] h-[400px] rounded-full opacity-[0.02]"
          style={{
            background:
              "radial-gradient(circle, rgba(168,85,247,1) 0%, transparent 70%)",
          }}
        />
      </div>

      <div className="relative z-10 max-w-[1600px] mx-auto px-4 md:px-6 py-6 pb-24">
        {/* Page header */}
        <motion.div initial={false} animate={{ opacity: 1 }} className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center shadow-lg shadow-amber-500/20">
              <Trophy className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl md:text-2xl font-bold tracking-tight">
                AI Trading Competition
              </h1>
              <p
                className="text-xs text-zinc-500 tracking-wider"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                Multi-AI Strategy Battle &bull; Real-time
              </p>
            </div>
          </div>
        </motion.div>

        {/* Main grid: Chart + Leaderboard */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 mb-6">
          {/* Performance Chart — 3 cols */}
          <motion.div
            initial={false}
            animate={{ opacity: 1 }}
            className="lg:col-span-3 rounded-2xl border border-white/[0.06] p-5"
            style={{
              background:
                "linear-gradient(135deg, rgba(255,255,255,0.02) 0%, rgba(16,185,129,0.02) 100%)",
              backdropFilter: "blur(12px)",
            }}
          >
            <div className="flex items-center gap-2 mb-4">
              <TrendingUp className="w-4 h-4 text-emerald-400" />
              <h2
                className="text-sm font-semibold text-zinc-300"
                style={{ fontFamily: "Outfit, sans-serif" }}
              >
                Performance Comparison
              </h2>
              <span
                className="text-[10px] text-zinc-600 ml-1"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                Real-time PnL %
              </span>
            </div>
            <div className="h-[340px]">
              <PerformanceChart
                data={performanceData}
                strategies={strategies}
              />
            </div>
          </motion.div>

          {/* Leaderboard — 2 cols */}
          <motion.div
            initial={false}
            animate={{ opacity: 1 }}
            className="lg:col-span-2 rounded-2xl border border-white/[0.06] p-5"
            style={{
              background:
                "linear-gradient(135deg, rgba(255,255,255,0.02) 0%, rgba(99,102,241,0.02) 100%)",
              backdropFilter: "blur(12px)",
            }}
          >
            <Leaderboard strategies={strategies} />
          </motion.div>
        </div>

        {/* Head-to-Head */}
        <motion.div
          initial={false}
          animate={{ opacity: 1 }}
          className="rounded-2xl border border-white/[0.06] p-5"
          style={{
            background:
              "linear-gradient(135deg, rgba(255,255,255,0.02) 0%, rgba(168,85,247,0.02) 100%)",
            backdropFilter: "blur(12px)",
          }}
        >
          <div className="flex items-center gap-2 mb-1">
            <Swords className="w-4 h-4 text-purple-400" />
          </div>
          <HeadToHead strategies={strategies} />
        </motion.div>
      </div>
    </div>
  );
}
