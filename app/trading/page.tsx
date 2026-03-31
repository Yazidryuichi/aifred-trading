"use client";

import dynamic from "next/dynamic";
import { Component, type ReactNode } from "react";
import { AccountSummaryBar } from "@/components/AccountSummaryBar";
import { KillSwitchButton } from "@/components/KillSwitchButton";
import { SystemHealthDot } from "@/components/SystemHealthDot";
import { LivePositionsPanel } from "@/components/LivePositionsPanel";
import { TradeFeed } from "@/components/TradeFeed";

// Error boundary to catch and display client-side errors
class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen bg-[#06060a] flex items-center justify-center p-8">
          <div className="max-w-lg text-center">
            <h1 className="text-2xl font-bold text-white mb-4">
              AIFred encountered an error
            </h1>
            <p className="text-red-400 text-sm font-mono mb-4 p-4 bg-red-500/10 rounded-lg border border-red-500/20 text-left whitespace-pre-wrap">
              {this.state.error.message}
            </p>
            <button
              onClick={() => {
                localStorage.clear();
                window.location.reload();
              }}
              className="px-6 py-3 bg-emerald-500 text-black font-semibold rounded-lg hover:bg-emerald-400 transition-all"
            >
              Clear Data & Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

const TradingDashboard = dynamic(
  () => import("@/components/trading/TradingDashboard").then(m => m.default || m),
  {
    ssr: false,
    loading: () => (
      <div className="p-8 text-gray-400">Loading dashboard...</div>
    ),
  }
);

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
          <TradingDashboard />
        </div>
      </div>
    </ErrorBoundary>
  );
}
