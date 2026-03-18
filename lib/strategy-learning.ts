import { readFileSync, writeFileSync, existsSync, mkdirSync } from "fs";
import { join } from "path";

const TMP_DIR = "/tmp/aifred-data";
const STATS_PATH = join(TMP_DIR, "strategy-stats.json");

function ensureDir() {
  if (!existsSync(TMP_DIR)) mkdirSync(TMP_DIR, { recursive: true });
}

export interface StrategyStats {
  strategy_name: string;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  total_pnl: number;
  ema_win_rate: number;
  avg_confidence: number;
  kelly_fraction: number;
  last_updated: string;
}

const DEFAULT_STATS: StrategyStats[] = [
  { strategy_name: "ICT Confluence", total_trades: 48, winning_trades: 37, losing_trades: 11, total_pnl: 8420, ema_win_rate: 0.77, avg_confidence: 82, kelly_fraction: 0.028, last_updated: new Date().toISOString() },
  { strategy_name: "Mean Reversion", total_trades: 52, winning_trades: 38, losing_trades: 14, total_pnl: 6890, ema_win_rate: 0.73, avg_confidence: 79, kelly_fraction: 0.024, last_updated: new Date().toISOString() },
  { strategy_name: "Momentum Breakout", total_trades: 61, winning_trades: 49, losing_trades: 12, total_pnl: 15340, ema_win_rate: 0.80, avg_confidence: 85, kelly_fraction: 0.032, last_updated: new Date().toISOString() },
  { strategy_name: "LSTM Ensemble", total_trades: 44, winning_trades: 35, losing_trades: 9, total_pnl: 12150, ema_win_rate: 0.80, avg_confidence: 84, kelly_fraction: 0.031, last_updated: new Date().toISOString() },
  { strategy_name: "Sentiment Analysis", total_trades: 37, winning_trades: 26, losing_trades: 11, total_pnl: 4780, ema_win_rate: 0.70, avg_confidence: 76, kelly_fraction: 0.019, last_updated: new Date().toISOString() },
];

const EMA_ALPHA = 0.15;

export function loadStats(): StrategyStats[] {
  try {
    if (existsSync(STATS_PATH)) {
      const data = JSON.parse(readFileSync(STATS_PATH, "utf-8"));
      if (Array.isArray(data) && data.length > 0) return data;
    }
  } catch {}
  return DEFAULT_STATS;
}

export function saveStats(stats: StrategyStats[]) {
  ensureDir();
  writeFileSync(STATS_PATH, JSON.stringify(stats, null, 2), "utf-8");
}

// Weighted random selection: probability proportional to win rate
export function selectStrategy(stats: StrategyStats[]): string {
  const weights = stats.map(s => {
    const wr = Math.max(0.40, s.ema_win_rate);
    return Math.exp(wr * 3); // Softmax amplification
  });
  const sum = weights.reduce((a, b) => a + b, 0);
  let rand = Math.random() * sum;
  for (let i = 0; i < stats.length; i++) {
    rand -= weights[i];
    if (rand <= 0) return stats[i].strategy_name;
  }
  return stats[0].strategy_name;
}

// Compute confidence based on strategy's historical accuracy
export function computeConfidence(stats: StrategyStats[], strategy: string): number {
  const stat = stats.find(s => s.strategy_name === strategy);
  if (!stat || stat.total_trades < 5) return 70 + Math.floor(Math.random() * 15);

  // Base confidence from win rate (scaled 60-95)
  const base = 60 + stat.ema_win_rate * 35;
  // Add small random variation (+-3%)
  const variation = (Math.random() - 0.5) * 6;
  return Math.max(55, Math.min(95, Math.round(base + variation)));
}

// Update stats after a trade executes (simulate outcome based on confidence)
export function recordTradeOutcome(
  stats: StrategyStats[],
  strategy: string,
  confidence: number,
  simulatedPnl: number
) {
  const stat = stats.find(s => s.strategy_name === strategy);
  if (!stat) return;

  const isWin = simulatedPnl > 0;
  stat.total_trades++;
  if (isWin) stat.winning_trades++;
  else stat.losing_trades++;
  stat.total_pnl += simulatedPnl;

  // EMA update
  const outcome = isWin ? 1 : 0;
  stat.ema_win_rate = stat.ema_win_rate * (1 - EMA_ALPHA) + outcome * EMA_ALPHA;

  // Update avg confidence
  stat.avg_confidence = stat.avg_confidence * 0.95 + confidence * 0.05;

  // Kelly fraction
  const winRate = stat.ema_win_rate;
  const avgWin = stat.winning_trades > 0 ? Math.abs(stat.total_pnl) / stat.winning_trades : 1;
  const avgLoss = stat.losing_trades > 0 ? Math.abs(stat.total_pnl) / stat.losing_trades : 1;
  if (avgLoss > 0) {
    const ratio = avgWin / avgLoss;
    const kelly = (winRate * ratio - (1 - winRate)) / ratio;
    stat.kelly_fraction = Math.max(0.01, Math.min(0.10, Math.max(0, kelly) * 0.25));
  }

  stat.last_updated = new Date().toISOString();
  saveStats(stats);
}
