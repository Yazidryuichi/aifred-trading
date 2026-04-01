"use client";

import { useEffect, useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  TrendingUp,
  Activity,
  Shield,
  Zap,
  Brain,
  AlertTriangle,
  BarChart3,
  ChevronDown,
  ChevronUp,
  ArrowUpDown,
  CheckCircle2,
} from "lucide-react";
import {
  type ActivityEntry,
  timeAgo,
  getEntryMode,
  STRATEGY_LABELS,
  TIER_COLORS,
  ACTIVITY_TYPE_CONFIG,
} from "@/components/trading/trading-utils";

export function ActivityTab() {
  const [activities, setActivities] = useState<ActivityEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filterMode, setFilterMode] = useState<"all" | "live" | "paper">("all");

  const mergeWithLocal = (serverList: ActivityEntry[]): ActivityEntry[] => {
    try {
      const localTrades: ActivityEntry[] = JSON.parse(
        localStorage.getItem("aifred_local_trades") || "[]"
      );
      // Sanitize entries — ensure title/message are strings, not objects
      const sanitize = (e: ActivityEntry): ActivityEntry => {
        const raw = e as unknown as Record<string, unknown>;
        return {
          ...e,
          id: (typeof raw.id === "string" ? raw.id : null) || `gen_${Math.random().toString(36).slice(2, 8)}`,
          title: typeof raw.title === "string" ? raw.title : (typeof raw.asset === "string" ? raw.asset : "Trade"),
          message: typeof raw.message === "string" ? raw.message : (typeof raw.title === "string" ? raw.title : (typeof raw.asset === "string" ? raw.asset : "Trade executed")),
          type: (typeof raw.type === "string" ? raw.type : null) || "trade_executed",
          severity: (typeof raw.severity === "string" ? raw.severity : null) || "info",
          timestamp: (typeof raw.timestamp === "string" ? raw.timestamp : null) || new Date().toISOString(),
        } as ActivityEntry;
      };
      // Merge: local trades first, then server entries, deduplicate by id
      const merged = [...localTrades.map(sanitize), ...serverList.map(sanitize)];
      const seen = new Set<string>();
      const deduped = merged.filter((e) => {
        if (seen.has(e.id)) return false;
        seen.add(e.id);
        return true;
      });
      // Sort newest first
      deduped.sort(
        (a, b) =>
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      );
      return deduped;
    } catch {
      return serverList;
    }
  };

  const fetchActivities = () => {
    fetch("/api/trading/activity")
      .then((r) => r.json())
      .then((data) => {
        const serverList = Array.isArray(data) ? data : (data?.activities ?? []);
        const merged = mergeWithLocal(serverList);
        setActivities(merged);
        // Auto-expand the newest trade_executed entry
        const newest = merged.find((e) => e.type === "trade_executed");
        if (newest) setExpandedId((prev) => prev ?? newest.id);
        setLoading(false);
      })
      .catch(() => {
        // Even on server error, show local trades
        const local = mergeWithLocal([]);
        setActivities(local);
        if (local.length > 0) {
          const newest = local.find((e) => e.type === "trade_executed");
          if (newest) setExpandedId((prev) => prev ?? newest.id);
        }
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchActivities();
    const interval = setInterval(fetchActivities, 10_000);
    return () => clearInterval(interval);
  }, []);

  // Separate user-executed trades (from localStorage) for the "Your Trades" section
  // MUST be before any conditional return (React Rules of Hooks)
  const userTrades = useMemo(() => {
    try {
      const local: ActivityEntry[] = JSON.parse(localStorage.getItem("aifred_local_trades") || "[]");
      return local.filter((e) => e.type === "trade_executed").slice(0, 20);
    } catch {
      return [];
    }
  }, [activities]); // re-derive when activities changes

  if (loading) {
    return (
      <motion.div
        initial={false}
        animate={{ opacity: 1 }}
        className="flex items-center justify-center py-20"
      >
        <div className="w-8 h-8 border-2 border-emerald-500/30 border-t-emerald-500 rounded-full animate-spin" />
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={false}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.3 }}
      className="space-y-4 pb-12"
    >
      {/* ─── Your Executed Trades (always visible) ─────────── */}
      <div className="card-glass rounded-2xl p-5" style={{ borderColor: userTrades.length > 0 ? "rgba(16,185,129,0.15)" : undefined }}>
        <h3 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          Your Executed Trades
          <span className="text-[11px] text-emerald-400/70 font-normal">
            {userTrades.length} trades
          </span>
        </h3>

        {/* Mode Filter */}
        {userTrades.length > 0 && (
          <div className="flex gap-2 mb-4">
            {(["all", "live", "paper"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setFilterMode(m)}
                className={`px-3 py-1.5 rounded-lg text-[11px] font-semibold tracking-wider uppercase transition-all ${
                  filterMode === m
                    ? m === "live"
                      ? "bg-green-500/20 text-green-400 border border-green-500/40"
                      : m === "paper"
                      ? "bg-yellow-500/20 text-yellow-400 border border-yellow-500/40"
                      : "bg-white/[0.08] text-white border border-white/[0.12]"
                    : "text-zinc-500 hover:text-zinc-300 border border-transparent"
                }`}
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {m === "all" ? "All" : m === "live" ? "Live Trades" : "Paper Trades"}
              </button>
            ))}
          </div>
        )}

        {userTrades.length === 0 ? (
          <div className="text-center py-8">
            <ArrowUpDown className="w-8 h-8 text-zinc-700 mx-auto mb-3" />
            <p className="text-sm text-zinc-500 mb-1">No trades executed yet</p>
            <p className="text-xs text-zinc-600">
              Click the <span className="text-emerald-400 font-semibold">Execute Trade</span> button above to place your first trade
            </p>
          </div>
        ) : (
          <div className="space-y-2 max-h-[40vh] overflow-y-auto pr-1">
            {userTrades
              .filter((trade) => {
                if (filterMode === "all") return true;
                return getEntryMode(trade) === filterMode;
              }).length === 0 && filterMode !== "all" ? (
              <div className="text-center py-6">
                <p className="text-sm text-zinc-500 mb-1">
                  {filterMode === "live" ? "No live trades yet" : "No simulation trades yet"}
                </p>
                <p className="text-xs text-zinc-600">
                  {filterMode === "live"
                    ? "Connect a broker in Settings and execute in Live mode to see trades here"
                    : "Execute a trade in Simulate mode to see trades here"}
                </p>
                <button
                  onClick={() => setFilterMode("all")}
                  className="mt-3 px-4 py-1.5 rounded-lg text-xs font-semibold bg-white/[0.06] text-zinc-400 hover:text-white transition-all"
                >
                  Show All Trades
                </button>
              </div>
            ) : null}
            {userTrades
              .filter((trade) => {
                if (filterMode === "all") return true;
                return getEntryMode(trade) === filterMode;
              })
              .map((trade) => {
              const isExpanded = expandedId === trade.id;
              const entryMode = getEntryMode(trade);
              const borderColor = entryMode === "live" ? "border-l-green-500" : "border-l-yellow-500";
              return (
                <motion.div
                  key={trade.id}
                  initial={false}
                  animate={{ opacity: 1, y: 0 }}
                  className={`rounded-xl border border-emerald-500/10 bg-emerald-500/[0.03] overflow-hidden border-l-[3px] ${borderColor}`}
                >
                  <button
                    onClick={() => setExpandedId(isExpanded ? null : trade.id)}
                    className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-emerald-500/[0.02] transition-colors"
                  >
                    <TrendingUp className={`w-4 h-4 flex-shrink-0 ${trade.details?.side === "SHORT" ? "text-red-400" : "text-emerald-400"}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-bold ${
                          entryMode === "live"
                            ? "bg-green-500/15 text-green-400 border border-green-500/30"
                            : "bg-yellow-500/15 text-yellow-400 border border-yellow-500/30"
                        }`} style={{ fontFamily: "JetBrains Mono, monospace" }}>
                          {entryMode === "live" ? "LIVE" : "PAPER"}
                        </span>
                        <span className="text-xs font-semibold text-white">{trade.title}</span>
                        {trade.details?.tier && (
                          <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold ${
                            trade.details.tier === "A+" ? "bg-amber-500/15 text-amber-400" :
                            trade.details.tier === "A" ? "bg-emerald-500/15 text-emerald-400" :
                            "bg-indigo-500/15 text-indigo-400"
                          }`} style={{ fontFamily: "JetBrains Mono, monospace" }}>
                            {trade.details.tier}
                          </span>
                        )}
                        {trade.details?.confidence !== undefined && (
                          <span className={`text-[9px] px-1.5 py-0.5 rounded font-medium ${
                            trade.details.confidence >= 85 ? "bg-emerald-500/10 text-emerald-400" :
                            trade.details.confidence >= 75 ? "bg-amber-500/10 text-amber-400" :
                            "bg-red-500/10 text-red-400"
                          }`} style={{ fontFamily: "JetBrains Mono, monospace" }}>
                            {trade.details.confidence}%
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-zinc-500 mt-0.5 truncate">{trade.message}</p>
                      {!isExpanded && trade.details?.reasoning && (
                        <p className="text-[10px] text-indigo-400/70 mt-0.5 flex items-center gap-1">
                          <Brain className="w-2.5 h-2.5 flex-shrink-0" />
                          <span className="truncate">{trade.details?.reasoning?.slice(0, 90)}{(trade.details?.reasoning?.length ?? 0) > 90 ? "..." : ""}</span>
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className="text-[10px] text-zinc-600" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                        {timeAgo(trade.timestamp)}
                      </span>
                      {isExpanded ? <ChevronUp className="w-3.5 h-3.5 text-zinc-600" /> : <ChevronDown className="w-3.5 h-3.5 text-zinc-600" />}
                    </div>
                  </button>
                  <AnimatePresence>
                    {isExpanded && trade.details && (
                      <motion.div
                        initial={false}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                      >
                        <div className="px-4 pb-4 space-y-3">
                          {/* Trade stats grid */}
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px]" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                            {trade.details?.asset && <div className="bg-white/[0.03] rounded-lg px-3 py-2"><div className="text-[9px] text-zinc-600 uppercase mb-0.5">Asset</div><div className="text-zinc-300">{trade.details.asset}</div></div>}
                            {trade.details?.side && <div className="bg-white/[0.03] rounded-lg px-3 py-2"><div className="text-[9px] text-zinc-600 uppercase mb-0.5">Side</div><div className={trade.details.side === "LONG" ? "text-emerald-400" : "text-red-400"}>{trade.details.side}</div></div>}
                            {trade.details?.entry_price != null && <div className="bg-white/[0.03] rounded-lg px-3 py-2"><div className="text-[9px] text-zinc-600 uppercase mb-0.5">Entry</div><div className="text-zinc-300">${Number(trade.details.entry_price).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</div></div>}
                            {trade.details?.strategy && <div className="bg-white/[0.03] rounded-lg px-3 py-2"><div className="text-[9px] text-zinc-600 uppercase mb-0.5">Strategy</div><div className="text-zinc-300">{trade.details.strategy}</div></div>}
                            {trade.details?.stop_loss != null && <div className="bg-white/[0.03] rounded-lg px-3 py-2"><div className="text-[9px] text-zinc-600 uppercase mb-0.5">Stop Loss</div><div className="text-red-400">${Number(trade.details.stop_loss).toFixed(2)}</div></div>}
                            {trade.details?.take_profit != null && <div className="bg-white/[0.03] rounded-lg px-3 py-2"><div className="text-[9px] text-zinc-600 uppercase mb-0.5">Take Profit</div><div className="text-emerald-400">${Number(trade.details.take_profit).toFixed(2)}</div></div>}
                          </div>
                          {/* Reasoning sections */}
                          {trade.details?.reasoning && (
                            <div className="card-glass rounded-xl p-4"><div className="text-[10px] text-indigo-400 uppercase tracking-wider mb-2 flex items-center gap-1.5" style={{ fontFamily: "JetBrains Mono, monospace" }}><Brain className="w-3 h-3" /> AI Reasoning</div><p className="text-xs text-zinc-400 leading-relaxed">{trade.details.reasoning}</p></div>
                          )}
                          {trade.details?.technical_signals && (
                            <div className="card-glass rounded-xl p-4"><div className="text-[10px] text-emerald-400 uppercase tracking-wider mb-2 flex items-center gap-1.5" style={{ fontFamily: "JetBrains Mono, monospace" }}><BarChart3 className="w-3 h-3" /> Technical Signals</div><p className="text-xs text-zinc-400 leading-relaxed">{trade.details.technical_signals}</p></div>
                          )}
                          {trade.details?.sentiment_signals && (
                            <div className="card-glass rounded-xl p-4"><div className="text-[10px] text-amber-400 uppercase tracking-wider mb-2 flex items-center gap-1.5" style={{ fontFamily: "JetBrains Mono, monospace" }}><Zap className="w-3 h-3" /> Sentiment</div><p className="text-xs text-zinc-400 leading-relaxed">{trade.details.sentiment_signals}</p></div>
                          )}
                          {trade.details?.risk_assessment && (
                            <div className="card-glass rounded-xl p-4"><div className="text-[10px] text-red-400 uppercase tracking-wider mb-2 flex items-center gap-1.5" style={{ fontFamily: "JetBrains Mono, monospace" }}><Shield className="w-3 h-3" /> Risk</div><p className="text-xs text-zinc-400 leading-relaxed">{trade.details.risk_assessment}</p></div>
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>

      {/* ─── Full Agent Reasoning Log ─────────────────────── */}
      <div className="card-glass rounded-2xl p-5">
        <h3 className="text-sm font-semibold text-zinc-300 mb-4 flex items-center gap-2">
          <Activity className="w-4 h-4 text-zinc-500" />
          Agent Reasoning Log
          <span className="text-[11px] text-zinc-600 font-normal">
            {activities.length} entries
          </span>
          <span className="ml-auto flex items-center gap-3">
            <button
              onClick={() => {
                localStorage.removeItem("aifred_local_trades");
                fetchActivities();
              }}
              className="text-[10px] text-zinc-600 hover:text-zinc-400 transition-colors uppercase tracking-wider"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
              title="Clear locally stored trades"
            >
              clear local
            </button>
            <div className="flex items-center gap-1.5">
              <div
                className="w-1.5 h-1.5 rounded-full bg-emerald-400"
                style={{ animation: "pulse-glow 2s ease-in-out infinite" }}
              />
              <span
                className="text-[10px] text-emerald-400/70 uppercase tracking-wider"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                Live · 10s
              </span>
            </div>
          </span>
        </h3>

        {activities.length === 0 ? (
          <div className="text-center py-12">
            <Activity className="w-8 h-8 text-zinc-700 mx-auto mb-3" />
            <p className="text-sm text-zinc-600">No activity yet</p>
          </div>
        ) : (
          <div className="space-y-1 max-h-[70vh] overflow-y-auto pr-1">
            {activities.map((entry, i) => {
              const config = ACTIVITY_TYPE_CONFIG[entry.type] || {
                icon: <Activity className="w-4 h-4" />,
                color: "text-zinc-400",
              };
              // For trade_closed, color based on P&L
              const iconColor =
                entry.type === "trade_closed" && entry.details?.pnl !== undefined
                  ? entry.details.pnl >= 0
                    ? "text-emerald-400"
                    : "text-red-400"
                  : config.color;
              const isExpanded = expandedId === entry.id;
              const isTrade = entry.type === "trade_executed" || entry.type === "trade_closed";
              const entryMode = isTrade ? getEntryMode(entry) : null;
              const tradeBorderClass = isTrade
                ? entryMode === "live" ? "border-l-[3px] border-l-green-500" : "border-l-[3px] border-l-yellow-500"
                : "";

              return (
                <motion.div
                  key={entry.id}
                  initial={false}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.03 }}
                  className={tradeBorderClass ? `rounded-lg ${tradeBorderClass}` : ""}
                >
                  <button
                    onClick={() =>
                      setExpandedId(isExpanded ? null : entry.id)
                    }
                    className="w-full flex items-start gap-3 px-3 py-3 rounded-lg hover:bg-white/[0.02] transition-colors text-left"
                  >
                    {/* Icon */}
                    <div
                      className={`mt-0.5 flex-shrink-0 ${iconColor}`}
                    >
                      {config.icon}
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        {isTrade && entryMode && (
                          <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-bold ${
                            entryMode === "live"
                              ? "bg-green-500/15 text-green-400 border border-green-500/30"
                              : "bg-yellow-500/15 text-yellow-400 border border-yellow-500/30"
                          }`} style={{ fontFamily: "JetBrains Mono, monospace" }}>
                            {entryMode === "live" ? "LIVE" : "PAPER"}
                          </span>
                        )}
                        <span className="text-xs font-semibold text-zinc-200">
                          {entry.title}
                        </span>
                        {entry.details?.tier && (
                          <span
                            className="text-[9px] px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-500"
                            style={{
                              fontFamily: "JetBrains Mono, monospace",
                            }}
                          >
                            {entry.details.tier}
                          </span>
                        )}
                        {entry.details?.confidence !== undefined && (
                          <span
                            className={`text-[9px] px-1.5 py-0.5 rounded font-medium ${
                              entry.details.confidence >= 85
                                ? "bg-emerald-500/10 text-emerald-400"
                                : entry.details.confidence >= 75
                                ? "bg-amber-500/10 text-amber-400"
                                : "bg-red-500/10 text-red-400"
                            }`}
                            style={{
                              fontFamily: "JetBrains Mono, monospace",
                            }}
                          >
                            {entry.details.confidence}% conf
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-zinc-500 mt-0.5 truncate">
                        {entry.message}
                      </p>
                      {/* Reasoning preview (trade entries only) */}
                      {!isExpanded && entry.details?.reasoning && (
                        <p className="text-[10px] text-indigo-400/70 mt-0.5 flex items-center gap-1">
                          <Brain className="w-2.5 h-2.5 flex-shrink-0" />
                          <span className="truncate">
                            {entry.details?.reasoning?.slice(0, 90)}
                            {(entry.details?.reasoning?.length ?? 0) > 90 ? "..." : ""}
                          </span>
                        </p>
                      )}
                    </div>

                    {/* Time + expand */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span
                        className="text-[10px] text-zinc-600"
                        style={{
                          fontFamily: "JetBrains Mono, monospace",
                        }}
                      >
                        {timeAgo(entry.timestamp)}
                      </span>
                      {entry.details && (
                        <span className="text-zinc-600">
                          {isExpanded ? (
                            <ChevronUp className="w-3.5 h-3.5" />
                          ) : (
                            <ChevronDown className="w-3.5 h-3.5" />
                          )}
                        </span>
                      )}
                    </div>
                  </button>

                  {/* Expandable details */}
                  <AnimatePresence>
                    {isExpanded && entry.details && (
                      <motion.div
                        initial={false}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                      >
                        <div className="px-10 pb-4 space-y-3">
                          {/* Trade details grid */}
                          {(entry.details.asset ||
                            entry.details.entry_price !== undefined) && (
                            <div
                              className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px]"
                              style={{
                                fontFamily: "JetBrains Mono, monospace",
                              }}
                            >
                              {entry.details.asset && (
                                <div className="bg-white/[0.02] rounded-lg px-3 py-2">
                                  <div className="text-[9px] text-zinc-600 uppercase tracking-wider mb-0.5">
                                    Asset
                                  </div>
                                  <div className="text-zinc-300">
                                    {entry.details.asset}
                                  </div>
                                </div>
                              )}
                              {entry.details.side && (
                                <div className="bg-white/[0.02] rounded-lg px-3 py-2">
                                  <div className="text-[9px] text-zinc-600 uppercase tracking-wider mb-0.5">
                                    Side
                                  </div>
                                  <div
                                    className={
                                      entry.details.side === "LONG"
                                        ? "text-emerald-400"
                                        : "text-red-400"
                                    }
                                  >
                                    {entry.details.side}
                                  </div>
                                </div>
                              )}
                              {entry.details.strategy && (
                                <div className="bg-white/[0.02] rounded-lg px-3 py-2">
                                  <div className="text-[9px] text-zinc-600 uppercase tracking-wider mb-0.5">
                                    Strategy
                                  </div>
                                  <div className="text-zinc-300">
                                    {STRATEGY_LABELS[
                                      entry.details.strategy
                                    ] || entry.details.strategy}
                                  </div>
                                </div>
                              )}
                              {entry.details.confidence !== undefined && (
                                <div className="bg-white/[0.02] rounded-lg px-3 py-2">
                                  <div className="text-[9px] text-zinc-600 uppercase tracking-wider mb-0.5">
                                    Confidence
                                  </div>
                                  <div className="text-amber-400">
                                    {Number(entry.details.confidence).toFixed(0)}%
                                  </div>
                                </div>
                              )}
                              {entry.details.entry_price !== undefined && (
                                <div className="bg-white/[0.02] rounded-lg px-3 py-2">
                                  <div className="text-[9px] text-zinc-600 uppercase tracking-wider mb-0.5">
                                    Entry Price
                                  </div>
                                  <div className="text-zinc-300">
                                    $
                                    {Number(entry.details.entry_price).toLocaleString(
                                      undefined,
                                      {
                                        minimumFractionDigits: 2,
                                        maximumFractionDigits: 2,
                                      }
                                    )}
                                  </div>
                                </div>
                              )}
                              {entry.details.stop_loss !== undefined && (
                                <div className="bg-white/[0.02] rounded-lg px-3 py-2">
                                  <div className="text-[9px] text-zinc-600 uppercase tracking-wider mb-0.5">
                                    Stop Loss
                                  </div>
                                  <div className="text-red-400">
                                    ${Number(entry.details.stop_loss).toFixed(2)}
                                  </div>
                                </div>
                              )}
                              {entry.details.take_profit !== undefined && (
                                <div className="bg-white/[0.02] rounded-lg px-3 py-2">
                                  <div className="text-[9px] text-zinc-600 uppercase tracking-wider mb-0.5">
                                    Take Profit
                                  </div>
                                  <div className="text-emerald-400">
                                    ${Number(entry.details.take_profit).toFixed(2)}
                                  </div>
                                </div>
                              )}
                              {entry.details.tier && (
                                <div className="bg-white/[0.02] rounded-lg px-3 py-2">
                                  <div className="text-[9px] text-zinc-600 uppercase tracking-wider mb-0.5">
                                    Tier
                                  </div>
                                  <div
                                    style={{
                                      color:
                                        TIER_COLORS[entry.details.tier] ||
                                        "#a1a1aa",
                                    }}
                                  >
                                    {entry.details.tier}
                                  </div>
                                </div>
                              )}
                            </div>
                          )}

                          {/* Reasoning section */}
                          {entry.details.reasoning && (
                            <div className="card-glass rounded-xl p-4">
                              <div
                                className="text-[10px] text-indigo-400 uppercase tracking-wider mb-2 flex items-center gap-1.5"
                                style={{
                                  fontFamily: "JetBrains Mono, monospace",
                                }}
                              >
                                <Brain className="w-3 h-3" />
                                AI Reasoning
                              </div>
                              <p className="text-xs text-zinc-400 leading-relaxed">
                                {entry.details.reasoning}
                              </p>
                            </div>
                          )}

                          {entry.details.technical_signals && (
                            <div className="card-glass rounded-xl p-4">
                              <div
                                className="text-[10px] text-emerald-400 uppercase tracking-wider mb-2 flex items-center gap-1.5"
                                style={{
                                  fontFamily: "JetBrains Mono, monospace",
                                }}
                              >
                                <BarChart3 className="w-3 h-3" />
                                Technical Analysis
                              </div>
                              <p className="text-xs text-zinc-400 leading-relaxed">
                                {entry.details.technical_signals}
                              </p>
                            </div>
                          )}

                          {entry.details.sentiment_signals && (
                            <div className="card-glass rounded-xl p-4">
                              <div
                                className="text-[10px] text-amber-400 uppercase tracking-wider mb-2 flex items-center gap-1.5"
                                style={{
                                  fontFamily: "JetBrains Mono, monospace",
                                }}
                              >
                                <Zap className="w-3 h-3" />
                                Sentiment Analysis
                              </div>
                              <p className="text-xs text-zinc-400 leading-relaxed">
                                {entry.details.sentiment_signals}
                              </p>
                            </div>
                          )}

                          {entry.details.risk_assessment && (
                            <div className="card-glass rounded-xl p-4">
                              <div
                                className="text-[10px] text-red-400 uppercase tracking-wider mb-2 flex items-center gap-1.5"
                                style={{
                                  fontFamily: "JetBrains Mono, monospace",
                                }}
                              >
                                <Shield className="w-3 h-3" />
                                Risk Assessment
                              </div>
                              <p className="text-xs text-zinc-400 leading-relaxed">
                                {entry.details.risk_assessment}
                              </p>
                            </div>
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>
    </motion.div>
  );
}
