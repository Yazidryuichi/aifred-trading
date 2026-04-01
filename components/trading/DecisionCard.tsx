"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronDown,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ClipboardList,
  Bot,
  Clock,
  TrendingUp,
  TrendingDown,
  Minus,
  LogOut,
} from "lucide-react";

// ─── Types ──────────────────────────────────────────────────
export interface AssetDecision {
  asset: string;
  action: "buy" | "sell" | "hold" | "close";
  succeeded: boolean;
}

export interface AgentContributions {
  technical?: string;
  sentiment?: string;
  risk?: string;
  regime?: string;
}

export interface Decision {
  id: string;
  cycleNumber: number;
  timestamp: string;
  status: "success" | "failure" | "partial";
  inputPrompt?: string;
  chainOfThought: string;
  assetDecisions: AssetDecision[];
  durationMs: number;
  agents?: AgentContributions;
}

// ─── Helpers ────────────────────────────────────────────────
const STATUS_STYLES: Record<
  Decision["status"],
  { bg: string; text: string; label: string; icon: typeof CheckCircle2 }
> = {
  success: {
    bg: "bg-emerald-500/10 border-emerald-500/20",
    text: "text-emerald-400",
    label: "Success",
    icon: CheckCircle2,
  },
  failure: {
    bg: "bg-red-500/10 border-red-500/20",
    text: "text-red-400",
    label: "Failure",
    icon: XCircle,
  },
  partial: {
    bg: "bg-amber-500/10 border-amber-500/20",
    text: "text-amber-400",
    label: "Partial",
    icon: AlertTriangle,
  },
};

const ACTION_STYLES: Record<
  AssetDecision["action"],
  { bg: string; text: string; icon: typeof TrendingUp }
> = {
  buy: { bg: "bg-emerald-500/10", text: "text-emerald-400", icon: TrendingUp },
  sell: { bg: "bg-red-500/10", text: "text-red-400", icon: TrendingDown },
  hold: { bg: "bg-zinc-500/10", text: "text-zinc-400", icon: Minus },
  close: { bg: "bg-amber-500/10", text: "text-amber-400", icon: LogOut },
};

