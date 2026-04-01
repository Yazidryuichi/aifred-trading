"use client";

import { motion } from "framer-motion";

interface ExchangeCardProps {
  name: string;
  id: string;
  type: "DEX" | "CEX";
  connected: boolean;
}

export function ExchangeCard({ name, id, type, connected }: ExchangeCardProps) {
  return (
    <motion.div
      initial={false}
      animate={{ opacity: 1 }}
      className="relative rounded-xl p-4 border backdrop-blur-sm transition-all hover:bg-white/[0.07] hover:border-white/[0.14]"
      style={{
        background: "rgba(255,255,255,0.03)",
        borderColor: "rgba(255,255,255,0.08)",
      }}
    >
      <div className="flex items-center justify-between mb-2">
        {/* Exchange name */}
        <h3
          className="text-sm font-bold text-white tracking-wide"
          style={{ fontFamily: "Outfit, sans-serif" }}
        >
          {name}
        </h3>

        {/* Type badge */}
        <span
          className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium tracking-wider ${
            type === "DEX"
              ? "bg-purple-500/15 border border-purple-500/25 text-purple-400"
              : "bg-blue-500/15 border border-blue-500/25 text-blue-400"
          }`}
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {type}
        </span>
      </div>

      {/* Exchange ID */}
      <p
        className="text-[10px] text-zinc-500 mb-3"
        style={{ fontFamily: "JetBrains Mono, monospace" }}
      >
        {id}
      </p>

      {/* Connection status */}
      <div className="flex items-center gap-2">
        <div
          className={`w-2 h-2 rounded-full ${
            connected ? "bg-emerald-400" : "bg-zinc-600"
          }`}
          style={connected ? { boxShadow: "0 0 6px rgba(16,185,129,0.5)" } : undefined}
        />
        <span
          className={`text-[10px] tracking-wider ${
            connected ? "text-emerald-400/80" : "text-zinc-600"
          }`}
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {connected ? "CONNECTED" : "AVAILABLE"}
        </span>

        {/* Visual bar */}
        <div className="flex-1 h-[2px] rounded-full bg-white/[0.04] ml-1">
          <div
            className={`h-full rounded-full transition-all ${
              connected ? "bg-emerald-500/40 w-full" : "w-0"
            }`}
          />
        </div>
      </div>
    </motion.div>
  );
}
