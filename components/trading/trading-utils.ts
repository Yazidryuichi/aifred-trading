import type { ReactNode } from "react";
import {
  TrendingUp,
  TrendingDown,
  Activity,
  Shield,
  Zap,
  Wifi,
  Play,
  Square,
  Radio,
  AlertTriangle,
  Brain,
} from "lucide-react";
import { createElement } from "react";
import { getConnectedBrokers as fetchBrokerStatus, type BrokerStatus } from "@/lib/credential-store";

// ─── Types ────────────────────────────────────────────────────
export interface TradingData {
  summary: {
    totalPnl: number;
    winRate: number;
    totalTrades: number;
    openPositions: number;
    sharpeRatio: number;
    maxDrawdown: number;
    profitFactor: number;
    avgWin: number;
    avgLoss: number;
    totalFees: number;
    currentEquity: number;
  };
  equityCurve: { date: string; value: number }[];
  byAsset: { asset: string; pnl: number; trades: number; winRate: number }[];
  byStrategy: {
    strategy: string;
    pnl: number;
    trades: number;
    winRate: number;
  }[];
  byTier: { tier: string; pnl: number; trades: number; winRate: number }[];
  recentTrades: Record<string, unknown>[];
  openPositions: Record<string, unknown>[];
}

// ─── Activity Types ──────────────────────────────────────────
export interface ActivityEntry {
  id: string;
  timestamp: string;
  type:
    | "trade_executed"
    | "trade_closed"
    | "signal_generated"
    | "signal_rejected"
    | "broker_connected"
    | "broker_disconnected"
    | "system_start"
    | "system_stop"
    | "error"
    | "optimization"
    | "scan_complete";
  severity: "info" | "success" | "warning" | "error";
  title: string;
  message: string;
  details?: {
    asset?: string;
    side?: "LONG" | "SHORT";
    strategy?: string;
    confidence?: number;
    entry_price?: number;
    stop_loss?: number;
    take_profit?: number;
    pnl?: number;
    reasoning?: string;
    technical_signals?: string;
    sentiment_signals?: string;
    risk_assessment?: string;
    broker?: string;
    tier?: string;
    mode?: "live" | "paper";
  };
}

// ─── Connected broker type (mirrors TradingSettings) ────────
export interface ConnectedBrokerInfo {
  id: string;
  name: string;
  status: "connected" | "disconnected" | "error";
}

// ─── Execute Trade Result type ───────────────────────────────
export interface TradeResult {
  success: boolean;
  orderId?: string;
  symbol?: string;
  side?: string;
  quantity?: number;
  executionPrice?: number;
  stopLoss?: number;
  takeProfit?: number;
  riskReward?: number;
  broker?: string;
  strategy?: string;
  confidence?: number;
  tier?: string;
  mode?: "live" | "paper";
  fee?: number;
  orderStatus?: string;
  reasoning?: string;
  technicalSignals?: string;
  sentimentSignals?: string;
  riskAssessment?: string;
  status?: string;
  message?: string;
}

// ─── Paper Status Types ──────────────────────────────────────
export interface PaperStatusData {
  running: boolean;
  not_configured?: boolean;
  scanCount: number;
  lastScanTime: string | null;
  lastPrices: Record<string, number>;
  portfolioValue: number;
  positions: { asset: string; side: string; entryPrice: number; currentPrice: number; size: number; pnl: number; pnlPercent: number }[];
  totalPnl: number;
  signalsGenerated: number;
  agentStatus: Record<string, boolean>;
  startedAt: string | null;
  assets: string[];
  scanInterval: number;
  logLines: number;
  lastActivity: string | null;
  // Railway API fields
  source?: string;
  uptime?: string;
  log_available?: boolean;
  total_lines?: number;
  last_scan?: string | null;
  last_prices?: string | null;
  log_tail?: string[];
}

