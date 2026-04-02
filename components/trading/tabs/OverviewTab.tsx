"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import {
  TrendingUp,
  Activity,
  Shield,
  Zap,
  Target,
  BarChart3,
  Brain,
  Layers,
  AlertTriangle,
} from "lucide-react";
import { ConnectWallet } from "@/components/wallet/ConnectWallet";
import { HyperliquidBalance } from "@/components/wallet/HyperliquidBalance";
import { LiveStatusPanel } from "@/components/trading/LiveStatusPanel";
import {
  type TradingData,
  type ActivityEntry,
  fmt,
  pct,
  timeAgo,
  getEntryMode,
  STRATEGY_LABELS,
  TIER_COLORS,
  SEVERITY_DOT,
} from "@/components/trading/trading-utils";

// ─── Sub-components ──────────────────────────────────────────

function HeroStat({
  label,
  value,
  sub,
  positive,
  icon,
  delay,
  highlight,
  invert,
}: {
  label: string;
  value: string;
  sub: string;
  positive: boolean;
  icon: React.ReactNode;
  delay: number;
  highlight?: boolean;
  invert?: boolean;
}) {
  const color = invert
    ? positive
      ? "text-emerald-400"
      : "text-red-400"
    : positive
    ? "text-emerald-400"
    : "text-red-400";
  const glow = invert
    ? positive
      ? "glow-green"
      : "glow-red"
    : positive
    ? "glow-green"
    : "glow-red";

  return (
    <motion.div
      initial={false}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
      className={`card-glass rounded-2xl p-5 relative overflow-hidden ${
        highlight ? "ring-1 ring-emerald-500/20" : ""
      }`}
    >
      {highlight && (
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            background:
              "radial-gradient(circle at 50% 0%, rgba(16,185,129,1) 0%, transparent 60%)",
          }}
        />
      )}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-zinc-500">{icon}</span>
        <span
          className="text-[10px] text-zinc-500 uppercase tracking-[0.15em]"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {label}
        </span>
      </div>
      <div
        className={`text-2xl font-bold ${color} ${glow}`}
        style={{ fontFamily: "JetBrains Mono, monospace" }}
      >
        {value}
      </div>
      <div
        className="text-[11px] text-zinc-600 mt-1"
        style={{ fontFamily: "JetBrains Mono, monospace" }}
      >
        {sub}
      </div>
    </motion.div>
  );
}

function MiniStat({
  label,
  value,
  positive,
  neutral,
}: {
  label: string;
  value: string;
  positive?: boolean;
  neutral?: boolean;
}) {
  return (
    <div className="text-center">
      <div
        className={`text-lg font-semibold ${
          neutral
            ? "text-zinc-300"
            : positive
            ? "text-emerald-400"
            : "text-red-400"
        }`}
        style={{ fontFamily: "JetBrains Mono, monospace" }}
      >
        {value}
      </div>
      <div
        className="text-[10px] text-zinc-600 mt-0.5 uppercase tracking-wider"
        style={{ fontFamily: "JetBrains Mono, monospace" }}
      >
        {label}
      </div>
    </div>
  );
}

