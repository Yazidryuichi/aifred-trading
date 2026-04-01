"use client";

import { motion } from "framer-motion";

interface ModelCardProps {
  name: string;
  modelId: string;
  provider: string;
  enabled: boolean;
  avatar?: string;
}

export function ModelCard({ name, modelId, provider, enabled, avatar }: ModelCardProps) {
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
      <div className="flex items-start gap-3">
        {/* Avatar */}
        <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-indigo-500/20 to-emerald-500/20 border border-white/[0.08] flex items-center justify-center flex-shrink-0">
          <span className="text-sm">{avatar || "🤖"}</span>
        </div>

        <div className="flex-1 min-w-0">
          {/* Name */}
          <h3
            className="text-sm font-semibold text-white truncate"
            style={{ fontFamily: "Outfit, sans-serif" }}
          >
            {name}
          </h3>

          {/* Model ID */}
          <p
            className="text-[10px] text-indigo-400/80 mt-0.5 truncate"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            {modelId}
          </p>

          {/* Provider */}
          <p
            className="text-[10px] text-zinc-500 mt-0.5"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            {provider}
          </p>
        </div>
      </div>

      {/* Status */}
      <div className="flex items-center gap-1.5 mt-3">
        <div
          className={`w-2 h-2 rounded-full ${
            enabled ? "bg-emerald-400" : "bg-zinc-600"
          }`}
          style={enabled ? { boxShadow: "0 0 6px rgba(16,185,129,0.5)" } : undefined}
        />
        <span
          className={`text-[10px] tracking-wider ${
            enabled ? "text-emerald-400/80" : "text-zinc-600"
          }`}
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          {enabled ? "ENABLED" : "DISABLED"}
        </span>
      </div>
    </motion.div>
  );
}
