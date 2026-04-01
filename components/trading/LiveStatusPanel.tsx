"use client";

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Zap,
  Radio,
  Server,
  RefreshCw,
  Loader2,
  Circle,
} from "lucide-react";
import {
  type PaperStatusData,
  type SystemHealthData,
  type LivePricesData,
  normalizePaperStatus,
  timeAgo,
} from "@/components/trading/trading-utils";

export function LiveStatusPanel() {
  const [paperStatus, setPaperStatus] = useState<PaperStatusData | null>(null);
  const [systemHealth, setSystemHealth] = useState<SystemHealthData | null>(null);
  const [livePrices, setLivePrices] = useState<LivePricesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const fetchAll = useCallback(() => {
    const safeFetchJson = (url: string) =>
      fetch(url).then((r) => r.json()).catch(() => null);

    Promise.allSettled([
      safeFetchJson("/api/trading/paper-status"),
      safeFetchJson("/api/trading/system-health"),
      safeFetchJson("/api/trading/live-prices"),
    ]).then(([paperRes, healthRes, pricesRes]) => {
      if (paperRes.status === "fulfilled") setPaperStatus(normalizePaperStatus(paperRes.value));
      if (healthRes.status === "fulfilled") setSystemHealth(healthRes.value);
      if (pricesRes.status === "fulfilled") setLivePrices(pricesRes.value);
      setLoading(false);
      setLastRefresh(new Date());
    });
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 10_000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const HEALTH_COLORS: Record<string, { dot: string; text: string; bg: string }> = {
    healthy: { dot: "bg-emerald-400", text: "text-emerald-400", bg: "bg-emerald-500/10" },
    degraded: { dot: "bg-amber-400", text: "text-amber-400", bg: "bg-amber-500/10" },
    down: { dot: "bg-red-400", text: "text-red-400", bg: "bg-red-500/10" },
  };

  if (loading) {
    return (
      <motion.div
        initial={false}
        animate={{ opacity: 1, y: 0 }}
        className="card-glass rounded-2xl p-6"
      >
        <div className="flex items-center gap-3">
          <Loader2 className="w-4 h-4 text-zinc-500 animate-spin" />
          <span className="text-xs text-zinc-500" style={{ fontFamily: "JetBrains Mono, monospace" }}>
            Loading live status...
          </span>
        </div>
      </motion.div>
    );
  }

  const btcPrice = livePrices?.prices?.BTC;
  const ethPrice = livePrices?.prices?.ETH;
  const solPrice = livePrices?.prices?.SOL;

  return (
    <motion.div
      initial={false}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.05 }}
      className="space-y-4"
    >
      {/* ─── Section Label ──────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span
            className="text-[10px] text-emerald-400/80 bg-emerald-500/10 border border-emerald-500/15 px-2.5 py-1 rounded-lg tracking-wider uppercase font-medium"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            Live System Status
          </span>
          {paperStatus?.running && (
            <span className="flex items-center gap-1.5">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
              </span>
              <span className="text-[10px] text-emerald-400" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                RUNNING
              </span>
            </span>
          )}
          {paperStatus && !paperStatus.running && (
            <span className="flex items-center gap-1.5">
              <Circle className={`w-2 h-2 ${paperStatus.not_configured ? "text-amber-400 fill-amber-400" : "text-red-400 fill-red-400"}`} />
              <span className={`text-[10px] ${paperStatus.not_configured ? "text-amber-400" : "text-red-400"}`} style={{ fontFamily: "JetBrains Mono, monospace" }}>
                {paperStatus.not_configured ? "STANDALONE" : "STOPPED"}
              </span>
            </span>
          )}
        </div>
        <button
          onClick={fetchAll}
          className="flex items-center gap-1.5 text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          <RefreshCw className="w-3 h-3" />
          {lastRefresh.toLocaleTimeString()}
        </button>
      </div>

      {/* ─── Main Grid ──────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* ── Paper Trading Status ────────────────────────── */}
        <div className="card-glass rounded-2xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-zinc-300 flex items-center gap-2">
              <Radio className="w-3.5 h-3.5 text-emerald-400" />
              Paper Trading
            </h3>
            {paperStatus?.scanCount != null && (
              <span
                className="text-[10px] text-zinc-600"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                Scan #{paperStatus.scanCount}
              </span>
            )}
          </div>

          {paperStatus ? (
            <div className="space-y-3">
              {/* Status row */}
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-zinc-500">Status</span>
                <span
                  className={`text-[11px] font-medium ${
                    paperStatus.running ? "text-emerald-400" :
                    paperStatus.not_configured ? "text-amber-400" : "text-red-400"
                  }`}
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  {paperStatus.running ? "Active" : paperStatus.not_configured ? "Standalone" : "Inactive"}
                </span>
              </div>
              {paperStatus.not_configured && (
                <div className="text-[10px] text-amber-400/60 leading-tight">
                  Python backend not connected. Trading via Next.js API routes.
                </div>
              )}

              {/* Portfolio */}
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-zinc-500">Portfolio</span>
                <span
                  className="text-[11px] text-zinc-300 font-medium"
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  ${(paperStatus.portfolioValue ?? 0).toLocaleString()}
                </span>
              </div>

              {/* Assets */}
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-zinc-500">Monitoring</span>
                <span
                  className="text-[11px] text-zinc-400"
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  {paperStatus.assets.join(", ") || "N/A"}
                </span>
              </div>

              {/* Last Scan */}
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-zinc-500">Last Scan</span>
                <span
                  className="text-[11px] text-zinc-400"
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  {paperStatus.lastScanTime
                    ? timeAgo(paperStatus.lastScanTime.replace(" ", "T") + "Z")
                    : "N/A"}
                </span>
              </div>

              {/* Signals */}
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-zinc-500">Signals</span>
                <span
                  className="text-[11px] text-zinc-300"
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  {paperStatus.signalsGenerated}
                </span>
              </div>

              {/* Scan interval */}
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-zinc-500">Interval</span>
                <span
                  className="text-[11px] text-zinc-400"
                  style={{ fontFamily: "JetBrains Mono, monospace" }}
                >
                  {paperStatus.scanInterval}s
                </span>
              </div>

              {/* Last prices from paper log */}
              {Object.keys(paperStatus.lastPrices).length > 0 && (
                <div className="pt-2 border-t border-white/[0.04]">
                  <span className="text-[10px] text-zinc-600 uppercase tracking-wider" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                    Last Log Prices
                  </span>
                  <div className="mt-1.5 space-y-1">
                    {Object.entries(paperStatus.lastPrices).map(([asset, price]) => (
                      <div key={asset} className="flex items-center justify-between">
                        <span className="text-[11px] text-zinc-400">{asset}</span>
                        <span
                          className="text-[11px] text-zinc-300"
                          style={{ fontFamily: "JetBrains Mono, monospace" }}
                        >
                          ${(price ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-[11px] text-zinc-600">No paper trading data available</div>
          )}
        </div>

        {/* ── Live Prices ─────────────────────────────────── */}
        <div className="card-glass rounded-2xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-zinc-300 flex items-center gap-2">
              <Zap className="w-3.5 h-3.5 text-amber-400" />
              Live Prices
            </h3>
            <span
              className="text-[10px] text-zinc-600"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              {livePrices?.source === "hyperliquid-mainnet"
                ? "Hyperliquid"
                : livePrices?.source === "coingecko-fallback"
                ? "CoinGecko"
                : "Unavailable"}
            </span>
          </div>

          {livePrices && !livePrices.prices?.BTC ? (
            <div className="text-[11px] text-zinc-600">Unable to fetch prices</div>
          ) : (
            <div className="space-y-3">
              {/* BTC */}
              {btcPrice != null && (
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-amber-400">BTC</span>
                    <span className="text-[10px] text-zinc-600">Bitcoin</span>
                  </div>
                  <span
                    className="text-sm font-semibold text-zinc-200 glow-gold"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    ${btcPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </div>
              )}

              {/* ETH */}
              {ethPrice != null && (
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-blue-400">ETH</span>
                    <span className="text-[10px] text-zinc-600">Ethereum</span>
                  </div>
                  <span
                    className="text-sm font-semibold text-zinc-200"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    ${ethPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </div>
              )}

              {/* SOL */}
              {solPrice != null && (
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-purple-400">SOL</span>
                    <span className="text-[10px] text-zinc-600">Solana</span>
                  </div>
                  <span
                    className="text-sm font-semibold text-zinc-200"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    ${solPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </div>
              )}

              {/* Additional assets */}
              {livePrices?.prices && (
                <div className="pt-2 border-t border-white/[0.04] space-y-1.5">
                  {Object.entries(livePrices.prices)
                    .filter(([k]) => !["BTC", "ETH", "SOL"].includes(k))
                    .filter(([, v]) => v != null)
                    .slice(0, 6)
                    .map(([asset, price]) => (
                      <div key={asset} className="flex items-center justify-between">
                        <span className="text-[11px] text-zinc-500">{asset}</span>
                        <span
                          className="text-[11px] text-zinc-400"
                          style={{ fontFamily: "JetBrains Mono, monospace" }}
                        >
                          ${((price as number) ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: (price as number) < 1 ? 6 : 2 })}
                        </span>
                      </div>
                    ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── System Health ────────────────────────────────── */}
        <div className="card-glass rounded-2xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-zinc-300 flex items-center gap-2">
              <Server className="w-3.5 h-3.5 text-blue-400" />
              System Health
            </h3>
            {systemHealth && (
              <span
                className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${HEALTH_COLORS[systemHealth.overall]?.bg || ""} ${HEALTH_COLORS[systemHealth.overall]?.text || "text-zinc-400"}`}
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {(systemHealth.overall || "unknown").toUpperCase()}
              </span>
            )}
          </div>

          {systemHealth ? (
            <div className="space-y-2.5">
              {(systemHealth.components ?? []).map((comp) => {
                const colors = HEALTH_COLORS[comp.status] || HEALTH_COLORS.down;
                return (
                  <div key={comp.name} className="space-y-1">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className={`w-1.5 h-1.5 rounded-full ${colors.dot}`} />
                        <span className="text-[11px] text-zinc-300">{comp.name}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {comp.latencyMs != null && comp.latencyMs > 0 && (
                          <span
                            className="text-[10px] text-zinc-600"
                            style={{ fontFamily: "JetBrains Mono, monospace" }}
                          >
                            {comp.latencyMs}ms
                          </span>
                        )}
                        <span className={`text-[10px] font-medium ${colors.text}`}>
                          {comp.status === "healthy" ? "OK" : (comp.status || "unknown").toUpperCase()}
                        </span>
                      </div>
                    </div>
                    <p
                      className="text-[10px] text-zinc-600 pl-3.5 truncate"
                      style={{ fontFamily: "JetBrains Mono, monospace" }}
                      title={comp.message}
                    >
                      {comp.message}
                    </p>
                  </div>
                );
              })}

              {/* Agent status from paper log */}
              {paperStatus && Object.keys(paperStatus.agentStatus).length > 0 && (
                <div className="pt-2 border-t border-white/[0.04]">
                  <span
                    className="text-[10px] text-zinc-600 uppercase tracking-wider"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    AI Agents
                  </span>
                  <div className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-1">
                    {Object.entries(paperStatus.agentStatus).map(([agent, ok]) => (
                      <div key={agent} className="flex items-center gap-1.5">
                        <div className={`w-1.5 h-1.5 rounded-full ${ok ? "bg-emerald-400" : "bg-zinc-600"}`} />
                        <span className="text-[10px] text-zinc-500 capitalize">{agent.replace(/_/g, " ")}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-[11px] text-zinc-600">Unable to check system health</div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