export interface SystemHealthData {
  overall: "healthy" | "degraded" | "down";
  timestamp: string;
  components: {
    name: string;
    status: "healthy" | "degraded" | "down";
    latencyMs: number | null;
    message: string;
  }[];
}

export interface LivePricesData {
  prices: Record<string, number | null>;
  source: string;
  cached: boolean;
  timestamp: string;
}

// ─── Regime Types ────────────────────────────────────────────
export interface RegimeApiResponse {
  success: boolean;
  symbol: string;
  currentRegime: string;
  regimeConfidence: number;
  signal: "LONG_ENTER" | "LONG_HOLD" | "EXIT" | "CASH";
  confirmations: { name: string; passed: boolean; value: number; threshold: string }[];
  confirmationsPassed: number;
  confirmationsRequired: number;
  regimeProbabilities: Record<string, number>;
  currentPrice: number;
  timestamp: string;
  error?: string;
}

export interface BacktestApiResponse {
  success: boolean;
  config: {
    symbol: string;
    startDate: string;
    endDate: string;
    initialCapital: number;
    leverage: number;
    requiredConfirmations: number;
    cooldownHours: number;
  };
  trades: {
    entryDate: string;
    exitDate: string;
    entryPrice: number;
    exitPrice: number;
    side: string;
    pnl: number;
    pnlPercent: number;
    regime: string;
    confirmationsPassed: number;
    holdDurationHours: number;
    exitReason: string;
  }[];
  metrics: {
    totalReturn: number;
    alpha: number;
    buyAndHoldReturn: number;
    winRate: number;
    totalTrades: number;
    winningTrades: number;
    losingTrades: number;
    maxDrawdown: number;
    sharpeRatio: number;
    avgTradeReturn: number;
    avgHoldDuration: number;
    finalEquity: number;
    peakEquity: number;
  };
  equityCurve: { date: string; equity: number; regime: string }[];
  regimeBreakdown: { regime: string; count: number; avgReturn: number; percentage: number }[];
  error?: string;
}

// ─── Utility Functions ───────────────────────────────────────
export function getConnectedBrokers(): ConnectedBrokerInfo[] {
  if (typeof window === "undefined") return [];
  const BROKER_NAMES: Record<string, string> = {
    alpaca: "Alpaca",
    binance: "Binance",
    coinbase: "Coinbase Advanced Trade",
    kraken: "Kraken",
    bybit: "Bybit",
    oanda: "OANDA",
    interactive_brokers: "Interactive Brokers",
    metatrader: "MetaTrader 5",
    bloomberg: "Bloomberg Terminal",
  };
  const results: ConnectedBrokerInfo[] = [];
  const seen = new Set<string>();

  // Source 1: server-side broker status (fetched async elsewhere, checked via localStorage cache)
  try {
    const cached = localStorage.getItem("aifred_broker_status");
    if (cached) {
      const brokers: BrokerStatus[] = JSON.parse(cached);
      for (const b of brokers) {
        if (!seen.has(b.id)) {
          seen.add(b.id);
          results.push({ id: b.id, name: b.name, status: "connected" });
        }
      }
    }
  } catch { /* ignore */ }

  // Source 2: legacy broker connections (backward compat)
  try {
    const raw = localStorage.getItem("aifred_broker_connections");
    if (raw) {
      const connections: Record<string, { connected?: boolean; status?: string }> = JSON.parse(raw);
      for (const [id, v] of Object.entries(connections)) {
        if ((v.connected || v.status === "connected") && !seen.has(id)) {
          seen.add(id);
          results.push({ id, name: BROKER_NAMES[id] || id, status: "connected" });
        }
      }
    }
  } catch { /* ignore */ }

  return results;
}

/** Determine the trade mode from an activity entry (backward compat) */
export function getEntryMode(entry: ActivityEntry): "live" | "paper" {
  if (entry.details?.mode) return entry.details.mode;
  if (entry.type === "trade_executed" && entry.details?.broker && entry.details.broker !== "paper") {
    return "live";
  }
  return "paper";
}

