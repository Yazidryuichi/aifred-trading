import { ErrorBoundary } from "@/components/ErrorBoundary";
import { KillSwitchButton } from "@/components/KillSwitchButton";
import { SystemHealthDot } from "@/components/SystemHealthDot";
import { TradingDashboardLoader } from "@/components/trading/TradingDashboardLoader";
import { DashboardShell } from "@/components/trading/DashboardShell";

export default function TradingPage() {
  return (
    <ErrorBoundary>
      <div className="min-h-screen">
        {/* Top bar: branding + kill switch */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-white/10">
          <div className="flex items-center gap-3">
            <h1
              className="text-lg font-bold text-white"
              style={{ fontFamily: "Outfit, sans-serif" }}
            >
              AIFred Trading
            </h1>
            <span className="text-[10px] text-zinc-500 border border-zinc-700 rounded px-1.5 py-0.5 font-mono">
              powered by{" "}
              <span className="text-emerald-400">Hyperliquid</span>
            </span>
            <SystemHealthDot />
          </div>
          <KillSwitchButton />
        </div>

        {/* Dashboard body (client component) */}
        <DashboardShell />

        {/* Existing tabbed dashboard (Overview, Regime, Trades, Activity, Agents) */}
        <div className="px-4 pb-4">
          <TradingDashboardLoader />
        </div>
      </div>
    </ErrorBoundary>
  );
}
