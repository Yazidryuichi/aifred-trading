"use client";

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  TrendingUp,
  TrendingDown,
  Activity,
  Shield,
  Zap,
  Brain,
  Layers,
  AlertTriangle,
  Target,
  BarChart3,
  CheckCircle2,
  Loader2,
  X,
} from "lucide-react";
import {
  type RegimeApiResponse,
  type BacktestApiResponse,
  fmt,
  REGIME_DISPLAY,
  REGIME_BAR_COLORS,
  SIGNAL_DISPLAY,
} from "@/components/trading/trading-utils";

export function RegimeTab() {
  const [regimeData, setRegimeData] = useState<RegimeApiResponse | null>(null);
  const [backtestData, setBacktestData] = useState<BacktestApiResponse | null>(null);
  const [regimeLoading, setRegimeLoading] = useState(true);
  const [backtestLoading, setBacktestLoading] = useState(true);
  const [regimeError, setRegimeError] = useState<string | null>(null);
  const [backtestError, setBacktestError] = useState<string | null>(null);

  const fetchRegime = useCallback(() => {
    setRegimeLoading(true);
    setRegimeError(null);
    fetch("/api/trading/regime?symbol=BTCUSDT")
      .then((r) => r.json())
      .then((data: RegimeApiResponse) => {
        if (!data.success) throw new Error(data.error || "Failed");
        setRegimeData(data);
      })
      .catch((e) => setRegimeError(e.message))
      .finally(() => setRegimeLoading(false));
  }, []);

  const fetchBacktest = useCallback(() => {
    setBacktestLoading(true);
    setBacktestError(null);
    fetch("/api/trading/backtest")
      .then((r) => r.json())
      .then((data: BacktestApiResponse) => {
        if (!data.success) throw new Error(data.error || "Failed");
        setBacktestData(data);
      })
      .catch((e) => setBacktestError(e.message))
      .finally(() => setBacktestLoading(false));
  }, []);

  useEffect(() => {
    fetchRegime();
    fetchBacktest();
    // Auto-refresh regime every 5 minutes
    const interval = setInterval(fetchRegime, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchRegime, fetchBacktest]);

  if (regimeLoading && backtestLoading) {
    return (
      <motion.div
        initial={false}
        animate={{ opacity: 1 }}
        className="flex items-center justify-center py-32"
      >
        <Loader2 className="w-6 h-6 text-zinc-500 animate-spin" />
        <span className="ml-3 text-sm text-zinc-500" style={{ fontFamily: "JetBrains Mono, monospace" }}>
          Analyzing regime...
        </span>
      </motion.div>
    );
  }

  const regime = regimeData?.currentRegime || "neutral";
  const regimeInfo = REGIME_DISPLAY[regime] || REGIME_DISPLAY.neutral;
  const signalInfo = SIGNAL_DISPLAY[regimeData?.signal || "CASH"];
  const confirmations = regimeData?.confirmations || [];
  const passed = regimeData?.confirmationsPassed || 0;
  const required = regimeData?.confirmationsRequired || 7;
  const probabilities = regimeData?.regimeProbabilities || {};
  const maxProb = Math.max(...Object.values(probabilities), 0.01);

  return (
    <motion.div
      initial={false}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.3 }}
      className="space-y-6"
    >
      {/* ── Section 1: Current Regime Status ──────────────── */}
      {regimeError ? (
        <div className="card-glass rounded-2xl p-6">
          <div className="flex items-center gap-3 text-red-400">
            <AlertTriangle className="w-5 h-5" />
            <span className="text-sm" style={{ fontFamily: "JetBrains Mono, monospace" }}>
              Regime analysis error: {regimeError}
            </span>
          </div>
          <button
            onClick={fetchRegime}
            className="mt-3 px-4 py-1.5 text-xs rounded-lg bg-white/[0.06] hover:bg-white/[0.1] text-zinc-300 transition-all"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            Retry
          </button>
        </div>
      ) : (
        <div className="card-glass rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-5">
            <Brain className="w-4 h-4 text-indigo-400" />
            <span className="text-xs font-medium tracking-wider uppercase text-zinc-500" style={{ fontFamily: "JetBrains Mono, monospace" }}>
              HMM Regime Detection — {regimeData?.symbol || "BTCUSDT"}
            </span>
            <span className="ml-auto text-[10px] text-zinc-600" style={{ fontFamily: "JetBrains Mono, monospace" }}>
              {regimeData?.timestamp ? new Date(regimeData.timestamp).toLocaleTimeString() : ""}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {/* Regime badge */}
            <div className="flex flex-col items-center justify-center">
              <div className={`px-5 py-2.5 rounded-xl border ${regimeInfo.bg}`}>
                <span className={`text-lg font-bold ${regimeInfo.color}`} style={{ fontFamily: "Outfit, sans-serif" }}>
                  {regimeInfo.label}
                </span>
              </div>
              <span className="text-[10px] text-zinc-600 mt-2 uppercase tracking-widest" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                Current Regime
              </span>
            </div>

            {/* Confidence */}
            <div className="flex flex-col items-center justify-center">
              <span className="text-3xl font-bold text-white" style={{ fontFamily: "Outfit, sans-serif" }}>
                {((regimeData?.regimeConfidence || 0) * 100).toFixed(1)}%
              </span>
              <span className="text-[10px] text-zinc-600 mt-1 uppercase tracking-widest" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                Confidence
              </span>
            </div>

            {/* Signal */}
            <div className="flex flex-col items-center justify-center">
              <div className="flex items-center gap-2">
                {signalInfo.icon === "arrow-up" && <TrendingUp className={`w-5 h-5 ${signalInfo.color}`} />}
                {signalInfo.icon === "pause" && <Activity className={`w-5 h-5 ${signalInfo.color}`} />}
                {signalInfo.icon === "arrow-down" && <TrendingDown className={`w-5 h-5 ${signalInfo.color}`} />}
                {signalInfo.icon === "minus" && <Shield className={`w-5 h-5 ${signalInfo.color}`} />}
                <span className={`text-lg font-bold ${signalInfo.color}`} style={{ fontFamily: "JetBrains Mono, monospace" }}>
                  {signalInfo.label}
                </span>
              </div>
              <span className="text-[10px] text-zinc-600 mt-1 uppercase tracking-widest" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                Signal
              </span>
            </div>

            {/* Price */}
            <div className="flex flex-col items-center justify-center">
              <span className="text-2xl font-bold text-white" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                ${regimeData?.currentPrice?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || "—"}
              </span>
              <span className="text-[10px] text-zinc-600 mt-1 uppercase tracking-widest" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                Current Price
              </span>
            </div>
          </div>
        </div>
      )}

      {/* ── Section 2: 8 Confirmation Signals ─────────────── */}
      {!regimeError && (
        <div className="card-glass rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <Target className="w-4 h-4 text-amber-400" />
            <span className="text-xs font-medium tracking-wider uppercase text-zinc-500" style={{ fontFamily: "JetBrains Mono, monospace" }}>
              Entry Confirmations
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
            {confirmations.map((c) => (
              <div
                key={c.name}
                className={`rounded-xl border p-3 transition-all ${
                  c.passed
                    ? "bg-emerald-500/[0.06] border-emerald-500/20"
                    : "bg-red-500/[0.06] border-red-500/20"
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[11px] font-medium text-zinc-300 truncate" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                    {c.name}
                  </span>
                  {c.passed ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                  ) : (
                    <X className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
                  )}
                </div>
                <div className="text-sm font-semibold text-white" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                  {c.value}
                </div>
                <div className="text-[10px] text-zinc-600 mt-0.5" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                  {c.threshold}
                </div>
              </div>
            ))}
          </div>

          {/* Progress bar */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-400" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                {passed}/{confirmations.length} Confirmations Passed
              </span>
              <span
                className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${
                  passed >= required
                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                    : "bg-red-500/15 text-red-400 border border-red-500/25"
                }`}
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {passed >= required ? "ENTRY CONFIRMED" : "ENTRY BLOCKED"}
              </span>
            </div>
            <div className="w-full h-2 rounded-full bg-white/[0.06] overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  passed >= required ? "bg-emerald-500" : passed >= required - 2 ? "bg-amber-500" : "bg-red-500"
                }`}
                style={{ width: `${(passed / confirmations.length) * 100}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {/* ── Section 3: Regime Probabilities ──────────────── */}
      {!regimeError && Object.keys(probabilities).length > 0 && (
        <div className="card-glass rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 className="w-4 h-4 text-indigo-400" />
            <span className="text-xs font-medium tracking-wider uppercase text-zinc-500" style={{ fontFamily: "JetBrains Mono, monospace" }}>
              Regime Probabilities
            </span>
          </div>

          <div className="space-y-2.5">
            {Object.entries(probabilities).map(([r, prob]) => {
              const info = REGIME_DISPLAY[r] || { label: r, color: "text-zinc-400" };
              const barColor = REGIME_BAR_COLORS[r] || "bg-zinc-500";
              const isActive = r === regime;
              return (
                <div key={r} className="flex items-center gap-3">
                  <span
                    className={`text-[11px] w-28 truncate ${isActive ? info.color + " font-bold" : "text-zinc-500"}`}
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {info.label}
                  </span>
                  <div className="flex-1 h-5 rounded bg-white/[0.04] overflow-hidden relative">
                    <div
                      className={`h-full rounded transition-all duration-700 ${barColor} ${isActive ? "opacity-100" : "opacity-50"}`}
                      style={{ width: `${(prob / maxProb) * 100}%` }}
                    />
                  </div>
                  <span
                    className={`text-[11px] w-14 text-right ${isActive ? "text-white font-bold" : "text-zinc-500"}`}
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {(prob * 100).toFixed(1)}%
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Section 4: Backtest Performance ──────────────── */}
      {backtestError ? (
        <div className="card-glass rounded-2xl p-6">
          <div className="flex items-center gap-3 text-amber-400">
            <AlertTriangle className="w-5 h-5" />
            <span className="text-sm" style={{ fontFamily: "JetBrains Mono, monospace" }}>
              Backtest error: {backtestError}
            </span>
          </div>
          <button
            onClick={fetchBacktest}
            className="mt-3 px-4 py-1.5 text-xs rounded-lg bg-white/[0.06] hover:bg-white/[0.1] text-zinc-300 transition-all"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            Retry
          </button>
        </div>
      ) : backtestLoading ? (
        <div className="card-glass rounded-2xl p-6 flex items-center justify-center py-12">
          <Loader2 className="w-5 h-5 text-zinc-500 animate-spin" />
          <span className="ml-3 text-sm text-zinc-500" style={{ fontFamily: "JetBrains Mono, monospace" }}>
            Running backtest...
          </span>
        </div>
      ) : backtestData?.metrics ? (
        <>
          <div className="card-glass rounded-2xl p-6">
            <div className="flex items-center gap-2 mb-1">
              <Layers className="w-4 h-4 text-emerald-400" />
              <span className="text-xs font-medium tracking-wider uppercase text-zinc-500" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                Backtest Performance — 180 Days
              </span>
              <span className="text-[9px] text-amber-400 font-bold bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 rounded tracking-wider uppercase" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                DEMO DATA
              </span>
            </div>
            <p className="text-[10px] text-zinc-600 mb-4" style={{ fontFamily: "JetBrains Mono, monospace" }}>
              Simulated results — not indicative of future performance
            </p>

            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              {[
                {
                  label: "Total Return",
                  value: `${backtestData.metrics.totalReturn >= 0 ? "+" : ""}${backtestData.metrics.totalReturn.toFixed(2)}%`,
                  color: backtestData.metrics.totalReturn >= 0 ? "text-emerald-400 glow-green" : "text-red-400 glow-red",
                },
                {
                  label: "Alpha",
                  value: `${backtestData.metrics.alpha >= 0 ? "+" : ""}${backtestData.metrics.alpha.toFixed(2)}%`,
                  color: backtestData.metrics.alpha >= 0 ? "text-emerald-400" : "text-red-400",
                },
                {
                  label: "Win Rate",
                  value: `${backtestData.metrics.winRate.toFixed(1)}%`,
                  color: backtestData.metrics.winRate >= 50 ? "text-emerald-400" : "text-amber-400",
                },
                {
                  label: "Max Drawdown",
                  value: `${backtestData.metrics.maxDrawdown.toFixed(2)}%`,
                  color: "text-red-400",
                },
                {
                  label: "Sharpe Ratio",
                  value: backtestData.metrics.sharpeRatio.toFixed(2),
                  color: backtestData.metrics.sharpeRatio >= 1 ? "text-emerald-400" : backtestData.metrics.sharpeRatio >= 0.5 ? "text-amber-400" : "text-red-400",
                },
              ].map((m) => (
                <div key={m.label} className="text-center">
                  <div className={`text-xl md:text-2xl font-bold ${m.color}`} style={{ fontFamily: "JetBrains Mono, monospace" }}>
                    {m.value}
                  </div>
                  <div className="text-[10px] text-zinc-600 mt-1 uppercase tracking-widest" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                    {m.label}
                  </div>
                </div>
              ))}
            </div>

            {/* Secondary metrics */}
            <div className="grid grid-cols-3 md:grid-cols-6 gap-3 mt-5 pt-4 border-t border-white/[0.06]">
              {[
                { label: "Trades", value: String(backtestData.metrics.totalTrades) },
                { label: "Winners", value: String(backtestData.metrics.winningTrades) },
                { label: "Losers", value: String(backtestData.metrics.losingTrades) },
                { label: "Avg Return", value: `${backtestData.metrics.avgTradeReturn.toFixed(2)}%` },
                { label: "Avg Hold", value: `${backtestData.metrics.avgHoldDuration.toFixed(0)}h` },
                { label: "Final Equity", value: fmt(backtestData.metrics.finalEquity) },
              ].map((m) => (
                <div key={m.label} className="text-center">
                  <div className="text-sm font-semibold text-zinc-200" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                    {m.value}
                  </div>
                  <div className="text-[9px] text-zinc-600 mt-0.5 uppercase tracking-widest" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                    {m.label}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* ── Section 5: Recent Regime Trades ────────────── */}
          {backtestData.trades.length > 0 && (
            <div className="card-glass rounded-2xl p-6">
              <div className="flex items-center gap-2 mb-4">
                <Activity className="w-4 h-4 text-blue-400" />
                <span className="text-xs font-medium tracking-wider uppercase text-zinc-500" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                  Recent Regime Trades
                </span>
                <span className="ml-auto text-[10px] text-zinc-600" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                  Last {Math.min(backtestData.trades.length, 20)} of {backtestData.trades.length}
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-[11px]" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                  <thead>
                    <tr className="text-zinc-600 uppercase tracking-wider border-b border-white/[0.06]">
                      <th className="text-left py-2 pr-3">Entry</th>
                      <th className="text-left py-2 pr-3">Exit</th>
                      <th className="text-right py-2 pr-3">Entry $</th>
                      <th className="text-right py-2 pr-3">Exit $</th>
                      <th className="text-right py-2 pr-3">PnL%</th>
                      <th className="text-left py-2 pr-3">Regime</th>
                      <th className="text-left py-2">Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {backtestData.trades.slice(-20).reverse().map((t, i) => {
                      const rInfo = REGIME_DISPLAY[t.regime] || REGIME_DISPLAY.neutral;
                      return (
                        <tr
                          key={i}
                          className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors"
                        >
                          <td className="py-2 pr-3 text-zinc-400">
                            {new Date(t.entryDate).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                          </td>
                          <td className="py-2 pr-3 text-zinc-400">
                            {new Date(t.exitDate).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                          </td>
                          <td className="py-2 pr-3 text-right text-zinc-300">
                            {(t.entryPrice ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                          </td>
                          <td className="py-2 pr-3 text-right text-zinc-300">
                            {(t.exitPrice ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                          </td>
                          <td className={`py-2 pr-3 text-right font-semibold ${t.pnlPercent >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                            {t.pnlPercent >= 0 ? "+" : ""}{t.pnlPercent.toFixed(2)}%
                          </td>
                          <td className="py-2 pr-3">
                            <span className={`text-[10px] ${rInfo.color}`}>{rInfo.label}</span>
                          </td>
                          <td className="py-2">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                              t.exitReason === "stop_loss"
                                ? "bg-red-500/15 text-red-400"
                                : t.exitReason === "regime_flip"
                                ? "bg-amber-500/15 text-amber-400"
                                : "bg-zinc-500/15 text-zinc-400"
                            }`}>
                              {t.exitReason.replace("_", " ")}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      ) : null}
    </motion.div>
  );
}
