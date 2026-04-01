"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Activity,
  Radio,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { fmt } from "@/components/trading/trading-utils";

// ─── Sub-components ──────────────────────────────────────────

function OpenPositionRow({ trade }: { trade: Record<string, unknown> }) {
  return (
    <div className="flex items-center justify-between py-2.5 px-3 rounded-lg bg-emerald-500/[0.03] border border-emerald-500/10">
      <div className="flex items-center gap-4">
        <div
          className="w-1.5 h-1.5 rounded-full bg-emerald-400"
          style={{ animation: "pulse-glow 2s ease-in-out infinite" }}
        />
        <span className="text-xs font-medium text-zinc-200">
          {trade.asset as string}
        </span>
        <span
          className={`text-[10px] font-medium ${
            trade.side === "LONG" ? "text-emerald-400" : "text-red-400"
          }`}
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {trade.side as string}
        </span>
      </div>
      <div
        className="flex items-center gap-4 text-[11px]"
        style={{ fontFamily: "JetBrains Mono, monospace" }}
      >
        <span className="text-zinc-500">
          Entry: {Number(trade.entry_price ?? 0).toFixed(2)}
        </span>
        <span className="text-zinc-500">
          Conf: {Number(trade.confidence ?? 0).toFixed(0)}%
        </span>
        <span className="text-zinc-500">
          SL: {Number(trade.stop_loss ?? 0).toFixed(2)}
        </span>
      </div>
    </div>
  );
}

function TradeRow({
  trade,
  expanded,
  onToggle,
}: {
  trade: Record<string, unknown>;
  expanded: boolean;
  onToggle: () => void;
}) {
  const pnl = Number(trade.pnl ?? 0);
  const isWin = pnl > 0;

  return (
    <div>
      <button
        onClick={onToggle}
        className="w-full grid grid-cols-[1fr_80px_80px_100px_80px_80px_60px] gap-2 px-3 py-2.5 rounded-lg hover:bg-white/[0.02] transition-colors items-center text-left"
      >
        <span className="text-xs font-medium text-zinc-200">
          {trade.asset as string}
        </span>
        <span
          className={`text-[11px] font-medium ${
            trade.side === "LONG" ? "text-emerald-400" : "text-red-400"
          }`}
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {trade.side as string}
        </span>
        <span
          className="text-[10px] text-zinc-500 truncate"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {((trade.strategy as string) || "").slice(0, 8)}
        </span>
        <span
          className="text-[11px] text-zinc-400 text-right"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {Number(trade.entry_price ?? 0).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          })}
        </span>
        <span
          className={`text-[11px] font-medium text-right ${
            isWin ? "text-emerald-400" : "text-red-400"
          }`}
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {isWin ? "+" : ""}
          {fmt(pnl)}
        </span>
        <span
          className="text-[11px] text-zinc-500 text-right"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {Number(trade.confidence ?? 0).toFixed(0)}%
        </span>
        <span className="text-zinc-600 flex justify-end">
          {expanded ? (
            <ChevronUp className="w-3.5 h-3.5" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5" />
          )}
        </span>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={false}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-3 pt-1 space-y-2">
              {!!trade.reasoning && (
                <div className="bg-white/[0.02] rounded-lg p-3">
                  <div
                    className="text-[10px] text-zinc-600 uppercase tracking-wider mb-1"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    Entry Reasoning
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    {trade.reasoning as string}
                  </p>
                </div>
              )}
              {!!trade.exit_reason && (
                <div className="bg-white/[0.02] rounded-lg p-3">
                  <div
                    className="text-[10px] text-zinc-600 uppercase tracking-wider mb-1"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    Exit Reasoning
                  </div>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    {trade.exit_reason as string}
                  </p>
                </div>
              )}
              <div
                className="flex gap-4 text-[10px] text-zinc-600"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                <span>
                  TIER: {(trade.tier as string) || "—"}
                </span>
                <span>
                  STOP: {Number(trade.stop_loss ?? 0).toFixed(2)}
                </span>
                <span>
                  TP: {Number(trade.take_profit ?? 0).toFixed(2)}
                </span>
                <span>
                  FEES: ${Number(trade.fees || 0).toFixed(2)}
                </span>
                <span>
                  EXIT: {Number(trade.exit_price || 0).toFixed(2)}
                </span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── TradesTab ───────────────────────────────────────────────

export function TradesTab({
  trades,
  openPositions,
  expandedTrade,
  setExpandedTrade,
}: {
  trades: Record<string, unknown>[];
  openPositions: Record<string, unknown>[];
  expandedTrade: number | null;
  setExpandedTrade: (id: number | null) => void;
}) {
  return (
    <motion.div
      initial={false}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.3 }}
      className="space-y-6 pb-12"
    >
      {/* Open Positions */}
      {openPositions.length > 0 && (
        <div className="card-glass rounded-2xl p-5">
          <h3 className="text-sm font-semibold text-zinc-300 mb-4 flex items-center gap-2">
            <Radio className="w-4 h-4 text-emerald-400" />
            Open Positions
            <span className="ml-auto text-xs text-emerald-400/60 bg-emerald-400/10 px-2 py-0.5 rounded-full">
              {openPositions.length} active
            </span>
          </h3>
          <div className="space-y-2">
            {openPositions.map((t, i) => (
              <OpenPositionRow key={i} trade={t} />
            ))}
          </div>
        </div>
      )}

      {/* Recent Trades */}
      <div className="card-glass rounded-2xl p-5">
        <h3 className="text-sm font-semibold text-zinc-300 mb-4 flex items-center gap-2">
          <Activity className="w-4 h-4 text-zinc-500" />
          Recent Trades
          <span className="text-[9px] px-1.5 py-0.5 rounded-full font-bold bg-yellow-500/15 text-yellow-400 border border-yellow-500/30" style={{ fontFamily: "JetBrains Mono, monospace" }}>
            PAPER / BACKTEST
          </span>
          <span className="ml-auto text-xs text-zinc-500">
            Last {trades.filter((t) => t.pnl !== null).length} closed
          </span>
        </h3>

        {/* Table header */}
        <div
          className="grid grid-cols-[1fr_80px_80px_100px_80px_80px_60px] gap-2 px-3 py-2 text-[10px] text-zinc-600 uppercase tracking-wider border-b border-white/[0.04]"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          <span>Asset</span>
          <span>Side</span>
          <span>Strategy</span>
          <span className="text-right">Entry</span>
          <span className="text-right">P&L</span>
          <span className="text-right">Conf</span>
          <span></span>
        </div>

        <div className="space-y-0.5 mt-1">
          {trades
            .filter((t) => t.pnl !== null)
            .map((t, i) => (
              <TradeRow
                key={i}
                trade={t}
                expanded={expandedTrade === i}
                onToggle={() =>
                  setExpandedTrade(expandedTrade === i ? null : i)
                }
              />
            ))}
        </div>
      </div>
    </motion.div>
  );
}
