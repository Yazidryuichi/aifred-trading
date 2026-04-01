"use client";

import { useState } from "react";

interface StatCardProps {
  icon: string;
  label: string;
  value: string;
  subtitle?: string;
  helpText?: string;
  color?: "green" | "red" | "default";
}

export function StatCard({
  icon,
  label,
  value,
  subtitle,
  helpText,
  color = "default",
}: StatCardProps) {
  const [showTooltip, setShowTooltip] = useState(false);

  const valueColor =
    color === "green"
      ? "text-emerald-400"
      : color === "red"
        ? "text-red-400"
        : "text-white";

  return (
    <div className="relative bg-white/5 border border-white/10 rounded-xl p-4 md:p-5 backdrop-blur-sm hover:bg-white/[0.07] hover:border-white/[0.14] transition-all">
      {/* Help icon */}
      {helpText && (
        <button
          className="absolute top-2.5 right-2.5 w-4 h-4 rounded-full bg-white/[0.06] border border-white/10 flex items-center justify-center text-[9px] text-zinc-500 hover:text-zinc-300 hover:bg-white/10 transition-colors"
          onMouseEnter={() => setShowTooltip(true)}
          onMouseLeave={() => setShowTooltip(false)}
          onClick={() => setShowTooltip((v) => !v)}
          aria-label={`Help: ${label}`}
        >
          ?
        </button>
      )}

      {/* Tooltip */}
      {showTooltip && helpText && (
        <div className="absolute top-0 right-0 -translate-y-full mr-0 mb-1 z-30 max-w-[200px] px-3 py-2 rounded-lg bg-zinc-900 border border-white/10 text-[10px] text-zinc-300 leading-relaxed shadow-xl">
          {helpText}
        </div>
      )}

      {/* Icon + Label */}
      <div className="flex items-center gap-1.5 mb-2">
        <span className="text-sm">{icon}</span>
        <p
          className="text-[10px] text-zinc-500 tracking-widest uppercase"
          style={{ fontFamily: "Outfit, sans-serif" }}
        >
          {label}
        </p>
      </div>

      {/* Value */}
      <p
        className={`text-xl md:text-2xl font-bold ${valueColor}`}
        style={{ fontFamily: "JetBrains Mono, monospace" }}
      >
        {value}
      </p>

      {/* Subtitle */}
      {subtitle && (
        <p
          className="text-[11px] text-zinc-500 mt-1"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {subtitle}
        </p>
      )}
    </div>
  );
}
