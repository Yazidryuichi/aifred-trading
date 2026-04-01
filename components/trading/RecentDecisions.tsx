"use client";

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { Brain, ChevronDown, Loader2, AlertCircle, RefreshCw } from "lucide-react";
import { DecisionCard, type Decision } from "./DecisionCard";

// ─── Mock data for development (remove when API is live) ────
const MOCK_DECISIONS: Decision[] = [
  {
    id: "d-001",
    cycleNumber: 42,
    timestamp: new Date(Date.now() - 5 * 60_000).toISOString(),
    status: "success",
    inputPrompt:
      "Analyze BTCUSDT, ETHUSDT, SOLUSDT on 15m timeframe. Current portfolio: $10.80 USDC. Consider RSI, MACD, Bollinger Bands. Market regime: consolidation.",
    chainOfThought:
      "Market Analysis:\n- BTC consolidating near $84,200, RSI 52.3 (neutral)\n- ETH showing slight weakness, RSI 48.1\n- SOL momentum positive, RSI 58.7, MACD bullish crossover\n\nRisk Assessment:\n- Portfolio size too small for meaningful positions\n- Spread costs would eat ~0.5% per round trip\n- Kelly criterion suggests minimal sizing\n\nDecision:\n- Hold all positions. Portfolio too small for favorable risk/reward on any setup.",
    assetDecisions: [
      { asset: "BTCUSDT", action: "hold", succeeded: true },
      { asset: "ETHUSDT", action: "hold", succeeded: true },
      { asset: "SOLUSDT", action: "hold", succeeded: true },
    ],
    durationMs: 12500,
    agents: {
      technical:
        "RSI neutral (52.3), MACD flat, BB squeeze forming. No clear directional signal.",
      sentiment:
        'FinBERT: neutral (0.51), social sentiment: slightly positive. "Consolidation before next move" narrative dominant.',
      risk: "Kelly size: 0.0% (no edge detected). ATR stop would be $83,800. R:R insufficient at current spread.",
      regime: "Consolidation (74% confidence). Low volatility regime detected via HMM.",
    },
  },
  {
    id: "d-002",
    cycleNumber: 41,
    timestamp: new Date(Date.now() - 20 * 60_000).toISOString(),
    status: "success",
    chainOfThought:
      "Market Analysis:\n- All assets in tight ranges\n- No significant volume spikes\n- Funding rates neutral across monitored pairs\n\nDecision: Hold. Waiting for volatility expansion.",
    assetDecisions: [
      { asset: "BTCUSDT", action: "hold", succeeded: true },
      { asset: "ETHUSDT", action: "hold", succeeded: true },
    ],
    durationMs: 8200,
    agents: {
      technical: "No signals above threshold. All indicators neutral.",
      regime: "Consolidation (81% confidence).",
    },
  },
  {
    id: "d-003",
    cycleNumber: 40,
    timestamp: new Date(Date.now() - 35 * 60_000).toISOString(),
    status: "partial",
    chainOfThought:
      "Market Analysis:\n- BTC showing bullish divergence on RSI\n- ETH lagging, potential weakness\n- SOL strong relative performance\n\nAttempted small SOL long but slippage exceeded threshold.\n\nDecision: SOL buy signal generated but execution failed due to insufficient margin.",
    assetDecisions: [
      { asset: "BTCUSDT", action: "hold", succeeded: true },
      { asset: "ETHUSDT", action: "hold", succeeded: true },
      { asset: "SOLUSDT", action: "buy", succeeded: false },
    ],
    durationMs: 15800,
    agents: {
      technical:
        "RSI bullish divergence on SOL (15m). MACD about to cross bullish. Bollinger Band squeeze breakout imminent.",
      sentiment: "FinBERT: bullish (0.72) on SOL. Social volume spike detected.",
      risk: "Kelly size: 2.1%. ATR stop: $134.20. R:R 2.3:1. Approved with minimum size.",
      regime: "Early Bull (62% confidence). Transition from consolidation detected.",
    },
  },
  {
    id: "d-004",
    cycleNumber: 39,
    timestamp: new Date(Date.now() - 50 * 60_000).toISOString(),
    status: "success",
    chainOfThought:
      "Routine scan. All indicators neutral. No actionable setups detected. Portfolio preservation mode.",
    assetDecisions: [
      { asset: "BTCUSDT", action: "hold", succeeded: true },
      { asset: "ETHUSDT", action: "hold", succeeded: true },
    ],
    durationMs: 6100,
  },
  {
    id: "d-005",
    cycleNumber: 38,
    timestamp: new Date(Date.now() - 65 * 60_000).toISOString(),
    status: "failure",
    chainOfThought:
      "API timeout during market data fetch. Unable to complete analysis cycle. Defaulting to hold all positions.\n\nError: Hyperliquid API responded with 503 after 30s timeout.",
    assetDecisions: [
      { asset: "BTCUSDT", action: "hold", succeeded: true },
      { asset: "ETHUSDT", action: "hold", succeeded: true },
    ],
    durationMs: 30200,
  },
];

