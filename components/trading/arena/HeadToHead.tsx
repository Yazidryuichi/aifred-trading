"use client";

import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import type { StrategyInfo } from "@/lib/arena-data";

interface Props {
  strategies: StrategyInfo[];
}

function StrategyCard({
  strategy,
  isLeader,
  gap,
}: {
  strategy: StrategyInfo;
  isLeader: boolean;
  gap: number;
}) {
  const borderColor = isLeader
    ? `rgba(${strategy.colorRgb}, 0.3)`
    : "rgba(161, 161, 170, 0.12)";
  const bgColor = isLeader
    ? `rgba(${strategy.colorRgb}, 0.04)`
    : "rgba(255,255,255,0.02)";

  return (
    <motion.div
      initial={false}
      animate={{ opacity: 1, scale: 1 }}
      className="flex-1 rounded-xl p-5 border relative overflow-hidden"
      style={{
        borderColor,
        background: bgColor,
        backdropFilter: "blur(12px)",
      }}
    >
      {/* Leader glow */}
      {isLeader && (
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: `radial-gradient(ellipse at top, rgba(${strategy.colorRgb}, 0.06) 0%, transparent 70%)`,
          }}
        />
      )}

      <div className="relative z-10">
        {/* Name */}
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xl">{strategy.emoji}</span>
          <div>
            <div
              className="text-sm font-semibold text-white"
              style={{ fontFamily: "Outfit, sans-serif" }}
            >
              {strategy.name}
            </div>
            <div
              className="text-[10px] text-zinc-500"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              {strategy.model}
            </div>
          </div>
        </div>

        {/* PnL */}
        <div
          className={`text-3xl font-bold mb-2 ${
            strategy.pnlPercent >= 0 ? "text-emerald-400" : "text-red-400"
          }`}
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {strategy.pnlPercent >= 0 ? "+" : ""}
          {strategy.pnlPercent}%
        </div>

        {/* Lead / Behind label */}
        <div
          className={`text-xs font-medium mb-4 ${
            isLeader ? "text-emerald-400/80" : "text-zinc-500"
          }`}
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {isLeader
            ? `Leading by ${gap.toFixed(1)}%`
            : `Behind by ${gap.toFixed(1)}%`}
        </div>

        {/* Detail stats */}
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "TRADES", value: strategy.totalTrades.toString() },
            { label: "WIN RATE", value: `${strategy.winRate}%` },
            { label: "SHARPE", value: strategy.sharpeRatio.toFixed(2) },
          ].map((stat) => (
            <div
              key={stat.label}
              className="bg-white/[0.04] rounded-lg px-2.5 py-2 text-center"
            >
              <div
                className="text-[9px] text-zinc-600 tracking-wider mb-0.5"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {stat.label}
              </div>
              <div
                className="text-xs text-zinc-200 font-semibold"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {stat.value}
              </div>
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}

function StrategySelector({
  strategies,
  selected,
  onChange,
  exclude,
}: {
  strategies: StrategyInfo[];
  selected: string;
  onChange: (id: string) => void;
  exclude: string;
}) {
  const [open, setOpen] = useState(false);
  const current = strategies.find((s) => s.id === selected);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/[0.06] border border-white/[0.08] hover:bg-white/[0.1] transition-all text-xs"
        style={{ fontFamily: "JetBrains Mono, monospace" }}
      >
        <span>{current?.emoji}</span>
        <span className="text-zinc-300">{current?.name}</span>
        <ChevronDown className="w-3 h-3 text-zinc-500" />
      </button>
      {open && (
        <div
          className="absolute top-full mt-1 left-0 z-20 rounded-lg border border-white/10 py-1 min-w-[180px]"
          style={{
            background: "rgba(6,6,10,0.95)",
            backdropFilter: "blur(16px)",
          }}
        >
          {strategies
            .filter((s) => s.id !== exclude)
            .map((s) => (
              <button
                key={s.id}
                onClick={() => {
                  onChange(s.id);
                  setOpen(false);
                }}
                className={`w-full text-left px-3 py-2 text-xs flex items-center gap-2 hover:bg-white/[0.06] transition-colors ${
                  s.id === selected ? "text-white" : "text-zinc-400"
                }`}
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                <span>{s.emoji}</span>
                <span>{s.name}</span>
                <span className="ml-auto text-emerald-400">
                  +{s.pnlPercent}%
                </span>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}

export function HeadToHead({ strategies }: Props) {
  const [leftId, setLeftId] = useState(strategies[0]?.id || "");
  const [rightId, setRightId] = useState(strategies[1]?.id || "");

  const left = useMemo(
    () => strategies.find((s) => s.id === leftId) || strategies[0],
    [strategies, leftId]
  );
  const right = useMemo(
    () => strategies.find((s) => s.id === rightId) || strategies[1],
    [strategies, rightId]
  );

  const gap = Math.abs(left.pnlPercent - right.pnlPercent);
  const leftLeads = left.pnlPercent >= right.pnlPercent;

  return (
    <div>
      {/* Header with selectors */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <h3
          className="text-sm font-semibold text-zinc-300"
          style={{ fontFamily: "Outfit, sans-serif" }}
        >
          Head-to-Head Battle
        </h3>
        <div className="flex items-center gap-2">
          <StrategySelector
            strategies={strategies}
            selected={leftId}
            onChange={setLeftId}
            exclude={rightId}
          />
          <span
            className="text-[10px] text-zinc-600 font-bold"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            VS
          </span>
          <StrategySelector
            strategies={strategies}
            selected={rightId}
            onChange={setRightId}
            exclude={leftId}
          />
        </div>
      </div>

      {/* Cards */}
      <div className="flex gap-4 flex-col md:flex-row">
        <StrategyCard
          strategy={left}
          isLeader={leftLeads}
          gap={gap}
        />
        <StrategyCard
          strategy={right}
          isLeader={!leftLeads}
          gap={gap}
        />
      </div>
    </div>
  );
}
