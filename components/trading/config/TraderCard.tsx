"use client";

import { motion } from "framer-motion";
import { Eye, Pencil, Square, Trash2 } from "lucide-react";

interface TraderCardProps {
  name: string;
  model: string;
  exchange: string;
  status: "running" | "stopped" | "error";
  onView: () => void;
  onEdit: () => void;
  onStop: () => void;
  onDelete: () => void;
}

const statusConfig = {
  running: {
    label: "RUNNING",
    bg: "bg-emerald-500/15",
    border: "border-emerald-500/25",
    text: "text-emerald-400",
    dot: "bg-emerald-400",
    glow: "0 0 6px rgba(16,185,129,0.5)",
  },
  stopped: {
    label: "STOPPED",
    bg: "bg-zinc-500/15",
    border: "border-zinc-500/25",
    text: "text-zinc-400",
    dot: "bg-zinc-500",
    glow: "none",
  },
  error: {
    label: "ERROR",
    bg: "bg-red-500/15",
    border: "border-red-500/25",
    text: "text-red-400",
    dot: "bg-red-400",
    glow: "0 0 6px rgba(239,68,68,0.5)",
  },
};

export function TraderCard({
  name,
  model,
  exchange,
  status,
  onView,
  onEdit,
  onStop,
  onDelete,
}: TraderCardProps) {
  const cfg = statusConfig[status];

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
        <div className="flex items-center gap-2">
          <span className="text-sm">🤖</span>
          <h3
            className="text-sm font-semibold text-white"
            style={{ fontFamily: "Outfit, sans-serif" }}
          >
            {name}
          </h3>
        </div>

        {/* Status badge */}
        <span
          className={`text-[9px] px-2 py-0.5 rounded-full font-bold tracking-wider border ${cfg.bg} ${cfg.border} ${cfg.text}`}
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          <span
            className={`inline-block w-1.5 h-1.5 rounded-full mr-1.5 ${cfg.dot}`}
            style={{ boxShadow: cfg.glow }}
          />
          {cfg.label}
        </span>
      </div>

      {/* Model + Exchange info */}
      <p
        className="text-[11px] text-zinc-400 mb-4"
        style={{ fontFamily: "JetBrains Mono, monospace" }}
      >
        {model} &bull; {exchange}
      </p>

      {/* Action buttons */}
      <div className="flex items-center gap-2">
        <button
          onClick={onView}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.04] border border-white/[0.06] text-[10px] text-zinc-400 hover:text-white hover:bg-white/[0.08] hover:border-white/[0.12] transition-all"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
          title="View trader"
        >
          <Eye className="w-3 h-3" />
          View
        </button>
        <button
          onClick={onEdit}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.04] border border-white/[0.06] text-[10px] text-zinc-400 hover:text-white hover:bg-white/[0.08] hover:border-white/[0.12] transition-all"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
          title="Edit trader"
        >
          <Pencil className="w-3 h-3" />
          Edit
        </button>
        <button
          onClick={onStop}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[10px] transition-all ${
            status === "running"
              ? "bg-amber-500/10 border-amber-500/20 text-amber-400 hover:bg-amber-500/20"
              : "bg-emerald-500/10 border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20"
          }`}
          style={{ fontFamily: "JetBrains Mono, monospace" }}
          title={status === "running" ? "Stop trader" : "Start trader"}
        >
          <Square className="w-3 h-3" />
          {status === "running" ? "Stop" : "Start"}
        </button>
        <button
          onClick={onDelete}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/10 border border-red-500/20 text-[10px] text-red-400 hover:bg-red-500/20 transition-all ml-auto"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
          title="Delete trader"
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
    </motion.div>
  );
}
