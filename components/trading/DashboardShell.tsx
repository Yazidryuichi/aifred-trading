"use client";

import { HeroMetrics } from "@/components/trading/HeroMetrics";
import { EquityCurve } from "@/components/trading/EquityCurve";
import { PositionsTable } from "@/components/trading/PositionsTable";
import { LiveStatusPanel } from "@/components/trading/LiveStatusPanel";
import { useViewMode } from "@/stores/viewMode";

export function DashboardShell() {
  const { mode, setMode } = useViewMode();

  return (
    <div className="p-4 space-y-4">
      {/* Hero Metrics */}
      <HeroMetrics />

      {/* Two-column: Equity Curve + Recent Decisions placeholder */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-3">
          <EquityCurve />
        </div>
        <div className="lg:col-span-2">
          <div className="bg-white/5 border border-white/10 rounded-xl p-5 h-full flex flex-col">
            <h3
              className="text-sm font-semibold text-zinc-300 mb-3"
              style={{ fontFamily: "Outfit, sans-serif" }}
            >
              Recent Decisions
            </h3>
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <p className="text-zinc-600 text-sm">AI Decision History</p>
                <p className="text-zinc-700 text-xs mt-1">Coming in Sprint 2</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Positions Table */}
      <PositionsTable />

      {/* Live System Status + Mode Toggle */}
      <div className="flex items-center gap-4 pb-2">
        {/* LIVE / DEMO toggle */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => setMode("live")}
            className={`px-3 py-1 rounded-lg text-[10px] font-bold tracking-wider transition-all ${
              mode === "live"
                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                : "text-zinc-500 hover:text-zinc-300 border border-transparent"
            }`}
          >
            LIVE
          </button>
          <button
            onClick={() => setMode("demo")}
            className={`px-3 py-1 rounded-lg text-[10px] font-bold tracking-wider transition-all ${
              mode === "demo"
                ? "bg-amber-500/20 text-amber-400 border border-amber-500/40"
                : "text-zinc-500 hover:text-zinc-300 border border-transparent"
            }`}
          >
            DEMO
          </button>
        </div>
      </div>

      {/* Live System Status */}
      <LiveStatusPanel />
    </div>
  );
}
