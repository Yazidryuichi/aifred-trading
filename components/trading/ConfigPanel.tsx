"use client";

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Settings2, Cpu, Building2, Bot, Plus, ChevronLeft } from "lucide-react";
import { useRouter } from "next/navigation";
import { ModelCard } from "@/components/trading/config/ModelCard";
import { ExchangeCard } from "@/components/trading/config/ExchangeCard";
import { TraderCard } from "@/components/trading/config/TraderCard";
import { AddModelModal } from "@/components/trading/config/AddModelModal";
import { AddTraderModal } from "@/components/trading/config/AddTraderModal";

// ─── Hardcoded data ──────────────────────────────────────────

const AI_MODELS = [
  { name: "Claude AI", modelId: "claude-opus-4-6", provider: "Meta-reasoning", enabled: true, avatar: "🧠" },
  { name: "GPT", modelId: "gpt-4-turbo", provider: "Signal validation", enabled: true, avatar: "⚡" },
  { name: "FinBERT", modelId: "finbert-tone", provider: "Sentiment", enabled: true, avatar: "📰" },
  { name: "LSTM Ensemble", modelId: "custom-v2.0", provider: "Price prediction", enabled: true, avatar: "📈" },
  { name: "XGBoost", modelId: "xgboost-v1.7", provider: "Feature importance", enabled: true, avatar: "🎯" },
  { name: "Transformer", modelId: "custom-attn-v2", provider: "Pattern recognition", enabled: true, avatar: "🔍" },
  { name: "HMM", modelId: "hmm-regime-v3", provider: "Regime detection", enabled: true, avatar: "📊" },
];

const EXCHANGES = [
  { name: "HYPERLIQUID", id: "hyperliquid", type: "DEX" as const, connected: true },
  { name: "BINANCE", id: "binance", type: "CEX" as const, connected: false },
  { name: "ALPACA", id: "alpaca", type: "CEX" as const, connected: false },
  { name: "OANDA", id: "oanda", type: "CEX" as const, connected: false },
  { name: "COINBASE", id: "coinbase", type: "CEX" as const, connected: false },
];

interface Trader {
  id: string;
  name: string;
  model: string;
  exchange: string;
  status: "running" | "stopped" | "error";
}

const DEFAULT_TRADERS: Trader[] = [
  {
    id: "aifred-main",
    name: "aifred-main",
    model: "Claude AI",
    exchange: "HYPERLIQUID",
    status: "running",
  },
];

// ─── ConfigPanel Component ───────────────────────────────────