// ─── Count options ──────────────────────────────────────────
const COUNT_OPTIONS = [5, 10, 25] as const;

// ─── Component ──────────────────────────────────────────────
export function RecentDecisions() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [count, setCount] = useState<(typeof COUNT_OPTIONS)[number]>(5);
  const [countOpen, setCountOpen] = useState(false);

  const fetchDecisions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/trading/decisions?limit=${count}`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data?.decisions) && data.decisions.length > 0) {
          setDecisions(data.decisions);
        } else {
          // Fallback to mock data during development
          setDecisions(MOCK_DECISIONS.slice(0, count));
        }
      } else {
        // API not yet built — use mock data
        setDecisions(MOCK_DECISIONS.slice(0, count));
      }
    } catch {
      // API not yet built — use mock data
      setDecisions(MOCK_DECISIONS.slice(0, count));
    } finally {
      setLoading(false);
    }
  }, [count]);

  useEffect(() => {
    fetchDecisions();
    const interval = setInterval(fetchDecisions, 30_000);
    return () => clearInterval(interval);
  }, [fetchDecisions]);

  return (
    <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4 h-full flex flex-col">
      {/* ── Header ─────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3
            className="text-sm font-semibold text-zinc-300 flex items-center gap-2"
            style={{ fontFamily: "Outfit, sans-serif" }}
          >
            <Brain className="w-4 h-4 text-purple-400" />
            Recent Decisions
          </h3>
          <p
            className="text-[10px] text-zinc-600 mt-0.5"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            Last {count} trading cycles
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Refresh */}
          <button
            onClick={fetchDecisions}
            className="text-zinc-600 hover:text-zinc-300 transition-colors p-1"
            title="Refresh decisions"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>

          {/* Count selector */}
          <div className="relative">
            <button
              onClick={() => setCountOpen((v) => !v)}
              className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors border border-white/[0.06] rounded-lg px-2 py-1"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              {count}
              <ChevronDown className="w-3 h-3" />
            </button>
            {countOpen && (
              <div className="absolute right-0 top-full mt-1 bg-zinc-900 border border-white/10 rounded-lg overflow-hidden z-10 shadow-xl">
                {COUNT_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    onClick={() => {
                      setCount(opt);
                      setCountOpen(false);
                    }}
                    className={`block w-full text-left px-3 py-1.5 text-[10px] transition-colors ${
                      opt === count
                        ? "text-purple-400 bg-purple-500/10"
                        : "text-zinc-400 hover:text-zinc-200 hover:bg-white/5"
                    }`}
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {opt} cycles
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Content ────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto space-y-2 min-h-0 scrollbar-thin">
        {loading ? (
          <DecisionsSkeleton count={3} />
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 py-8">
            <AlertCircle className="w-5 h-5 text-red-400" />
            <p className="text-[11px] text-red-400">{error}</p>
            <button
              onClick={fetchDecisions}
              className="text-[10px] text-zinc-500 hover:text-zinc-300 underline"
            >
              Retry
            </button>
          </div>
        ) : decisions.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 py-8">
            <Brain className="w-5 h-5 text-zinc-600" />
            <p className="text-[11px] text-zinc-600">
              No decisions yet. Waiting for first trading cycle.
            </p>
          </div>
        ) : (
          decisions.map((d) => <DecisionCard key={d.id} decision={d} />)
        )}
      </div>
    </div>
  );
}

// ─── Loading Skeleton ───────────────────────────────────────
function DecisionsSkeleton({ count }: { count: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <motion.div
          key={i}
          initial={false}
          animate={{ opacity: [0.3, 0.6, 0.3] }}
          transition={{ duration: 1.5, repeat: Infinity, delay: i * 0.15 }}
          className="bg-white/[0.02] border border-white/[0.04] rounded-xl p-4 space-y-3"
        >
          <div className="flex items-center justify-between">
            <div className="h-3 w-20 bg-zinc-800 rounded" />
            <div className="h-4 w-14 bg-zinc-800 rounded-full" />
          </div>
          <div className="space-y-1.5">
            <div className="h-2.5 w-full bg-zinc-800/60 rounded" />
            <div className="h-2.5 w-3/4 bg-zinc-800/60 rounded" />
          </div>
          <div className="flex gap-2">
            <div className="h-5 w-24 bg-zinc-800/40 rounded" />
            <div className="h-5 w-24 bg-zinc-800/40 rounded" />
          </div>
        </motion.div>
      ))}
    </>
  );
}
