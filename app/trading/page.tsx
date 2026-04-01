import { ErrorBoundary } from "@/components/ErrorBoundary";
import { AccountSummaryBar } from "@/components/AccountSummaryBar";
import { KillSwitchButton } from "@/components/KillSwitchButton";
import { SystemHealthDot } from "@/components/SystemHealthDot";
import { LivePositionsPanel } from "@/components/LivePositionsPanel";
import { TradeFeed } from "@/components/TradeFeed";
import { TradingDashboardLoader } from "@/components/trading/TradingDashboardLoader";

export default function TradingPage() {
  return (
    <ErrorBoundary>
      <div className="min-h-screen">
        <div className="flex items-center justify-between px-4 py-2 border-b border-white/10">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-bold text-white">AIFred Trading</h1>
            <SystemHealthDot />
          </div>
          <KillSwitchButton />
        </div>
        <AccountSummaryBar />
        <div className="p-4 space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <LivePositionsPanel />
            <TradeFeed />
          </div>
          <TradingDashboardLoader />
        </div>
      </div>
    </ErrorBoundary>
  );
}
