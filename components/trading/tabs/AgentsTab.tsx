"use client";

import { motion } from "framer-motion";
import {
  Brain,
  Layers,
} from "lucide-react";
import { type TradingData } from "@/components/trading/trading-utils";

export function AgentsTab({ data }: { data: TradingData }) {
  const agents = [
    {
      name: "Data Ingestion",
      status: "active",
      desc: "Price feeds, orderbooks, news scraping",
      tech: "ccxt, yfinance, feedparser",
      files: 10,
      lines: 2646,
    },
    {
      name: "Technical Analysis",
      status: "active",
      desc: "LSTM, Transformer, CNN pattern detection",
      tech: "PyTorch, pandas-ta, XGBoost",
      files: 10,
      lines: 3627,
    },
    {
      name: "NLP & Sentiment",
      status: "active",
      desc: "FinBERT, LLM analysis, Fear & Greed",
      tech: "HuggingFace, spaCy, Claude API",
      files: 9,
      lines: 1613,
    },
    {
      name: "Risk Management",
      status: "active",
      desc: "Kelly sizing, ATR stops, drawdown protection",
      tech: "numpy, scipy, empyrical",
      files: 9,
      lines: 1750,
    },
    {
      name: "Execution",
      status: "active",
      desc: "Multi-exchange, smart order routing",
      tech: "ccxt, alpaca-trade-api",
      files: 7,
      lines: 1546,
    },
    {
      name: "Monitoring",
      status: "active",
      desc: "Trade logging, alerts, dashboards",
      tech: "Streamlit, Telegram",
      files: 7,
      lines: 1361,
    },
    {
      name: "Orchestrator",
      status: "active",
      desc: "Central coordinator, signal fusion",
      tech: "Custom Python",
      files: 2,
      lines: 1304,
    },
  ];

  return (
    <motion.div
      initial={false}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.3 }}
      className="space-y-4 pb-12"
    >
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents.map((agent, i) => (
          <motion.div
            key={agent.name}
            initial={false}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06 }}
            className="card-glass rounded-2xl p-5 group"
          >
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="text-sm font-semibold text-zinc-200">
                  {agent.name}
                </h3>
                <p className="text-xs text-zinc-500 mt-0.5">{agent.desc}</p>
              </div>
              <div className="flex items-center gap-1.5">
                <div
                  className="w-1.5 h-1.5 rounded-full bg-emerald-400"
                  style={{ animation: "pulse-glow 2s ease-in-out infinite" }}
                />
                <span
                  className="text-[10px] text-emerald-400/70 uppercase tracking-wider"
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  online
                </span>
              </div>
            </div>

            <div className="flex items-center gap-3 mt-4">
              <span
                className="text-[10px] text-zinc-600 bg-white/[0.03] px-2 py-1 rounded"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {agent.tech}
              </span>
            </div>

            <div
              className="flex items-center gap-4 mt-3 text-[10px] text-zinc-600"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              <span>{agent.files} files</span>
              <span>{agent.lines.toLocaleString()} lines</span>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Self-Improvement Cycle */}
      <div className="card-glass rounded-2xl p-5 border border-indigo-500/10">
        <h3 className="text-sm font-semibold text-zinc-300 mb-4 flex items-center gap-2">
          <Brain className="w-4 h-4 text-indigo-400" />
          Continuous Learning Pipeline
        </h3>
        <div className="grid md:grid-cols-4 gap-3 mb-4">
          {[
            { step: "1", label: "Analyze", desc: "7 agents scan markets using LSTM, Transformer, CNN + FinBERT sentiment", color: "text-emerald-400", border: "border-emerald-500/20" },
            { step: "2", label: "Execute", desc: "Signals fused with 60/40 tech/sentiment weighting, risk-gated, and routed to broker", color: "text-amber-400", border: "border-amber-500/20" },
            { step: "3", label: "Evaluate", desc: "Every trade outcome tracked — P&L, slippage, fill quality, prediction accuracy", color: "text-indigo-400", border: "border-indigo-500/20" },
            { step: "4", label: "Improve", desc: "Walk-forward validation retrains models, Bayesian optimizer tunes parameters daily", color: "text-purple-400", border: "border-purple-500/20" },
          ].map((item) => (
            <div key={item.step} className={`bg-white/[0.02] rounded-xl p-4 border ${item.border}`}>
              <div className="flex items-center gap-2 mb-2">
                <span className={`text-lg font-bold ${item.color}`} style={{ fontFamily: "JetBrains Mono, monospace" }}>{item.step}</span>
                <span className="text-xs font-semibold text-zinc-200">{item.label}</span>
              </div>
              <p className="text-[10px] text-zinc-500 leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-indigo-500/5 border border-indigo-500/10">
          <Layers className="w-3.5 h-3.5 text-indigo-400 flex-shrink-0" />
          <p className="text-[10px] text-indigo-300/80">
            Models retrain every 12 hours via automated pipeline. Walk-forward validation prevents overfitting. Ensemble weights adapt based on per-model accuracy.
          </p>
        </div>
      </div>

      {/* System stats */}
      <div className="card-glass rounded-2xl p-5">
        <h3 className="text-sm font-semibold text-zinc-300 mb-4">
          System Architecture
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="text-center">
            <div
              className="text-2xl font-bold text-emerald-400 glow-green"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              7
            </div>
            <div className="text-[10px] text-zinc-500 mt-1 uppercase tracking-wider">
              Active Agents
            </div>
          </div>
          <div className="text-center">
            <div
              className="text-2xl font-bold text-amber-400 glow-gold"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              61
            </div>
            <div className="text-[10px] text-zinc-500 mt-1 uppercase tracking-wider">
              Python Modules
            </div>
          </div>
          <div className="text-center">
            <div
              className="text-2xl font-bold text-indigo-400"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              18.8K
            </div>
            <div className="text-[10px] text-zinc-500 mt-1 uppercase tracking-wider">
              Lines of Code
            </div>
          </div>
          <div className="text-center">
            <div
              className="text-2xl font-bold text-zinc-300"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              5
            </div>
            <div className="text-[10px] text-zinc-500 mt-1 uppercase tracking-wider">
              ML Models
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
