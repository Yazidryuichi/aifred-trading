"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { motion } from "framer-motion";
import {
  Brain,
  Filter,
  ChevronLeft,
  ChevronRight,
  Loader2,
  ArrowLeft,
  X,
} from "lucide-react";
import Link from "next/link";
import { DecisionCard, type Decision } from "@/components/trading/DecisionCard";

// ─── Mock data generator for development ────────────────────
function generateMockDecisions(count: number): Decision[] {
  const statuses: Decision["status"][] = ["success", "success", "success", "partial", "failure"];
  const assets = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "LINKUSDT"];
  const actions: ("buy" | "sell" | "hold" | "close")[] = ["buy", "sell", "hold", "hold", "close"];

  return Array.from({ length: count }, (_, i) => {
    const cycleNum = count - i;
    const status = statuses[i % statuses.length];
    const numAssets = 2 + (i % 3);
    const selectedAssets = assets.slice(0, numAssets);
    const ts = new Date(Date.now() - i * 15 * 60_000).toISOString();

    return {
      id: `d-${String(cycleNum).padStart(4, "0")}`,
      cycleNumber: cycleNum,
      timestamp: ts,
      status,
      chainOfThought: `Cycle ${cycleNum} analysis:\n- Market conditions ${
        status === "success" ? "favorable" : status === "partial" ? "mixed" : "degraded"
      }\n- Technical signals ${i % 2 === 0 ? "aligned" : "conflicting"}\n- Risk parameters within bounds\n\nDecision executed with ${status} outcome.`,
      inputPrompt:
        i % 3 === 0
          ? `Analyze ${selectedAssets.join(", ")} on 15m timeframe. Portfolio: $10.80 USDC. Regime: ${
              i % 2 === 0 ? "consolidation" : "trending"
            }.`
          : undefined,
      assetDecisions: selectedAssets.map((asset, j) => ({
        asset,
        action: actions[(i + j) % actions.length],
        succeeded: status !== "failure" && (status !== "partial" || j !== numAssets - 1),
      })),
      durationMs: 5000 + Math.floor(Math.random() * 25000),
      agents:
        i % 2 === 0
          ? {
              technical: `RSI ${30 + Math.floor(Math.random() * 40)}, MACD ${
                i % 3 === 0 ? "bullish crossover" : "neutral"
              }`,
              sentiment: `FinBERT: ${i % 2 === 0 ? "bullish" : "neutral"} (${(0.4 + Math.random() * 0.4).toFixed(2)})`,
              risk: `Kelly: ${(Math.random() * 3).toFixed(1)}%, R:R ${(1 + Math.random() * 2).toFixed(1)}:1`,
              regime: `${
                ["Consolidation", "Bull Run", "Bear Market", "High Volatility"][i % 4]
              } (${60 + Math.floor(Math.random() * 30)}% confidence)`,
            }
          : undefined,
    };
  });
}

const ALL_MOCK = generateMockDecisions(60);

// ─── Filter types ───────────────────────────────────────────
type StatusFilter = "all" | "success" | "failure" | "partial";
type ActionFilter = "all" | "buy" | "sell" | "hold" | "close";

const PAGE_SIZE = 20;

