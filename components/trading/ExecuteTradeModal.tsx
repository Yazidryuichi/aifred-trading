"use client";

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Shield,
  Zap,
  Eye,
  Brain,
  AlertTriangle,
  Wifi,
  X,
  ArrowUpDown,
  CheckCircle2,
  Loader2,
  BarChart3,
} from "lucide-react";
import {
  type TradeResult,
  type ConnectedBrokerInfo,
  getConnectedBrokers,
  fetchBrokerStatus,
  AVAILABLE_SYMBOLS,
} from "@/components/trading/trading-utils";

export function ExecuteTradeModal({
  onClose,
  onTradeExecuted,
}: {
  onClose: () => void;
  onTradeExecuted: (result: TradeResult) => void;
}) {
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [side, setSide] = useState<"LONG" | "SHORT">("LONG");
  const [quantity, setQuantity] = useState("0.01");
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState<TradeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(8);
  const [tradeMode, setTradeMode] = useState<"paper" | "live">("paper");
  const [selectedBroker, setSelectedBroker] = useState<string>("");
  const [connectedBrokers, setConnectedBrokers] = useState<ConnectedBrokerInfo[]>(() => getConnectedBrokers());

  // Refresh connected brokers on mount (modal is conditionally rendered, so mount = open)
  useEffect(() => {
    setConnectedBrokers(getConnectedBrokers());
    // Also fetch server-side broker status and cache it
    fetchBrokerStatus().then((brokers) => {
      try { localStorage.setItem("aifred_broker_status", JSON.stringify(brokers)); } catch {}
      setConnectedBrokers(getConnectedBrokers());
    }).catch(() => {});
  }, []);

  // Auto-close 8 seconds after result appears
  useEffect(() => {
    if (!result) return;
    setCountdown(8);
    const timer = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          clearInterval(timer);
          onClose();
          return 0;
        }
        return c - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [result, onClose]);

  const handleExecute = useCallback(async () => {
    setExecuting(true);
    setError(null);
    try {
      // Credentials are now server-side only (env vars)
      const brokerCredentials = undefined;

      const res = await fetch("/api/trading/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          side,
          quantity: parseFloat(quantity) || 0.01,
          orderType,
          mode: tradeMode,
          brokerId: tradeMode === "live" ? selectedBroker : undefined,
          credentials: brokerCredentials || undefined,
          forceExecution: true,
        }),
      });
      const data: TradeResult = await res.json();
      if (data.success) {
        const resultWithMode = { ...data, mode: tradeMode };
        setResult(resultWithMode);
        onTradeExecuted(resultWithMode);
      } else {
        setError(data.message || "Trade failed");
      }
    } catch {
      setError("Network error — could not reach trading API");
    } finally {
      setExecuting(false);
    }
  }, [symbol, side, quantity, orderType, tradeMode, selectedBroker, onTradeExecuted]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-modal="true" aria-labelledby="execute-trade-title">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />
      {/* Modal */}
      <motion.div
        initial={false}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 12 }}
        transition={{ duration: 0.2 }}
        className="relative z-10 w-full max-w-md mx-4"
        style={{
          background: "linear-gradient(135deg, rgba(15,15,20,0.98) 0%, rgba(10,10,15,0.98) 100%)",
          border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: "16px",
          backdropFilter: "blur(40px)",
        }}
      >
        {!result ? (
          <div className="p-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                  <ArrowUpDown className="w-4 h-4 text-emerald-400" />
                </div>
                <div>
                  <h2 id="execute-trade-title" className="text-base font-bold text-white" style={{ fontFamily: "Outfit, sans-serif" }}>
                    Execute Trade
                  </h2>
                  <p className="text-[11px] tracking-wider" style={{ fontFamily: "JetBrains Mono, monospace", color: tradeMode === "live" ? "#4ade80" : "#a78bfa" }}>
                    {tradeMode === "live" ? "LIVE TRADING" : "SIMULATION MODE"}
                  </p>
                </div>
              </div>
              <button
                onClick={onClose}
                aria-label="Close trade modal"
                className="w-8 h-8 rounded-lg bg-white/[0.04] flex items-center justify-center hover:bg-white/[0.08] transition-colors text-zinc-500 hover:text-zinc-300"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Trading Mode Toggle */}
            <div className="flex items-center gap-2 p-1 rounded-lg border border-zinc-700 mb-3">
              <button
                onClick={() => setTradeMode("paper")}
                className={`flex-1 py-2 px-4 rounded-md text-xs font-semibold transition-all ${
                  tradeMode === "paper"
                    ? "bg-indigo-500/20 text-indigo-400 border border-indigo-500/50"
                    : "text-zinc-500 hover:text-zinc-300 border border-transparent"
                }`}
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                SIMULATE
              </button>
              <button
                onClick={() => {
                  setTradeMode("live");
                  if (!selectedBroker && connectedBrokers.length > 0) {
                    setSelectedBroker(connectedBrokers[0].id);
                  }
                }}
                className={`flex-1 py-2 px-4 rounded-md text-xs font-semibold transition-all ${
                  tradeMode === "live"
                    ? "bg-green-500/20 text-green-400 border border-green-500/50"
                    : "text-zinc-500 hover:text-zinc-300 border border-transparent"
                }`}
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                LIVE MODE
              </button>
            </div>

            {/* Mode-specific banners */}
            {tradeMode === "paper" && (
              <div className="mb-3 px-3 py-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center gap-2">
                <Eye className="w-3.5 h-3.5 text-indigo-400 flex-shrink-0" />
                <span className="text-[11px] text-indigo-300/90">Simulation Mode — Validating strategy before live execution</span>
              </div>
            )}
            {tradeMode === "live" && connectedBrokers.length > 0 && (
              <>
                <div className="mb-3 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center gap-2">
                  <AlertTriangle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
                  <span className="text-[11px] text-red-300/90">LIVE TRADING — Real orders will be placed through your connected broker</span>
                </div>
                <div className="mb-4">
                  <label className="block text-[11px] text-zinc-500 tracking-wider mb-1.5 uppercase" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                    Broker
                  </label>
                  <select
                    value={selectedBroker}
                    onChange={(e) => setSelectedBroker(e.target.value)}
                    className="w-full bg-white/[0.04] border border-green-500/20 rounded-lg px-3 py-2.5 text-sm text-white outline-none focus:border-green-500/40 transition-colors"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {connectedBrokers.map((b) => (
                      <option key={b.id} value={b.id} style={{ background: "#0a0a0f" }}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                </div>
              </>
            )}
            {tradeMode === "live" && connectedBrokers.length === 0 && (
              <div className="mb-3 px-3 py-2.5 rounded-lg bg-zinc-800 border border-zinc-700 flex items-center gap-2">
                <Wifi className="w-3.5 h-3.5 text-zinc-500 flex-shrink-0" />
                <span className="text-[11px] text-zinc-400">Connect a broker in <strong className="text-zinc-300">Settings</strong> to enable live trading</span>
              </div>
            )}

            {/* Symbol */}
            <div className="mb-4">
              <label className="block text-[11px] text-zinc-500 tracking-wider mb-1.5 uppercase" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                Symbol
              </label>
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2.5 text-sm text-white outline-none focus:border-emerald-500/40 transition-colors"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {AVAILABLE_SYMBOLS.map((s) => (
                  <option key={s} value={s} style={{ background: "#0a0a0f" }}>
                    {s}
                  </option>
                ))}
              </select>
            </div>

            {/* Side */}
            <div className="mb-4">
              <label className="block text-[11px] text-zinc-500 tracking-wider mb-1.5 uppercase" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                Direction
              </label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => setSide("LONG")}
                  className={`py-2.5 rounded-lg text-sm font-semibold transition-all border ${
                    side === "LONG"
                      ? "bg-emerald-500/20 border-emerald-500/40 text-emerald-400"
                      : "bg-white/[0.03] border-white/[0.06] text-zinc-500 hover:text-zinc-300"
                  }`}
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  ▲ LONG
                </button>
                <button
                  onClick={() => setSide("SHORT")}
                  className={`py-2.5 rounded-lg text-sm font-semibold transition-all border ${
                    side === "SHORT"
                      ? "bg-red-500/20 border-red-500/40 text-red-400"
                      : "bg-white/[0.03] border-white/[0.06] text-zinc-500 hover:text-zinc-300"
                  }`}
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  ▼ SHORT
                </button>
              </div>
            </div>

            {/* Quantity */}
            <div className="mb-4">
              <label className="block text-[11px] text-zinc-500 tracking-wider mb-1.5 uppercase" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                Quantity
              </label>
              <input
                type="number"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                step="0.001"
                min="0.001"
                className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2.5 text-sm text-white outline-none focus:border-emerald-500/40 transition-colors"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              />
            </div>

            {/* Order Type */}
            <div className="mb-6">
              <label className="block text-[11px] text-zinc-500 tracking-wider mb-1.5 uppercase" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                Order Type
              </label>
              <div className="grid grid-cols-2 gap-2">
                {(["market", "limit"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setOrderType(t)}
                    className={`py-2 rounded-lg text-xs font-medium transition-all border uppercase tracking-wider ${
                      orderType === t
                        ? "bg-indigo-500/20 border-indigo-500/40 text-indigo-400"
                        : "bg-white/[0.03] border-white/[0.06] text-zinc-500 hover:text-zinc-300"
                    }`}
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

            {error && (
              <div className="mb-4 px-3 py-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex items-center gap-2">
                <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                {error}
              </div>
            )}

            {/* Execute Button */}
            <button
              onClick={handleExecute}
              disabled={executing || (tradeMode === "live" && connectedBrokers.length === 0)}
              className={`w-full py-3 rounded-xl font-semibold text-sm transition-all flex items-center justify-center gap-2 ${
                side === "LONG"
                  ? "bg-emerald-500 hover:bg-emerald-400 text-black disabled:opacity-50"
                  : "bg-red-500 hover:bg-red-400 text-white disabled:opacity-50"
              }`}
              style={{ fontFamily: "Outfit, sans-serif" }}
            >
              {executing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Executing...
                </>
              ) : (
                <>
                  <ArrowUpDown className="w-4 h-4" />
                  {side === "LONG" ? "Buy / Long" : "Sell / Short"} {symbol}
                </>
              )}
            </button>
          </div>
        ) : (
          // Trade confirmation view
          <div className="p-6">
            {/* Mode Badge */}
            <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold mb-4 ${
              result.mode === "live"
                ? "bg-green-500/20 text-green-400 border border-green-500/50"
                : "bg-yellow-500/20 text-yellow-400 border border-yellow-500/50"
            }`} style={{ fontFamily: "JetBrains Mono, monospace" }}>
              {result.mode === "live" ? "\u25CF LIVE TRADE" : "\u25D0 PAPER TRADE"}
            </div>

            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-white" style={{ fontFamily: "Outfit, sans-serif" }}>
                    Order Filled
                  </h2>
                  <p className="text-[11px] text-emerald-400/70 tracking-wider" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                    {result.mode === "paper" ? <span className="text-yellow-400/70">SIM-</span> : ""}{result.orderId}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-zinc-600" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                  closing in {countdown}s
                </span>
                <button
                  onClick={onClose}
                  className="w-8 h-8 rounded-lg bg-white/[0.04] flex items-center justify-center hover:bg-white/[0.08] transition-colors text-zinc-500 hover:text-zinc-300"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
            {/* Note: Switching to Activity Log tab */}
            <div className="mb-4 px-3 py-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center gap-2">
              <Brain className="w-3.5 h-3.5 text-indigo-400 flex-shrink-0" />
              <span className="text-[11px] text-indigo-300">Full reasoning log saved to <strong>Activity</strong> tab — auto-opens when this closes.</span>
            </div>

            {/* Key stats */}
            <div className="grid grid-cols-2 gap-2 mb-4">
              {[
                { label: "Symbol", value: result.symbol },
                { label: "Side", value: result.side, color: result.side === "LONG" ? "text-emerald-400" : "text-red-400" },
                { label: result.mode === "paper" ? "Price (Sim)" : "Fill Price", value: result.executionPrice?.toFixed(4) },
                { label: "Quantity", value: result.quantity?.toString() },
                { label: "Stop Loss", value: result.stopLoss?.toFixed(4), color: "text-red-400" },
                { label: "Take Profit", value: result.takeProfit?.toFixed(4), color: "text-emerald-400" },
                { label: "Risk/Reward", value: `1:${result.riskReward}` },
                { label: "Confidence", value: `${result.confidence}%`, color: (result.confidence ?? 0) >= 80 ? "text-emerald-400" : "text-amber-400" },
              ].map(({ label, value, color }) => (
                <div key={label} className="bg-white/[0.03] rounded-lg px-3 py-2">
                  <div className="text-[10px] text-zinc-600 tracking-wider uppercase mb-0.5" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                    {label}
                  </div>
                  <div className={`text-sm font-semibold ${color || "text-white"}`} style={{ fontFamily: "JetBrains Mono, monospace" }}>
                    {value}
                  </div>
                </div>
              ))}
            </div>

            {/* Reasoning + Signals */}
            <div className="space-y-2 mb-4 max-h-[40vh] overflow-y-auto pr-1">
              {result.reasoning && (
                <div className="bg-white/[0.02] border border-indigo-500/20 rounded-lg p-3">
                  <div className="text-[10px] text-indigo-400 tracking-wider uppercase mb-1.5 flex items-center gap-1.5" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                    <Brain className="w-3 h-3" /> AI Reasoning
                  </div>
                  <p className="text-xs text-zinc-300 leading-relaxed">{result.reasoning}</p>
                </div>
              )}
              {result.technicalSignals && (
                <div className="bg-white/[0.02] border border-emerald-500/20 rounded-lg p-3">
                  <div className="text-[10px] text-emerald-400 tracking-wider uppercase mb-1.5 flex items-center gap-1.5" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                    <BarChart3 className="w-3 h-3" /> Technical Signals
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">{result.technicalSignals}</p>
                </div>
              )}
              {result.sentimentSignals && (
                <div className="bg-white/[0.02] border border-amber-500/20 rounded-lg p-3">
                  <div className="text-[10px] text-amber-400 tracking-wider uppercase mb-1.5 flex items-center gap-1.5" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                    <Zap className="w-3 h-3" /> Sentiment Analysis
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">{result.sentimentSignals}</p>
                </div>
              )}
              {result.riskAssessment && (
                <div className="bg-white/[0.02] border border-red-500/20 rounded-lg p-3">
                  <div className="text-[10px] text-red-400 tracking-wider uppercase mb-1.5 flex items-center gap-1.5" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                    <Shield className="w-3 h-3" /> Risk Assessment
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">{result.riskAssessment}</p>
                </div>
              )}
            </div>

            {/* Strategy + Tier */}
            <div className="flex items-center gap-2 mb-4">
              <span className="px-2 py-1 rounded-md bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-[11px]" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                {result.strategy}
              </span>
              <span className={`px-2 py-1 rounded-md text-[11px] font-bold ${
                result.tier === "A+" ? "bg-amber-500/10 border border-amber-500/20 text-amber-400" :
                result.tier === "A" ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-400" :
                "bg-indigo-500/10 border border-indigo-500/20 text-indigo-400"
              }`} style={{ fontFamily: "JetBrains Mono, monospace" }}>
                Tier {result.tier}
              </span>
              <span className="ml-auto text-[11px] text-zinc-500" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                via {result.broker ?? "unknown"}
              </span>
            </div>

            <button
              onClick={onClose}
              className="w-full py-2.5 rounded-xl bg-white/[0.05] hover:bg-white/[0.08] text-zinc-300 text-sm font-medium transition-colors"
              style={{ fontFamily: "Outfit, sans-serif" }}
            >
              Close
            </button>
          </div>
        )}
      </motion.div>
    </div>
  );
}