function formatAsset(raw: string): string {
  // "BTCUSDT" -> "BTC/USDT", "ETH-USD" stays, "SOL" stays
  if (raw.endsWith("USDT")) return raw.replace("USDT", "/USDT");
  if (raw.endsWith("USD") && !raw.includes("-"))
    return raw.replace("USD", "/USD");
  return raw;
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

// ─── Component ──────────────────────────────────────────────
export function DecisionCard({ decision }: { decision: Decision }) {
  const [promptOpen, setPromptOpen] = useState(false);
  const [cotOpen, setCotOpen] = useState(false);

  const status = STATUS_STYLES[decision.status];
  const StatusIcon = status.icon;

  return (
    <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl overflow-hidden">
      {/* ── Header ───────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-3">
          <span
            className="text-xs font-semibold text-zinc-300"
            style={{ fontFamily: "Outfit, sans-serif" }}
          >
            Cycle #{decision.cycleNumber}
          </span>
          <span
            className="text-[10px] text-zinc-500"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            {formatTimestamp(decision.timestamp)}
          </span>
        </div>
        <span
          className={`inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full border ${status.bg} ${status.text}`}
        >
          <StatusIcon className="w-3 h-3" />
          {status.label}
        </span>
      </div>

      {/* ── Expandable Sections ──────────────────────────── */}
      <div className="border-t border-white/[0.04] px-4 py-2 space-y-1">
        {/* Input Prompt */}
        {decision.inputPrompt && (
          <ExpandableSection
            icon={<ClipboardList className="w-3.5 h-3.5 text-blue-400" />}
            label="Input Prompt"
            open={promptOpen}
            onToggle={() => setPromptOpen((v) => !v)}
          >
            <pre
              className="text-[11px] text-zinc-400 whitespace-pre-wrap leading-relaxed"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              {decision.inputPrompt}
            </pre>
          </ExpandableSection>
        )}

        {/* AI Chain of Thought */}
        <ExpandableSection
          icon={<Bot className="w-3.5 h-3.5 text-purple-400" />}
          label="AI Chain of Thought"
          open={cotOpen}
          onToggle={() => setCotOpen((v) => !v)}
        >
          <div className="space-y-3">
            <pre
              className="text-[11px] text-zinc-400 whitespace-pre-wrap leading-relaxed"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              {decision.chainOfThought}
            </pre>

            {/* Agent Contributions inline */}
            {decision.agents && <AgentBreakdown agents={decision.agents} />}
          </div>
        </ExpandableSection>
      </div>

      {/* ── Asset Decisions ──────────────────────────────── */}
      <div className="border-t border-white/[0.04] px-4 py-2.5">
        <div className="flex flex-wrap gap-2">
          {decision.assetDecisions.map((ad) => {
            const actionStyle = ACTION_STYLES[ad.action];
            const ActionIcon = actionStyle.icon;
            return (
              <div
                key={ad.asset}
                className="flex items-center gap-1.5 text-[11px]"
              >
                <span
                  className="text-zinc-300 font-medium"
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  {formatAsset(ad.asset)}
                </span>
                <span
                  className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded ${actionStyle.bg} ${actionStyle.text}`}
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  <ActionIcon className="w-3 h-3" />
                  {ad.action}
                </span>
                {ad.succeeded ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                ) : (
                  <XCircle className="w-3.5 h-3.5 text-red-400" />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Footer: Duration ─────────────────────────────── */}
      <div className="border-t border-white/[0.04] px-4 py-2 flex items-center gap-1.5">
        <Clock className="w-3 h-3 text-zinc-600" />
        <span
          className="text-[10px] text-zinc-600"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          AI call duration: {decision.durationMs.toLocaleString()} ms
        </span>
      </div>
    </div>
  );
}

// ─── Expandable Section ─────────────────────────────────────
function ExpandableSection({
  icon,
  label,
  open,
  onToggle,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div>
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between py-1.5 group"
      >
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-[11px] text-zinc-400 group-hover:text-zinc-200 transition-colors">
            {label}
          </span>
        </div>
        <ChevronDown
          className={`w-3.5 h-3.5 text-zinc-600 transition-transform duration-200 ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="pb-2 pl-5">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Agent Contributions Breakdown ──────────────────────────
function AgentBreakdown({ agents }: { agents: AgentContributions }) {
  const entries: { key: string; label: string; color: string; value: string }[] =
    [];

  if (agents.technical)
    entries.push({
      key: "technical",
      label: "Technical Analysis",
      color: "text-blue-400",
      value: agents.technical,
    });
  if (agents.sentiment)
    entries.push({
      key: "sentiment",
      label: "Sentiment",
      color: "text-purple-400",
      value: agents.sentiment,
    });
  if (agents.risk)
    entries.push({
      key: "risk",
      label: "Risk Management",
      color: "text-amber-400",
      value: agents.risk,
    });
  if (agents.regime)
    entries.push({
      key: "regime",
      label: "Regime Detection",
      color: "text-emerald-400",
      value: agents.regime,
    });

  if (entries.length === 0) return null;

  return (
    <div className="border-t border-white/[0.04] pt-2 space-y-2">
      <span
        className="text-[10px] text-zinc-600 uppercase tracking-wider"
        style={{ fontFamily: "JetBrains Mono, monospace" }}
      >
        Agent Contributions
      </span>
      {entries.map((e) => (
        <div key={e.key} className="flex items-start gap-2">
          <div className={`w-1.5 h-1.5 rounded-full mt-1.5 ${e.color.replace("text-", "bg-")}`} />
          <div className="flex-1 min-w-0">
            <span className={`text-[10px] font-medium ${e.color}`}>
              {e.label}
            </span>
            <p
              className="text-[10px] text-zinc-500 mt-0.5 leading-relaxed"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              {e.value}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