function AssetRow({
  asset,
  pnl,
  trades,
  winRate,
}: {
  asset: string;
  pnl: number;
  trades: number;
  winRate: number;
}) {
  return (
    <div className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-white/[0.02] transition-colors">
      <div className="flex items-center gap-3">
        <span className="text-xs font-medium text-zinc-300 w-20">
          {asset}
        </span>
        <span
          className="text-[10px] text-zinc-600"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {trades}t
        </span>
      </div>
      <div className="flex items-center gap-4">
        <div className="w-16 h-1 bg-white/[0.04] rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full ${
              winRate >= 70 ? "bg-emerald-500" : winRate >= 50 ? "bg-amber-500" : "bg-red-500"
            }`}
            style={{ width: `${Math.min(winRate, 100)}%` }}
          />
        </div>
        <span
          className={`text-xs font-medium w-14 text-right ${
            pnl >= 0 ? "text-emerald-400" : "text-red-400"
          }`}
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {pnl >= 0 ? "+" : ""}
          {fmt(pnl)}
        </span>
      </div>
    </div>
  );
}

function StrategyRow({
  strategy,
  pnl,
  trades,
  winRate,
}: {
  strategy: string;
  pnl: number;
  trades: number;
  winRate: number;
}) {
  return (
    <div className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-white/[0.02] transition-colors">
      <div>
        <span className="text-xs font-medium text-zinc-300">
          {STRATEGY_LABELS[strategy] || strategy}
        </span>
        <div
          className="text-[10px] text-zinc-600 mt-0.5"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {trades} trades · WR {pct(winRate)}
        </div>
      </div>
      <span
        className={`text-xs font-medium ${
          pnl >= 0 ? "text-emerald-400" : "text-red-400"
        }`}
        style={{ fontFamily: "JetBrains Mono, monospace" }}
      >
        {pnl >= 0 ? "+" : ""}
        {fmt(pnl)}
      </span>
    </div>
  );
}

// ─── OverviewTab ─────────────────────────────────────────────

export function OverviewTab({
  data,
  onNavigateActivity,
}: {
  data: TradingData;
  onNavigateActivity: () => void;
}) {
  const summary = {
    totalPnl: 0, winRate: 0, totalTrades: 0, openPositions: 0,
    avgConfidence: 0, signalCount: 0, activeStrategies: 0,
    sharpeRatio: 0, sortinoRatio: null as number | null, maxDrawdown: 0, profitFactor: 0,
    avgWin: 0, avgLoss: 0, totalFees: 0, currentEquity: 0,
    ...(data.summary ?? {}),
  };
  const isPositive = summary.totalPnl >= 0;
  const [recentActivity, setRecentActivity] = useState<ActivityEntry[]>([]);

  useEffect(() => {
    fetch("/api/trading/activity")
      .then((r) => r.json())
      .then((data) => {
        const serverList = Array.isArray(data) ? data : (data?.activities ?? []);
        // Merge with localStorage trades for consistency
        try {
          const localTrades = JSON.parse(
            localStorage.getItem("aifred_local_trades") || "[]"
          );
          // Sanitize entries — ensure they have required fields
          const sanitize = (e: Record<string, unknown>) => ({
            ...e,
            id: e.id || `gen_${Math.random().toString(36).slice(2, 8)}`,
            message: typeof e.message === "string" ? e.message : (e.title || e.asset || "Trade") as string,
            type: e.type || "trade_executed",
            severity: e.severity || "info",
            timestamp: e.timestamp || new Date().toISOString(),
          });
          const merged = [...localTrades.map(sanitize), ...serverList.map(sanitize)];
          const seen = new Set<string>();
          const deduped = merged.filter((e) => {
            if (seen.has(e.id)) return false;
            seen.add(e.id);
            return true;
          });
          deduped.sort(
            (a, b) =>
              new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
          );
          setRecentActivity(deduped.slice(0, 5));
        } catch {
          setRecentActivity(serverList.slice(0, 5));
        }
      })
      .catch(() => {});
  }, []);

  return (
    <motion.div
      initial={false}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.3 }}
      className="space-y-6 pb-12"
    >
      {/* ─── Activity Summary Bar ─────────────────────────── */}
      {recentActivity.length > 0 && (
        <motion.div
          initial={false}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          aria-live="polite"
          className="card-glass rounded-xl px-4 py-2.5 flex items-center gap-2 overflow-x-auto cursor-pointer hover:border-white/[0.12] transition-all"
          onClick={onNavigateActivity}
        >
          <Activity className="w-3.5 h-3.5 text-zinc-500 flex-shrink-0" />
          <span
            className="text-[10px] text-zinc-500 uppercase tracking-wider flex-shrink-0 mr-2"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            LIVE
          </span>
          <div className="flex items-center gap-4 overflow-x-auto">
            {recentActivity.map((entry) => {
              const isTrade = entry.type === "trade_executed" || entry.type === "trade_closed";
              const entryMode = isTrade ? getEntryMode(entry) : null;
              return (
                <div
                  key={entry.id}
                  className="flex items-center gap-2 flex-shrink-0"
                >
                  <div
                    className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                      SEVERITY_DOT[entry.severity] || "bg-zinc-500"
                    }`}
                  />
                  {isTrade && entryMode && (
                    <span className={`text-[8px] px-1 py-0.5 rounded font-bold flex-shrink-0 ${
                      entryMode === "live"
                        ? "bg-green-500/15 text-green-400"
                        : "bg-yellow-500/15 text-yellow-400"
                    }`} style={{ fontFamily: "JetBrains Mono, monospace" }}>
                      {entryMode === "live" ? "LIVE" : "SIM"}
                    </span>
                  )}
                  <span className="text-[11px] text-zinc-400 whitespace-nowrap">
                    {typeof entry.message === "string"
                      ? (entry.message.length > 40 ? entry.message.slice(0, 40) + "..." : entry.message)
                      : String(entry.message ?? "")}
                  </span>
                  <span
                    className="text-[10px] text-zinc-600 whitespace-nowrap"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {timeAgo(entry.timestamp)}
                  </span>
                </div>
              );
            })}
          </div>
        </motion.div>
      )}

      {/* ─── Hyperliquid Account ──────────────────────────── */}
      <HyperliquidBalance />

      {/* ─── Live System Status ─────────────────────────────── */}
      <LiveStatusPanel />

      {/* ─── Demo Data Warning Banner ──────────────────────── */}
      <div className="flex items-start gap-3 px-4 py-3 rounded-xl border border-amber-500/25 bg-amber-500/[0.06]">
        <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 flex-shrink-0" />
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span
              className="text-[11px] text-amber-400 font-bold tracking-wider uppercase"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              DEMO DATA
            </span>
            <span className="text-[10px] text-amber-400/60 bg-amber-500/10 border border-amber-500/15 px-2 py-0.5 rounded-md tracking-wider uppercase font-medium" style={{ fontFamily: "JetBrains Mono, monospace" }}>
              Simulated Backtest
            </span>
          </div>
          <p className="text-[11px] text-zinc-400 leading-relaxed">
            Based on simulated backtest results. Not indicative of future performance. Live trading validation in progress.
          </p>
        </div>
      </div>

      {/* ─── Hero Stats ─────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <HeroStat
          label="Total P&L"
          value={fmt(summary.totalPnl)}
          sub={`Equity: ${fmt(summary.currentEquity)}`}
          positive={isPositive}
          icon={<TrendingUp className="w-4 h-4" />}
          delay={0}
        />
        <HeroStat
          label="Win Rate"
          value={pct(summary.winRate)}
          sub={`${summary.totalTrades} closed trades`}
          positive={summary.winRate >= 60}
          icon={<Target className="w-4 h-4" />}
          delay={0.05}
          highlight
        />
        <HeroStat
          label="Sharpe Ratio"
          value={summary.sharpeRatio.toFixed(2)}
          sub={`Sortino: ${summary.sortinoRatio !== null ? summary.sortinoRatio.toFixed(2) : "N/A"}`}
          positive={summary.sharpeRatio > 1}
          icon={<BarChart3 className="w-4 h-4" />}
          delay={0.1}
        />
        <HeroStat
          label="Max Drawdown"
          value={pct(summary.maxDrawdown)}
          sub={`Profit factor: ${summary.profitFactor.toFixed(2)}`}
          positive={summary.maxDrawdown < 10}
          icon={<Shield className="w-4 h-4" />}
          delay={0.15}
          invert
        />
      </div>

      {/* ─── Equity Curve ───────────────────────────────────── */}
      <motion.div
        initial={false}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="card-glass rounded-2xl p-6"
      >
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-sm font-semibold text-zinc-300">
              Equity Curve
            </h2>
            <p
              className="text-[11px] text-zinc-600 mt-0.5"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              30-DAY PERFORMANCE · WALK-FORWARD VALIDATED
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`text-sm font-semibold ${
                isPositive ? "text-emerald-400 glow-green" : "text-red-400 glow-red"
              }`}
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              {isPositive ? "+" : ""}
              {fmt(summary.totalPnl)}
            </span>
          </div>
        </div>
        <div className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.equityCurve ?? []}>
              <defs>
                <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="0%"
                    stopColor={isPositive ? "#10b981" : "#ef4444"}
                    stopOpacity={0.3}
                  />
                  <stop
                    offset="100%"
                    stopColor={isPositive ? "#10b981" : "#ef4444"}
                    stopOpacity={0}
                  />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(255,255,255,0.03)"
              />
              <XAxis
                dataKey="date"
                tick={{ fill: "#52525b", fontSize: 10, fontFamily: "JetBrains Mono" }}
                axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fill: "#52525b", fontSize: 10, fontFamily: "JetBrains Mono" }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v) => `$${(v / 1000).toFixed(0)}K`}
                domain={["dataMin - 1000", "dataMax + 1000"]}
              />
              <Tooltip
                contentStyle={{
                  background: "#0f0f14",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: "12px",
                  fontFamily: "JetBrains Mono",
                  fontSize: 12,
                }}
                labelStyle={{ color: "#71717a" }}
                formatter={(v?: number) => [`$${(v ?? 0).toLocaleString()}`, "Equity"]}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke={isPositive ? "#10b981" : "#ef4444"}
                strokeWidth={2}
                fill="url(#eqGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        {/* Equity curve disclaimer */}
        <div className="flex items-center gap-2 mt-3 px-1">
          <AlertTriangle className="w-3 h-3 text-amber-500/50 flex-shrink-0" />
          <p
            className="text-[10px] text-zinc-600 leading-relaxed"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            DEMO DATA — Simulated backtest equity curve. Past hypothetical performance does not guarantee future results.
          </p>
        </div>
      </motion.div>

      {/* ─── Three-column breakdown ─────────────────────────── */}
      <div className="grid lg:grid-cols-3 gap-4">
        {/* By Asset */}
        <motion.div
          initial={false}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
          className="card-glass rounded-2xl p-5"
        >
          <h3 className="text-sm font-semibold text-zinc-300 mb-4 flex items-center gap-2">
            <Layers className="w-4 h-4 text-zinc-500" />
            Performance by Asset
          </h3>
          <div className="space-y-3">
            {(data.byAsset ?? [])
              .sort((a, b) => b.pnl - a.pnl)
              .map((a) => (
                <AssetRow key={a.asset} {...a} />
              ))}
          </div>
        </motion.div>

        {/* By Strategy */}
        <motion.div
          initial={false}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="card-glass rounded-2xl p-5"
        >
          <h3 className="text-sm font-semibold text-zinc-300 mb-4 flex items-center gap-2">
            <Brain className="w-4 h-4 text-zinc-500" />
            Performance by Strategy
          </h3>
          <div className="space-y-3">
            {(data.byStrategy ?? [])
              .sort((a, b) => b.pnl - a.pnl)
              .map((s) => (
                <StrategyRow key={s.strategy} {...s} />
              ))}
          </div>
        </motion.div>

        {/* By Signal Tier */}
        <motion.div
          initial={false}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35 }}
          className="card-glass rounded-2xl p-5"
        >
          <h3 className="text-sm font-semibold text-zinc-300 mb-4 flex items-center gap-2">
            <Zap className="w-4 h-4 text-zinc-500" />
            Signal Tier Breakdown
          </h3>
          <div className="h-[160px] mb-4">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={(data.byTier ?? []).map((t) => ({
                    name: t.tier,
                    value: t.trades,
                  }))}
                  cx="50%"
                  cy="50%"
                  innerRadius={40}
                  outerRadius={65}
                  paddingAngle={3}
                  dataKey="value"
                  stroke="none"
                >
                  {(data.byTier ?? []).map((t, i) => (
                    <Cell
                      key={i}
                      fill={TIER_COLORS[t.tier] || "#6366f1"}
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: "#0f0f14",
                    border: "1px solid rgba(255,255,255,0.08)",
                    borderRadius: "8px",
                    fontFamily: "JetBrains Mono",
                    fontSize: 11,
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="space-y-2">
            {(data.byTier ?? [])
              .sort((a, b) => {
                const order = ["A+", "A", "B", "C"];
                return order.indexOf(a.tier) - order.indexOf(b.tier);
              })
              .map((t) => (
                <div
                  key={t.tier}
                  className="flex items-center justify-between text-xs"
                >
                  <div className="flex items-center gap-2">
                    <div
                      className="w-2 h-2 rounded-full"
                      style={{
                        backgroundColor: TIER_COLORS[t.tier] || "#6366f1",
                      }}
                    />
                    <span className="text-zinc-400">Tier {t.tier}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span
                      className="text-zinc-500"
                      style={{ fontFamily: "JetBrains Mono, monospace" }}
                    >
                      {t.trades} trades
                    </span>
                    <span
                      className={`font-medium ${
                        t.winRate >= 70
                          ? "text-emerald-400"
                          : t.winRate >= 50
                          ? "text-amber-400"
                          : "text-red-400"
                      }`}
                      style={{ fontFamily: "JetBrains Mono, monospace" }}
                    >
                      {pct(t.winRate)}
                    </span>
                  </div>
                </div>
              ))}
          </div>
        </motion.div>
      </div>

      {/* ─── Risk metrics bar ───────────────────────────────── */}
      <motion.div
        initial={false}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="card-glass rounded-2xl p-5"
      >
        <h3 className="text-sm font-semibold text-zinc-300 mb-4 flex items-center gap-2">
          <Shield className="w-4 h-4 text-zinc-500" />
          Risk Management
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          <MiniStat label="Avg Win" value={fmt(summary.avgWin)} positive />
          <MiniStat label="Avg Loss" value={fmt(summary.avgLoss)} positive={false} />
          <MiniStat
            label="Win/Loss Ratio"
            value={
              summary.avgLoss > 0
                ? (summary.avgWin / summary.avgLoss).toFixed(2)
                : "∞"
            }
            positive={summary.avgWin > summary.avgLoss}
          />
          <MiniStat
            label="Profit Factor"
            value={summary.profitFactor.toFixed(2)}
            positive={summary.profitFactor > 1.5}
          />
          <MiniStat
            label="Open Positions"
            value={String(summary.openPositions)}
            neutral
          />
          <MiniStat
            label="Total Fees"
            value={fmt(summary.totalFees)}
            positive={false}
          />
        </div>
      </motion.div>
    </motion.div>
  );
}