// ─── Page Component ─────────────────────────────────────────
export default function DecisionsPage() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  // Filters
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [actionFilter, setActionFilter] = useState<ActionFilter>("all");
  const [assetFilter, setAssetFilter] = useState<string>("all");
  const [filtersOpen, setFiltersOpen] = useState(false);

  const fetchDecisions = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        limit: "200",
        ...(statusFilter !== "all" && { status: statusFilter }),
        ...(actionFilter !== "all" && { action: actionFilter }),
        ...(assetFilter !== "all" && { asset: assetFilter }),
      });
      const res = await fetch(`/api/trading/decisions?${params}`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data?.decisions) && data.decisions.length > 0) {
          setDecisions(data.decisions);
          setLoading(false);
          return;
        }
      }
    } catch {
      // API not built yet
    }
    // Fallback to mock
    setDecisions(ALL_MOCK);
    setLoading(false);
  }, [statusFilter, actionFilter, assetFilter]);

  useEffect(() => {
    fetchDecisions();
  }, [fetchDecisions]);

  // Reset page on filter change
  useEffect(() => {
    setPage(1);
  }, [statusFilter, actionFilter, assetFilter]);

  // Derived
  const filtered = useMemo(() => {
    let result = decisions;
    if (statusFilter !== "all") {
      result = result.filter((d) => d.status === statusFilter);
    }
    if (actionFilter !== "all") {
      result = result.filter((d) =>
        d.assetDecisions.some((ad) => ad.action === actionFilter)
      );
    }
    if (assetFilter !== "all") {
      result = result.filter((d) =>
        d.assetDecisions.some((ad) => ad.asset === assetFilter)
      );
    }
    return result;
  }, [decisions, statusFilter, actionFilter, assetFilter]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageDecisions = filtered.slice(
    (page - 1) * PAGE_SIZE,
    page * PAGE_SIZE
  );

  // Unique assets for filter
  const allAssets = useMemo(() => {
    const set = new Set<string>();
    decisions.forEach((d) => d.assetDecisions.forEach((ad) => set.add(ad.asset)));
    return Array.from(set).sort();
  }, [decisions]);

  const hasActiveFilters =
    statusFilter !== "all" || actionFilter !== "all" || assetFilter !== "all";

  return (
    <div className="min-h-screen bg-[#0a0a0a]">
      {/* ── Top Bar ────────────────────────────────────── */}
      <div className="border-b border-white/10 px-4 py-3">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/trading"
              className="text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <h1
                className="text-lg font-bold text-white flex items-center gap-2"
                style={{ fontFamily: "Outfit, sans-serif" }}
              >
                <Brain className="w-5 h-5 text-purple-400" />
                Decision History
              </h1>
              <p
                className="text-[10px] text-zinc-600"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {filtered.length} decisions {hasActiveFilters ? "(filtered)" : "total"}
              </p>
            </div>
          </div>

          <button
            onClick={() => setFiltersOpen((v) => !v)}
            className={`flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded-lg border transition-colors ${
              hasActiveFilters
                ? "text-purple-400 border-purple-500/30 bg-purple-500/10"
                : "text-zinc-500 border-white/[0.06] hover:text-zinc-300"
            }`}
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            <Filter className="w-3.5 h-3.5" />
            Filters
            {hasActiveFilters && (
              <span className="bg-purple-400 text-black text-[9px] font-bold rounded-full w-4 h-4 flex items-center justify-center">
                {[statusFilter, actionFilter, assetFilter].filter(
                  (f) => f !== "all"
                ).length}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* ── Filters Panel ──────────────────────────────── */}
      {filtersOpen && (
        <div className="border-b border-white/[0.06] bg-white/[0.02] px-4 py-3">
          <div className="max-w-6xl mx-auto flex flex-wrap items-center gap-4">
            {/* Status */}
            <FilterGroup label="Status">
              {(["all", "success", "failure", "partial"] as StatusFilter[]).map(
                (s) => (
                  <FilterChip
                    key={s}
                    active={statusFilter === s}
                    onClick={() => setStatusFilter(s)}
                    label={s === "all" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}
                  />
                )
              )}
            </FilterGroup>

            {/* Action */}
            <FilterGroup label="Action">
              {(["all", "buy", "sell", "hold", "close"] as ActionFilter[]).map(
                (a) => (
                  <FilterChip
                    key={a}
                    active={actionFilter === a}
                    onClick={() => setActionFilter(a)}
                    label={a === "all" ? "All" : a.charAt(0).toUpperCase() + a.slice(1)}
                  />
                )
              )}
            </FilterGroup>

            {/* Asset */}
            <FilterGroup label="Asset">
              <FilterChip
                active={assetFilter === "all"}
                onClick={() => setAssetFilter("all")}
                label="All"
              />
              {allAssets.map((a) => (
                <FilterChip
                  key={a}
                  active={assetFilter === a}
                  onClick={() => setAssetFilter(a)}
                  label={a.replace("USDT", "")}
                />
              ))}
            </FilterGroup>

            {/* Clear */}
            {hasActiveFilters && (
              <button
                onClick={() => {
                  setStatusFilter("all");
                  setActionFilter("all");
                  setAssetFilter("all");
                }}
                className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors ml-auto"
              >
                <X className="w-3 h-3" />
                Clear all
              </button>
            )}
          </div>
        </div>
      )}

      {/* ── Decision List ──────────────────────────────── */}
      <div className="max-w-6xl mx-auto px-4 py-4">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-5 h-5 text-zinc-500 animate-spin" />
            <span
              className="text-[11px] text-zinc-500 ml-2"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              Loading decision history...
            </span>
          </div>
        ) : pageDecisions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 gap-2">
            <Brain className="w-6 h-6 text-zinc-700" />
            <p className="text-[11px] text-zinc-600">
              No decisions match your filters.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {pageDecisions.map((d) => (
              <motion.div key={d.id} initial={false} animate={{ opacity: 1 }}>
                <DecisionCard decision={d} />
              </motion.div>
            ))}
          </div>
        )}

        {/* ── Pagination ────────────────────────────────── */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-6 pt-4 border-t border-white/[0.06]">
            <span
              className="text-[10px] text-zinc-600"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              Page {page} of {totalPages} ({filtered.length} decisions)
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded-lg border border-white/[0.06] text-zinc-500 hover:text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
              </button>

              {/* Page numbers */}
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                let pageNum: number;
                if (totalPages <= 5) {
                  pageNum = i + 1;
                } else if (page <= 3) {
                  pageNum = i + 1;
                } else if (page >= totalPages - 2) {
                  pageNum = totalPages - 4 + i;
                } else {
                  pageNum = page - 2 + i;
                }
                return (
                  <button
                    key={pageNum}
                    onClick={() => setPage(pageNum)}
                    className={`w-7 h-7 rounded-lg text-[10px] font-medium transition-colors ${
                      page === pageNum
                        ? "bg-purple-500/20 text-purple-400 border border-purple-500/30"
                        : "text-zinc-500 hover:text-zinc-300 border border-transparent"
                    }`}
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {pageNum}
                  </button>
                );
              })}

              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="p-1.5 rounded-lg border border-white/[0.06] text-zinc-500 hover:text-zinc-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Filter Components ──────────────────────────────────────
function FilterGroup({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="text-[10px] text-zinc-600 uppercase tracking-wider"
        style={{ fontFamily: "JetBrains Mono, monospace" }}
      >
        {label}:
      </span>
      <div className="flex items-center gap-1">{children}</div>
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
        active
          ? "text-purple-400 border-purple-500/30 bg-purple-500/10"
          : "text-zinc-500 border-white/[0.06] hover:text-zinc-300 hover:bg-white/5"
      }`}
      style={{ fontFamily: "JetBrains Mono, monospace" }}
    >
      {label}
    </button>
  );
}