export function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function fmt(n: number, prefix = "$") {
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `${prefix}${(n / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `${prefix}${(n / 1_000).toFixed(1)}K`;
  return `${prefix}${n.toFixed(2)}`;
}

export function pct(n: number) {
  return `${n.toFixed(2)}%`;
}

/** Normalize Railway API response to match expected PaperStatusData shape */
export function normalizePaperStatus(raw: Record<string, unknown>): PaperStatusData {
  // If it already has the expected shape (local API), return as-is
  if (raw.portfolioValue !== undefined) return raw as unknown as PaperStatusData;

  // If backend is not configured, return minimal data with flag
  if (raw.not_configured) {
    return {
      running: false,
      not_configured: true,
      scanCount: 0,
      lastScanTime: null,
      lastPrices: {},
      portfolioValue: 0,
      positions: [],
      totalPnl: 0,
      signalsGenerated: 0,
      agentStatus: {},
      startedAt: null,
      assets: [],
      scanInterval: 0,
      logLines: 0,
      lastActivity: null,
      source: "not_configured",
    };
  }

  // Railway shape — extract what we can from log data
  const logTail = (raw.log_tail as string[]) || [];
  const totalLines = (raw.total_lines as number) || 0;

  // Count scans from log
  const scanLines = logTail.filter((l: string) => l.includes("=== Paper Scan"));
  const signalLines = logTail.filter((l: string) => l.includes("On-chain signal") || l.includes("signal for"));

  return {
    running: !!(raw.running || raw.log_available),
    scanCount: scanLines.length,
    lastScanTime: (() => {
      const scan = raw.last_scan as string;
      if (!scan) return null;
      // Extract timestamp from log line like "2026-03-30 13:27:53 | INFO | ..."
      const match = scan.match(/^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})/);
      return match ? match[1] : null;
    })(),
    lastPrices: {},
    portfolioValue: 10000,
    positions: [],
    totalPnl: 0,
    signalsGenerated: signalLines.length,
    agentStatus: {},
    startedAt: null,
    assets: ["ETH", "BTC"],
    scanInterval: 60,
    logLines: totalLines,
    lastActivity: logTail.length > 0 ? logTail[logTail.length - 1] : null,
    source: raw.source as string,
    uptime: raw.uptime as string,
  };
}

// ─── Constants ───────────────────────────────────────────────
export const STRATEGY_LABELS: Record<string, string> = {
  mean_reversion: "Mean Reversion",
  ict_confluence: "ICT Confluence",
  lstm_ensemble: "LSTM Ensemble",
  transformer: "Transformer",
  sentiment_breakout: "Sentiment Breakout",
};

export const TIER_COLORS: Record<string, string> = {
  "A+": "#f59e0b",
  A: "#10b981",
  B: "#6366f1",
  C: "#ef4444",
};

export const AVAILABLE_SYMBOLS = [
  // Coinbase USD pairs (recommended for Coinbase)
  "BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD", "XRP/USD", "ADA/USD", "AVAX/USD",
  // Binance USDT pairs
  "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
  "ADA/USDT", "DOGE/USDT", "AVAX/USDT",
  // Forex
  "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD",
  // Stocks
  "AAPL", "MSFT", "TSLA", "NVDA", "GOOGL", "AMZN", "META",
];

export const INJECTED_STYLES = `
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Outfit:wght@300;400;500;600;700;800;900&display=swap');

@keyframes pulse-glow {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}
@keyframes scan-line {
  0% { transform: translateY(-100%); }
  100% { transform: translateY(100vh); }
}
@keyframes ticker {
  0% { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}
.glow-green { text-shadow: 0 0 20px rgba(16, 185, 129, 0.5); }
.glow-red { text-shadow: 0 0 20px rgba(239, 68, 68, 0.4); }
.glow-gold { text-shadow: 0 0 20px rgba(245, 158, 11, 0.5); }
.card-glass {
  background: linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255,255,255,0.06);
}
.card-glass:hover {
  border-color: rgba(255,255,255,0.12);
}
.noise-bg {
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.03'/%3E%3C/svg%3E");
}
`;

export const SEVERITY_DOT: Record<string, string> = {
  info: "bg-blue-400",
  success: "bg-emerald-400",
  warning: "bg-amber-400",
  error: "bg-red-400",
};

export const ACTIVITY_TYPE_CONFIG: Record<
  ActivityEntry["type"],
  { icon: ReactNode; color: string }
> = {
  trade_executed: {
    icon: createElement(TrendingUp, { className: "w-4 h-4" }),
    color: "text-emerald-400",
  },
  trade_closed: {
    icon: createElement(TrendingDown, { className: "w-4 h-4" }),
    color: "text-zinc-400",
  },
  signal_generated: {
    icon: createElement(Zap, { className: "w-4 h-4" }),
    color: "text-amber-400",
  },
  signal_rejected: {
    icon: createElement(Shield, { className: "w-4 h-4" }),
    color: "text-red-400",
  },
  broker_connected: {
    icon: createElement(Wifi, { className: "w-4 h-4" }),
    color: "text-emerald-400",
  },
  broker_disconnected: {
    icon: createElement(Wifi, { className: "w-4 h-4" }),
    color: "text-red-400",
  },
  system_start: {
    icon: createElement(Play, { className: "w-4 h-4" }),
    color: "text-emerald-400",
  },
  system_stop: {
    icon: createElement(Square, { className: "w-4 h-4" }),
    color: "text-red-400",
  },
  scan_complete: {
    icon: createElement(Radio, { className: "w-4 h-4" }),
    color: "text-blue-400",
  },
  error: {
    icon: createElement(AlertTriangle, { className: "w-4 h-4" }),
    color: "text-red-400",
  },
  optimization: {
    icon: createElement(Brain, { className: "w-4 h-4" }),
    color: "text-purple-400",
  },
};

export const REGIME_DISPLAY: Record<string, { label: string; color: string; bg: string }> = {
  strong_bull: { label: "Strong Bull Run", color: "text-emerald-300", bg: "bg-emerald-500/20 border-emerald-500/30" },
  bull: { label: "Bull Trend", color: "text-emerald-400", bg: "bg-emerald-500/15 border-emerald-500/25" },
  weak_bull: { label: "Moderate Bull", color: "text-green-300", bg: "bg-green-500/15 border-green-500/25" },
  neutral: { label: "Sideways", color: "text-yellow-300", bg: "bg-yellow-500/15 border-yellow-500/25" },
  weak_bear: { label: "Choppy", color: "text-orange-300", bg: "bg-orange-500/15 border-orange-500/25" },
  bear: { label: "Bear Trend", color: "text-red-400", bg: "bg-red-500/15 border-red-500/25" },
  crash: { label: "Crash", color: "text-red-300", bg: "bg-red-600/20 border-red-600/30" },
};

export const REGIME_BAR_COLORS: Record<string, string> = {
  strong_bull: "bg-emerald-400",
  bull: "bg-emerald-500",
  weak_bull: "bg-green-400",
  neutral: "bg-yellow-400",
  weak_bear: "bg-orange-400",
  bear: "bg-red-400",
  crash: "bg-red-600",
};

export const SIGNAL_DISPLAY: Record<string, { label: string; color: string; icon: string }> = {
  LONG_ENTER: { label: "LONG ENTER", color: "text-emerald-400", icon: "arrow-up" },
  LONG_HOLD: { label: "LONG HOLD", color: "text-blue-400", icon: "pause" },
  EXIT: { label: "EXIT", color: "text-red-400", icon: "arrow-down" },
  CASH: { label: "CASH", color: "text-zinc-400", icon: "minus" },
};

// Re-export fetchBrokerStatus for use in ExecuteTradeModal
export { fetchBrokerStatus };
