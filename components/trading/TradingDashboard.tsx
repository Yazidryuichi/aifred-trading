"use client";

import { useEffect, useState, useCallback, Component, type ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Brain,
  Settings,
  ArrowUpDown,
  CheckCircle2,
  X,
  Activity,
  BarChart3,
  Wrench,
  Trophy,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { ConnectWallet } from "@/components/wallet/ConnectWallet";
import {
  type TradingData,
  type ActivityEntry,
  type TradeResult,
  getConnectedBrokers,
  fmt,
  pct,
  INJECTED_STYLES,
} from "@/components/trading/trading-utils";
import { OverviewTab } from "@/components/trading/tabs/OverviewTab";
import { RegimeTab } from "@/components/trading/tabs/RegimeTab";
import { TradesTab } from "@/components/trading/tabs/TradesTab";
import { ActivityTab } from "@/components/trading/tabs/ActivityTab";
import { AgentsTab } from "@/components/trading/tabs/AgentsTab";
import { ExecuteTradeModal } from "@/components/trading/ExecuteTradeModal";

// ─── Error Boundary ──────────────────────────────────────────
class DashboardErrorBoundary extends Component<
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
        <div className="p-8 text-center">
          <p className="text-zinc-400 mb-2">Dashboard render error:</p>
          <p className="text-red-400 text-xs font-mono mb-4">{this.state.error.message}</p>
          <button
            onClick={() => { localStorage.clear(); this.setState({ error: null }); }}
            className="px-4 py-2 bg-emerald-500 text-black rounded-lg text-sm"
          >
            Reset & Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// ─── Main Dashboard (thin orchestrator) ──────────────────────
export default function TradingDashboard() {
  const router = useRouter();
  const [data, setData] = useState<TradingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedTrade, setExpandedTrade] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<
    "overview" | "regime" | "trades" | "activity" | "agents"
  >("overview");
  const [showTradeModal, setShowTradeModal] = useState(false);
  const [activityRefreshKey, setActivityRefreshKey] = useState(0);
  const [tradeToast, setTradeToast] = useState<TradeResult | null>(null);
  const [showWelcome, setShowWelcome] = useState(() => {
    if (typeof window === "undefined") return false;
    return !localStorage.getItem("aifred_welcomed");
  });

  const handleTradeExecuted = useCallback((result: TradeResult) => {
    // Persist trade to localStorage so it survives serverless resets
    try {
      const stored: ActivityEntry[] = JSON.parse(
        localStorage.getItem("aifred_local_trades") || "[]"
      );
      const tradeMode = result.mode || "paper";
      const newEntry: ActivityEntry = {
        id: `local_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
        timestamp: new Date().toISOString(),
        type: "trade_executed",
        severity: "success",
        title: `${result.side} ${result.symbol} — Order Filled`,
        message: `[${tradeMode === "live" ? "LIVE" : "PAPER"}] ${result.side} ${result.quantity} ${result.symbol} @ ${result.executionPrice?.toFixed(4)} | Strategy: ${result.strategy} | Confidence: ${result.confidence}%`,
        details: {
          asset: result.symbol,
          side: result.side as "LONG" | "SHORT",
          strategy: result.strategy,
          confidence: result.confidence,
          entry_price: result.executionPrice,
          stop_loss: result.stopLoss,
          take_profit: result.takeProfit,
          reasoning: result.reasoning,
          technical_signals: result.technicalSignals,
          sentiment_signals: result.sentimentSignals,
          risk_assessment: result.riskAssessment,
          broker: result.broker,
          tier: result.tier,
          mode: tradeMode,
        },
      };
      stored.unshift(newEntry);
      localStorage.setItem(
        "aifred_local_trades",
        JSON.stringify(stored.slice(0, 100))
      );
    } catch { /* localStorage may not be available */ }
    // Show persistent toast + switch to activity tab
    setTradeToast(result);
    setActiveTab("activity");
    setActivityRefreshKey((k) => k + 1);
    // Dismiss toast after 12s
    setTimeout(() => setTradeToast(null), 12000);
  }, []);

  useEffect(() => {
    // Inject custom styles
    const style = document.createElement("style");
    style.textContent = INJECTED_STYLES;
    document.head.appendChild(style);
    return () => {
      document.head.removeChild(style);
    };
  }, []);

  useEffect(() => {
    fetch("/api/trading")
      .then((r) => r.json())
      .then((d) => {
        // Ensure data has required structure — API may return {error: "..."}
        const safeData = {
          summary: {
            totalPnl: 0, winRate: 0, totalTrades: 0, openPositions: 0,
            avgConfidence: 0, signalCount: 0, activeStrategies: 0,
            sharpeRatio: 0, maxDrawdown: 0, profitFactor: 0,
            avgWin: 0, avgLoss: 0, totalFees: 0, currentEquity: 0,
          },
          byAsset: [],
          byStrategy: [],
          byTier: [],
          recentTrades: [],
          openPositions: [],
          equityCurve: [],
          equity: [],
          signals: [],
          ...((d && !d.error) ? d : {}),
        };
        setData(safeData);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#06060a] flex items-center justify-center">
        <motion.div
          initial={false}
          animate={{ opacity: 1 }}
          className="flex flex-col items-center gap-4"
        >
          <div className="w-10 h-10 border-2 border-emerald-500/30 border-t-emerald-500 rounded-full animate-spin" />
          <span
            className="text-zinc-500 text-sm tracking-[0.3em]"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            INITIALIZING AGENTS...
          </span>
        </motion.div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-[#06060a] flex items-center justify-center text-red-400">
        <span style={{ fontFamily: "JetBrains Mono, monospace" }}>
          ERROR: {error || "No data"}
        </span>
      </div>
    );
  }

  const summary = {
    totalPnl: 0, winRate: 0, totalTrades: 0, openPositions: 0,
    avgConfidence: 0, signalCount: 0, activeStrategies: 0,
    sharpeRatio: 0, maxDrawdown: 0, profitFactor: 0,
    avgWin: 0, avgLoss: 0, totalFees: 0, currentEquity: 0,
    ...(data.summary ?? {}),
  };
  const isPositive = summary.totalPnl >= 0;

  return (
    <DashboardErrorBoundary>
    <div
      className="min-h-screen bg-[#06060a] text-white noise-bg relative overflow-hidden"
      style={{ fontFamily: "Outfit, sans-serif" }}
    >
      {/* Ambient glow effects */}
      <div className="fixed inset-0 pointer-events-none">
        <div
          className="absolute top-0 left-1/4 w-[600px] h-[600px] rounded-full opacity-[0.03]"
          style={{
            background:
              "radial-gradient(circle, rgba(16,185,129,1) 0%, transparent 70%)",
          }}
        />
        <div
          className="absolute bottom-0 right-1/4 w-[400px] h-[400px] rounded-full opacity-[0.02]"
          style={{
            background:
              "radial-gradient(circle, rgba(99,102,241,1) 0%, transparent 70%)",
          }}
        />
      </div>

      {/* ─── Header ─────────────────────────────────────────── */}
      <header className="relative z-10 border-b border-white/[0.06] px-4 md:px-6 py-3 md:py-4">
        <div className="max-w-[1600px] mx-auto">
          {/* Top row: Logo + Execute Trade + Settings */}
          <div className="flex items-center justify-between mb-3 md:mb-0">
            <div className="flex items-center gap-3 md:gap-4">
              <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-emerald-500 to-emerald-700 flex items-center justify-center">
                <Brain className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1
                  className="text-lg font-bold tracking-tight"
                  style={{ fontFamily: "Outfit, sans-serif" }}
                >
                  AIFred
                </h1>
                <div className="flex items-center gap-2">
                  {(() => {
                    const brokers = getConnectedBrokers();
                    const hasLive = brokers.length > 0;
                    return (
                      <span
                        className={`text-[9px] px-2 py-0.5 rounded-full tracking-wider font-medium ${
                          hasLive
                            ? "bg-green-500/15 border border-green-500/25 text-green-400"
                            : "bg-indigo-500/15 border border-indigo-500/25 text-indigo-400"
                        }`}
                        style={{ fontFamily: "JetBrains Mono, monospace" }}
                      >
                        {hasLive ? "LIVE READY" : "AI TRADER"}
                      </span>
                    );
                  })()}
                  <div
                    className="w-2 h-2 rounded-full bg-emerald-400"
                    style={{ animation: "pulse-glow 2s ease-in-out infinite" }}
                  />
                  <span
                    className="text-[10px] text-emerald-400/80 tracking-wider hidden md:inline"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    7 AGENTS ONLINE
                  </span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 md:gap-4">
              {/* Wallet Connection */}
              <ConnectWallet />

              {/* Execute Trade Button — always visible, prominent */}
              <button
                onClick={() => setShowTradeModal(true)}
                className="flex items-center gap-2 px-4 md:px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black text-xs md:text-sm font-bold transition-all shadow-lg shadow-emerald-500/25 active:scale-95"
                style={{ fontFamily: "Outfit, sans-serif" }}
              >
                <ArrowUpDown className="w-4 h-4" />
                <span>Execute Trade</span>
              </button>

              {/* Arena */}
              <button
                onClick={() => router.push("/trading/arena")}
                className="w-9 h-9 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center hover:bg-amber-500/20 hover:border-amber-500/30 transition-all text-amber-400 hover:text-amber-300"
                title="AI Arena"
                aria-label="Open AI competition arena"
              >
                <Trophy className="w-4 h-4" />
              </button>

              {/* AI Decisions */}
              <button
                onClick={() => router.push("/trading/decisions")}
                className="w-9 h-9 rounded-lg bg-white/[0.04] border border-white/[0.06] flex items-center justify-center hover:bg-white/[0.08] hover:border-white/[0.12] transition-all text-zinc-500 hover:text-zinc-300"
                title="AI Decisions"
                aria-label="Open AI decision history"
              >
                <Brain className="w-4 h-4" />
              </button>

              {/* Stats */}
              <button
                onClick={() => router.push("/trading/stats")}
                className="w-9 h-9 rounded-lg bg-white/[0.04] border border-white/[0.06] flex items-center justify-center hover:bg-white/[0.08] hover:border-white/[0.12] transition-all text-zinc-500 hover:text-zinc-300"
                title="Trading Stats"
                aria-label="Open trading stats"
              >
                <BarChart3 className="w-4 h-4" />
              </button>

              {/* Config */}
              <button
                onClick={() => router.push("/trading/config")}
                className="w-9 h-9 rounded-lg bg-white/[0.04] border border-white/[0.06] flex items-center justify-center hover:bg-white/[0.08] hover:border-white/[0.12] transition-all text-zinc-500 hover:text-zinc-300"
                title="Config"
                aria-label="Open AI Traders config"
              >
                <Wrench className="w-4 h-4" />
              </button>

              {/* Settings */}
              <button
                onClick={() => router.push("/trading/settings")}
                className="w-9 h-9 rounded-lg bg-white/[0.04] border border-white/[0.06] flex items-center justify-center hover:bg-white/[0.08] hover:border-white/[0.12] transition-all text-zinc-500 hover:text-zinc-300"
                title="Settings"
                aria-label="Open settings"
              >
                <Settings className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Nav tabs — scrollable on mobile */}
          <div className="flex gap-1 bg-white/[0.03] rounded-lg p-1 overflow-x-auto" role="tablist" aria-label="Dashboard navigation">
            {(["overview", "regime", "trades", "activity", "agents"] as const).map((tab) => (
              <button
                key={tab}
                role="tab"
                aria-selected={activeTab === tab}
                aria-controls={`tabpanel-${tab}`}
                id={`tab-${tab}`}
                onClick={() => setActiveTab(tab)}
                className={`flex-1 md:flex-none px-3 md:px-4 py-1.5 text-xs font-medium rounded-md transition-all tracking-wider uppercase whitespace-nowrap ${
                  activeTab === tab
                    ? "bg-white/[0.08] text-white"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* ─── Trade Execution Toast ───────────────────────── */}
      <div aria-live="polite" aria-atomic="true">
      <AnimatePresence>
        {tradeToast && (
          <motion.div
            initial={false}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -16 }}
            transition={{ duration: 0.25 }}
            role="status"
            className="fixed top-20 right-6 z-40 w-80"
            style={{
              background: "linear-gradient(135deg, rgba(16,185,129,0.12) 0%, rgba(10,10,15,0.98) 100%)",
              border: "1px solid rgba(16,185,129,0.3)",
              borderRadius: "12px",
              backdropFilter: "blur(20px)",
            }}
          >
            <div className="p-4">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-bold ${
                  tradeToast.mode === "live"
                    ? "bg-green-500/20 text-green-400 border border-green-500/40"
                    : "bg-yellow-500/20 text-yellow-400 border border-yellow-500/40"
                }`} style={{ fontFamily: "JetBrains Mono, monospace" }}>
                  {tradeToast.mode === "live" ? "LIVE" : "PAPER"}
                </span>
                <span className="text-sm font-semibold text-white" style={{ fontFamily: "Outfit, sans-serif" }}>
                  {tradeToast.side} {tradeToast.symbol} — Filled
                </span>
                <button onClick={() => setTradeToast(null)} className="ml-auto text-zinc-600 hover:text-zinc-400">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="grid grid-cols-3 gap-1.5 mb-2 text-[10px]" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                <div className="bg-white/[0.04] rounded px-2 py-1">
                  <div className="text-zinc-600">Price</div>
                  <div className="text-zinc-200">{tradeToast.executionPrice?.toFixed(4)}</div>
                </div>
                <div className="bg-white/[0.04] rounded px-2 py-1">
                  <div className="text-zinc-600">Conf.</div>
                  <div className="text-amber-400">{tradeToast.confidence}%</div>
                </div>
                <div className="bg-white/[0.04] rounded px-2 py-1">
                  <div className="text-zinc-600">Tier</div>
                  <div className="text-emerald-400">{tradeToast.tier}</div>
                </div>
              </div>
              {tradeToast.reasoning && (
                <p className="text-[10px] text-zinc-400 leading-relaxed line-clamp-2">
                  {tradeToast.reasoning}
                </p>
              )}
              <p className="text-[10px] text-indigo-400 mt-2 flex items-center gap-1">
                <Activity className="w-2.5 h-2.5" />
                Full log visible in Activity tab below ↓
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      </div>

      {/* ─── Welcome Panel (first visit) ──────────────────── */}
      <AnimatePresence>
        {showWelcome && (
          <motion.div
            initial={false}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, height: 0 }}
            className="relative z-10 max-w-[1600px] mx-auto px-4 md:px-6 pt-4"
          >
            <div className="rounded-2xl p-5 md:p-6 border border-indigo-500/15" style={{ background: "linear-gradient(135deg, rgba(99,102,241,0.06) 0%, rgba(16,185,129,0.04) 100%)" }}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <h2 className="text-base md:text-lg font-bold text-white mb-2" style={{ fontFamily: "Outfit, sans-serif" }}>
                    Welcome to AIFred — Multi-Agent Trading Intelligence
                  </h2>
                  <p className="text-xs text-zinc-400 leading-relaxed mb-4 max-w-2xl">
                    7 AI agents work together to analyze markets, generate signals, manage risk, and execute trades autonomously.
                    The system continuously improves through walk-forward validation and Bayesian parameter optimization.
                  </p>
                  <div className="flex flex-wrap gap-2 mb-4">
                    {[
                      { label: "1. Connect Broker", desc: "Link your exchange API keys" },
                      { label: "2. Configure Risk", desc: "Set position sizes & limits" },
                      { label: "3. Start Trading", desc: "AI executes trades for you" },
                    ].map((s) => (
                      <div key={s.label} className="bg-white/[0.04] rounded-lg px-3 py-2 flex-1 min-w-[140px]">
                        <div className="text-[10px] text-emerald-400 font-semibold tracking-wider uppercase" style={{ fontFamily: "JetBrains Mono, monospace" }}>{s.label}</div>
                        <div className="text-[10px] text-zinc-500 mt-0.5">{s.desc}</div>
                      </div>
                    ))}
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => { setShowWelcome(false); localStorage.setItem("aifred_welcomed", "1"); setShowTradeModal(true); }}
                      className="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black text-xs font-bold transition-all"
                      style={{ fontFamily: "Outfit, sans-serif" }}
                    >
                      Execute First Trade
                    </button>
                    <button
                      onClick={() => { setShowWelcome(false); localStorage.setItem("aifred_welcomed", "1"); router.push("/trading/settings"); }}
                      className="px-4 py-2 rounded-lg bg-white/[0.06] hover:bg-white/[0.1] text-zinc-300 text-xs font-medium transition-all border border-white/[0.08]"
                      style={{ fontFamily: "Outfit, sans-serif" }}
                    >
                      Connect Broker
                    </button>
                  </div>
                </div>
                <button
                  onClick={() => { setShowWelcome(false); localStorage.setItem("aifred_welcomed", "1"); }}
                  aria-label="Dismiss welcome panel"
                  className="text-zinc-600 hover:text-zinc-400 transition-colors flex-shrink-0"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ─── Content ────────────────────────────────────────── */}
      <main id="main-content" className="relative z-10 max-w-[1600px] mx-auto px-6 py-6" role="tabpanel" aria-labelledby={`tab-${activeTab}`}>
        <AnimatePresence mode="wait">
          {activeTab === "overview" && (
            <OverviewTab
              key="overview"
              data={data}
              onNavigateActivity={() => setActiveTab("activity")}
            />
          )}
          {activeTab === "regime" && <RegimeTab key="regime" />}
          {activeTab === "trades" && (
            <TradesTab
              key="trades"
              trades={data.recentTrades ?? []}
              openPositions={data.openPositions ?? []}
              expandedTrade={expandedTrade}
              setExpandedTrade={setExpandedTrade}
            />
          )}
          {activeTab === "activity" && <ActivityTab key={`activity-${activityRefreshKey}`} />}
          {activeTab === "agents" && <AgentsTab key="agents" data={data} />}
        </AnimatePresence>
      </main>

      {/* ─── Footer ticker ──────────────────────────────────── */}
      <footer className="fixed bottom-0 left-0 right-0 z-20 border-t border-white/[0.04] bg-[#06060a]/90 backdrop-blur-sm">
        <div className="overflow-hidden h-8 flex items-center">
          <div
            className="flex gap-12 whitespace-nowrap"
            style={{
              animation: "ticker 30s linear infinite",
              fontFamily: "JetBrains Mono, monospace",
            }}
          >
            {[...(data.byAsset ?? []), ...(data.byAsset ?? [])].map((a, i) => (
              <span key={i} className="text-[11px] flex items-center gap-2">
                <span className="text-zinc-400">{a.asset}</span>
                <span
                  className={a.pnl >= 0 ? "text-emerald-400" : "text-red-400"}
                >
                  {a.pnl >= 0 ? "+" : ""}
                  {fmt(a.pnl)}
                </span>
                <span className="text-zinc-600">|</span>
                <span className="text-zinc-500">WR {pct(a.winRate)}</span>
              </span>
            ))}
          </div>
        </div>
      </footer>

      {/* ─── Execute Trade Modal ─────────────────────────── */}
      <AnimatePresence>
        {showTradeModal && (
          <ExecuteTradeModal
            onClose={() => setShowTradeModal(false)}
            onTradeExecuted={handleTradeExecuted}
          />
        )}
      </AnimatePresence>
    </div>
    </DashboardErrorBoundary>
  );
}
