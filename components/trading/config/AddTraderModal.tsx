"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { X, Bot, Info } from "lucide-react";

interface AddTraderModalProps {
  onClose: () => void;
}

const aiModels = [
  "Claude AI (claude-opus-4-6)",
  "GPT (gpt-4-turbo)",
  "FinBERT (finbert-tone)",
  "LSTM Ensemble (custom-v2.0)",
  "XGBoost (xgboost-v1.7)",
  "Transformer (custom-attn-v2)",
  "HMM (hmm-regime-v3)",
];

const exchanges = [
  "HYPERLIQUID (DEX)",
  "BINANCE (CEX)",
  "ALPACA (CEX)",
  "OANDA (CEX)",
  "COINBASE (CEX)",
];

const strategies = [
  "Multi-Agent Fusion",
  "Momentum",
  "Mean Reversion",
  "Regime-Adaptive",
  "Trend Following",
];

export function AddTraderModal({ onClose }: AddTraderModalProps) {
  const [traderName, setTraderName] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [selectedExchange, setSelectedExchange] = useState("");
  const [selectedStrategy, setSelectedStrategy] = useState("");

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-trader-title"
    >
      {/* Backdrop */}
      <motion.div
        initial={false}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <motion.div
        initial={false}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="relative w-full max-w-md rounded-2xl border border-white/[0.08] p-6"
        style={{
          background: "linear-gradient(135deg, rgba(15,15,20,0.98) 0%, rgba(10,10,15,0.98) 100%)",
          backdropFilter: "blur(20px)",
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-emerald-500/15 border border-emerald-500/25 flex items-center justify-center">
              <Bot className="w-4 h-4 text-emerald-400" />
            </div>
            <div>
              <h2
                id="add-trader-title"
                className="text-base font-bold text-white"
                style={{ fontFamily: "Outfit, sans-serif" }}
              >
                Create Trader
              </h2>
              <p className="text-[10px] text-zinc-500" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                Configure a new AI trading bot
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg bg-white/[0.04] border border-white/[0.06] flex items-center justify-center text-zinc-500 hover:text-white hover:bg-white/[0.08] transition-all"
            aria-label="Close modal"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form fields */}
        <div className="space-y-4">
          {/* Trader Name */}
          <div>
            <label
              className="block text-[10px] text-zinc-500 tracking-wider uppercase mb-1.5"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              Trader Name
            </label>
            <input
              type="text"
              value={traderName}
              onChange={(e) => setTraderName(e.target.value)}
              placeholder="e.g. aifred-btc-scalper"
              className="w-full px-3 py-2.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-emerald-500/40 transition-colors"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            />
          </div>

          {/* AI Model */}
          <div>
            <label
              className="block text-[10px] text-zinc-500 tracking-wider uppercase mb-1.5"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              AI Model
            </label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="w-full px-3 py-2.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-sm text-white focus:outline-none focus:border-emerald-500/40 transition-colors appearance-none"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              <option value="" className="bg-zinc-900">Select AI model...</option>
              {aiModels.map((m) => (
                <option key={m} value={m} className="bg-zinc-900">
                  {m}
                </option>
              ))}
            </select>
          </div>

          {/* Exchange */}
          <div>
            <label
              className="block text-[10px] text-zinc-500 tracking-wider uppercase mb-1.5"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              Exchange
            </label>
            <select
              value={selectedExchange}
              onChange={(e) => setSelectedExchange(e.target.value)}
              className="w-full px-3 py-2.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-sm text-white focus:outline-none focus:border-emerald-500/40 transition-colors appearance-none"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              <option value="" className="bg-zinc-900">Select exchange...</option>
              {exchanges.map((e) => (
                <option key={e} value={e} className="bg-zinc-900">
                  {e}
                </option>
              ))}
            </select>
          </div>

          {/* Strategy */}
          <div>
            <label
              className="block text-[10px] text-zinc-500 tracking-wider uppercase mb-1.5"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              Strategy
            </label>
            <select
              value={selectedStrategy}
              onChange={(e) => setSelectedStrategy(e.target.value)}
              className="w-full px-3 py-2.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-sm text-white focus:outline-none focus:border-emerald-500/40 transition-colors appearance-none"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              <option value="" className="bg-zinc-900">Select strategy...</option>
              {strategies.map((s) => (
                <option key={s} value={s} className="bg-zinc-900">
                  {s}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Coming soon notice */}
        <div className="mt-5 p-3 rounded-lg bg-amber-500/[0.06] border border-amber-500/15 flex items-start gap-2">
          <Info className="w-3.5 h-3.5 text-amber-400 mt-0.5 flex-shrink-0" />
          <p
            className="text-[10px] text-amber-400/80 leading-relaxed"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            Coming soon — multi-trader support requires backend integration. Trader creation will be available in a future update.
          </p>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3 mt-5">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-xs text-zinc-400 hover:text-white hover:bg-white/[0.08] transition-all font-medium"
            style={{ fontFamily: "Outfit, sans-serif" }}
          >
            Cancel
          </button>
          <button
            disabled
            className="flex-1 px-4 py-2.5 rounded-lg bg-emerald-500/20 border border-emerald-500/20 text-xs text-emerald-400/50 font-medium cursor-not-allowed"
            style={{ fontFamily: "Outfit, sans-serif" }}
          >
            Create Trader
          </button>
        </div>
      </motion.div>
    </div>
  );
}