export default function ConfigPanel() {
  const router = useRouter();
  const [showModelModal, setShowModelModal] = useState(false);
  const [showTraderModal, setShowTraderModal] = useState(false);
  const [traders, setTraders] = useState(DEFAULT_TRADERS);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  const activeCount = traders.filter((t) => t.status === "running").length;

  const handleView = useCallback(() => {
    router.push("/trading");
  }, [router]);

  const handleEdit = useCallback(() => {
    // Placeholder — future modal
  }, []);

  const handleStop = useCallback((traderId: string) => {
    setTraders((prev) =>
      prev.map((t) =>
        t.id === traderId
          ? { ...t, status: (t.status === "running" ? "stopped" : "running") as "running" | "stopped" }
          : t
      )
    );
  }, []);

  const handleDelete = useCallback((traderId: string) => {
    if (deleteConfirm === traderId) {
      setTraders((prev) => prev.filter((t) => t.id !== traderId));
      setDeleteConfirm(null);
    } else {
      setDeleteConfirm(traderId);
      // Auto-clear confirmation after 3s
      setTimeout(() => setDeleteConfirm(null), 3000);
    }
  }, [deleteConfirm]);

  return (
    <div
      className="min-h-screen bg-[#06060a] text-white relative overflow-hidden"
      style={{ fontFamily: "Outfit, sans-serif" }}
    >
      {/* Ambient glow */}
      <div className="fixed inset-0 pointer-events-none">
        <div
          className="absolute top-0 left-1/4 w-[600px] h-[600px] rounded-full opacity-[0.03]"
          style={{
            background: "radial-gradient(circle, rgba(16,185,129,1) 0%, transparent 70%)",
          }}
        />
        <div
          className="absolute bottom-0 right-1/4 w-[400px] h-[400px] rounded-full opacity-[0.02]"
          style={{
            background: "radial-gradient(circle, rgba(99,102,241,1) 0%, transparent 70%)",
          }}
        />
      </div>

      {/* Content */}
      <div className="relative z-10 max-w-[1400px] mx-auto px-4 md:px-6 py-6">
        {/* Breadcrumb */}
        <button
          onClick={() => router.push("/trading")}
          className="flex items-center gap-1.5 text-zinc-500 hover:text-zinc-300 transition-colors mb-6 group"
        >
          <ChevronLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
          <span
            className="text-xs tracking-wider uppercase"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            Dashboard
          </span>
        </button>

        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-8">
          <div className="flex items-center gap-4">
            <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-emerald-500 to-emerald-700 flex items-center justify-center">
              <Settings2 className="w-6 h-6 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-3">
                <h1
                  className="text-xl md:text-2xl font-bold tracking-tight"
                  style={{ fontFamily: "Outfit, sans-serif" }}
                >
                  AI Traders
                </h1>
                <span
                  className="text-[9px] px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/25 text-emerald-400 font-medium tracking-wider"
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  {activeCount} ACTIVE
                </span>
              </div>
              <p
                className="text-xs text-zinc-500 mt-0.5"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                Manage your AI trading bots
              </p>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowModelModal(true)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white/[0.04] border border-white/[0.06] text-xs text-zinc-400 hover:text-white hover:bg-white/[0.08] hover:border-white/[0.12] transition-all"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              <Plus className="w-3.5 h-3.5" />
              AI Models
            </button>
            <button
              onClick={() => setShowModelModal(true)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white/[0.04] border border-white/[0.06] text-xs text-zinc-400 hover:text-white hover:bg-white/[0.08] hover:border-white/[0.12] transition-all"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              <Plus className="w-3.5 h-3.5" />
              Exchanges
            </button>
            <button
              onClick={() => setShowTraderModal(true)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black text-xs font-bold transition-all shadow-lg shadow-emerald-500/25 active:scale-95"
              style={{ fontFamily: "Outfit, sans-serif" }}
            >
              <Plus className="w-3.5 h-3.5" />
              Create Trader
            </button>
          </div>
        </div>

        {/* Two-column: AI Models + Exchanges */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* AI Models Section */}
          <div>
            <div className="flex items-center gap-2 mb-4">
              <Cpu className="w-4 h-4 text-indigo-400" />
              <h2
                className="text-sm font-semibold text-white tracking-wide"
                style={{ fontFamily: "Outfit, sans-serif" }}
              >
                AI Models
              </h2>
              <span
                className="text-[9px] text-zinc-600 ml-1"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {AI_MODELS.length} configured
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {AI_MODELS.map((model) => (
                <ModelCard key={model.modelId} {...model} />
              ))}
            </div>
          </div>

          {/* Exchanges Section */}
          <div>
            <div className="flex items-center gap-2 mb-4">
              <Building2 className="w-4 h-4 text-blue-400" />
              <h2
                className="text-sm font-semibold text-white tracking-wide"
                style={{ fontFamily: "Outfit, sans-serif" }}
              >
                Exchanges
              </h2>
              <span
                className="text-[9px] text-zinc-600 ml-1"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {EXCHANGES.filter((e) => e.connected).length} connected
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {EXCHANGES.map((exchange) => (
                <ExchangeCard key={exchange.id} {...exchange} />
              ))}
            </div>
          </div>
        </div>

        {/* Divider */}
        <div className="h-px bg-white/[0.06] mb-8" />

        {/* Current Traders Section */}
        <div>
          <div className="flex items-center gap-2 mb-4">
            <Bot className="w-4 h-4 text-emerald-400" />
            <h2
              className="text-sm font-semibold text-white tracking-wide"
              style={{ fontFamily: "Outfit, sans-serif" }}
            >
              Current Traders
            </h2>
            <span
              className="text-[9px] text-zinc-600 ml-1"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              {traders.length} trader{traders.length !== 1 ? "s" : ""}
            </span>
          </div>

          {traders.length === 0 ? (
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-8 text-center">
              <Bot className="w-8 h-8 text-zinc-700 mx-auto mb-3" />
              <p className="text-sm text-zinc-500 mb-1" style={{ fontFamily: "Outfit, sans-serif" }}>
                No traders configured
              </p>
              <p className="text-[10px] text-zinc-600 mb-4" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                Create your first AI trading bot to get started
              </p>
              <button
                onClick={() => setShowTraderModal(true)}
                className="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black text-xs font-bold transition-all"
                style={{ fontFamily: "Outfit, sans-serif" }}
              >
                Create Trader
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {traders.map((trader) => (
                <div key={trader.id} className="relative">
                  <TraderCard
                    name={trader.name}
                    model={trader.model}
                    exchange={trader.exchange}
                    status={trader.status}
                    onView={handleView}
                    onEdit={handleEdit}
                    onStop={() => handleStop(trader.id)}
                    onDelete={() => handleDelete(trader.id)}
                  />
                  {/* Delete confirmation overlay */}
                  <AnimatePresence>
                    {deleteConfirm === trader.id && (
                      <motion.div
                        initial={false}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="absolute inset-0 rounded-xl bg-red-500/10 border border-red-500/30 backdrop-blur-sm flex items-center justify-center"
                      >
                        <div className="text-center">
                          <p className="text-xs text-red-400 mb-2" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                            Click delete again to confirm
                          </p>
                          <div className="flex items-center gap-2 justify-center">
                            <button
                              onClick={() => setDeleteConfirm(null)}
                              className="px-3 py-1.5 rounded-lg bg-white/[0.06] border border-white/[0.08] text-[10px] text-zinc-400 hover:text-white transition-all"
                              style={{ fontFamily: "JetBrains Mono, monospace" }}
                            >
                              Cancel
                            </button>
                            <button
                              onClick={() => handleDelete(trader.id)}
                              className="px-3 py-1.5 rounded-lg bg-red-500/20 border border-red-500/30 text-[10px] text-red-400 hover:bg-red-500/30 transition-all"
                              style={{ fontFamily: "JetBrains Mono, monospace" }}
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Modals */}
      <AnimatePresence>
        {showModelModal && <AddModelModal onClose={() => setShowModelModal(false)} />}
      </AnimatePresence>
      <AnimatePresence>
        {showTraderModal && <AddTraderModal onClose={() => setShowTraderModal(false)} />}
      </AnimatePresence>
    </div>
  );
}
