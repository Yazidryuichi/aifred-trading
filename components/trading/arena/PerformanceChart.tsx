"use client";

import { useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { DataPoint, StrategyInfo } from "@/lib/arena-data";

const COLORS: Record<string, string> = {
  emerald: "#10b981",
  blue: "#3b82f6",
  purple: "#a855f7",
};

interface Props {
  data: DataPoint[];
  strategies: StrategyInfo[];
}

function CustomTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: Array<{ dataKey: string; value: number; color: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const date = label ? new Date(label) : null;
  return (
    <div
      className="rounded-xl border border-white/10 px-4 py-3 text-xs"
      style={{
        background: "rgba(6,6,10,0.95)",
        backdropFilter: "blur(12px)",
        fontFamily: "JetBrains Mono, monospace",
      }}
    >
      {date && (
        <div className="text-zinc-500 mb-2">
          {date.toLocaleDateString("en-US", { month: "short", day: "numeric" })}{" "}
          {date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
        </div>
      )}
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 py-0.5">
          <div
            className="w-2 h-2 rounded-full"
            style={{ background: p.color }}
          />
          <span className="text-zinc-400 capitalize">{p.dataKey}</span>
          <span
            className="ml-auto font-semibold"
            style={{ color: p.color }}
          >
            {p.value >= 0 ? "+" : ""}
            {p.value.toFixed(1)}%
          </span>
        </div>
      ))}
    </div>
  );
}

export function PerformanceChart({ data, strategies }: Props) {
  // Downsample for performance: show every 4th point (180 points)
  const sampled = useMemo(() => {
    const result: DataPoint[] = [];
    for (let i = 0; i < data.length; i += 4) {
      result.push(data[i]);
    }
    // Always include last point
    if (data.length > 0 && result[result.length - 1] !== data[data.length - 1]) {
      result.push(data[data.length - 1]);
    }
    return result;
  }, [data]);

  const leader = strategies[0];
  const gap = strategies.length > 1
    ? (strategies[0].pnlPercent - strategies[1].pnlPercent).toFixed(1)
    : "0";

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={sampled}
            margin={{ top: 8, right: 8, left: -10, bottom: 0 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(255,255,255,0.04)"
              vertical={false}
            />
            <XAxis
              dataKey="time"
              tickFormatter={(v: string) => {
                const d = new Date(v);
                return `${d.getMonth() + 1}/${d.getDate()}`;
              }}
              stroke="rgba(255,255,255,0.15)"
              tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              interval={Math.floor(sampled.length / 6)}
            />
            <YAxis
              tickFormatter={(v: number) => `${v >= 0 ? "+" : ""}${v}%`}
              stroke="rgba(255,255,255,0.15)"
              tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              domain={["auto", "auto"]}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              verticalAlign="top"
              height={28}
              formatter={(value: string) => (
                <span className="text-xs text-zinc-400 capitalize">{value}</span>
              )}
            />
            {strategies.map((s) => (
              <Line
                key={s.id}
                type="monotone"
                dataKey={s.id === "claude-ensemble" ? "claude" : s.id === "deepseek-momentum" ? "deepseek" : "gemini"}
                name={s.name}
                stroke={COLORS[s.color] || "#888"}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 0 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Stats bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3 pt-3 border-t border-white/[0.06]">
        {[
          { label: "LEADER", value: leader.name, color: "text-emerald-400" },
          { label: "LEAD PNL", value: `+${leader.pnlPercent}%`, color: "text-emerald-400" },
          { label: "CURRENT GAP", value: `${gap}%`, color: "text-amber-400" },
          { label: "DATA POINTS", value: data.length.toLocaleString(), color: "text-zinc-300" },
        ].map((s) => (
          <div key={s.label} className="text-center">
            <div
              className="text-[9px] text-zinc-600 tracking-widest mb-0.5"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              {s.label}
            </div>
            <div
              className={`text-xs font-semibold ${s.color}`}
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              {s.value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
