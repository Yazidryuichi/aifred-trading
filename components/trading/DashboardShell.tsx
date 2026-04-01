"use client";

import { HeroMetrics } from "@/components/trading/HeroMetrics";
import { ChartSection } from "@/components/trading/ChartSection";
import { PositionsTable } from "@/components/trading/PositionsTable";
import { LiveStatusPanel } from "@/components/trading/LiveStatusPanel";
import { RecentDecisions } from "@/components/trading/RecentDecisions";
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
          <ChartSection />
        </div>
        <div className="lg:col-span-2">
          <RecentDecisions />
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
