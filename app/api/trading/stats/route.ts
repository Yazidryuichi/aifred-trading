import { NextResponse } from "next/server";
import { join } from "path";
import { readJsonWithFallback } from "@/lib/file-lock";

export const dynamic = "force-dynamic";

const TRADING_DATA = join(process.cwd(), "data", "trading-data.json");

interface Trade {
  id: number;
  asset: string;
  side: string;
  direction?: string;
  pnl: number;
  fees: number;
  entry_time: string;
  exit_time: string;
  [key: string]: unknown;
}

interface TradingData {
  summary?: {
    totalPnl?: number;
    winRate?: number;
    totalTrades?: number;
    sharpeRatio?: number | null;
    sortinoRatio?: number | null;
    maxDrawdown?: number;
    profitFactor?: number;
    avgWin?: number;
    avgLoss?: number;
    totalFees?: number;
    currentEquity?: number;
  };
  recentTrades?: Trade[];
}

function computeStats(trades: Trade[]) {
  if (trades.length === 0) {
    return {
      totalTrades: 0,
      winRate: 0,
      totalPnl: 0,
      profitFactor: 0,
      plRatio: 0,
      sharpeRatio: null,
      sortinoRatio: null,
      maxDrawdown: 0,
      avgWin: 0,
      avgLoss: 0,
      netPnl: 0,
      longStats: { trades: 0, winRate: 0, totalPnl: 0, avgPnl: 0 },
      shortStats: { trades: 0, winRate: 0, totalPnl: 0, avgPnl: 0 },
      symbolPerformance: [],
    };
  }

  const wins = trades.filter((t) => t.pnl > 0);
  const losses = trades.filter((t) => t.pnl <= 0);

  const totalPnl = trades.reduce((sum, t) => sum + t.pnl, 0);
  const totalFees = trades.reduce((sum, t) => sum + (t.fees ?? 0), 0);
  const netPnl = totalPnl - totalFees;

  const grossProfit = wins.reduce((sum, t) => sum + t.pnl, 0);
  const grossLoss = Math.abs(losses.reduce((sum, t) => sum + t.pnl, 0));

  const avgWin = wins.length > 0 ? grossProfit / wins.length : 0;
  const avgLoss = losses.length > 0 ? grossLoss / losses.length : 0;
  const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0;
  const plRatio = avgLoss > 0 ? avgWin / avgLoss : avgWin > 0 ? Infinity : 0;

  // Aggregate trades to daily returns for Sharpe/Sortino
  const RISK_FREE_RATE = 0.05; // annual
  const dailyRf = RISK_FREE_RATE / 252;
  const MIN_OBSERVATIONS = 30;

  // Build daily PnL map from trade exit times
  const dailyPnlMap = new Map<string, number>();
  const sortedTrades = [...trades].sort(
    (a, b) => new Date(a.exit_time || a.entry_time).getTime() - new Date(b.exit_time || b.entry_time).getTime()
  );
  for (const t of sortedTrades) {
    const date = (t.exit_time || t.entry_time || "").slice(0, 10);
    if (date) {
      dailyPnlMap.set(date, (dailyPnlMap.get(date) ?? 0) + t.pnl);
    }
  }

  // Convert daily PnL to daily returns using a running equity
  const dailyDates = Array.from(dailyPnlMap.keys()).sort();
  const dailyReturns: number[] = [];
  let runningEquity = 100_000; // starting equity assumption
  for (const date of dailyDates) {
    const pnl = dailyPnlMap.get(date) ?? 0;
    if (runningEquity > 0) {
      dailyReturns.push(pnl / runningEquity);
    }
    runningEquity += pnl;
  }

  // Sharpe ratio (annualized, daily returns with risk-free rate)
  let sharpeRatio: number | null = null;
  if (dailyReturns.length >= MIN_OBSERVATIONS) {
    const excess = dailyReturns.map((r) => r - dailyRf);
    const meanExcess = excess.reduce((s, r) => s + r, 0) / excess.length;
    const variance = excess.reduce((s, r) => s + (r - meanExcess) ** 2, 0) / (excess.length - 1);
    const stdExcess = Math.sqrt(variance);
    sharpeRatio = stdExcess > 0 ? (meanExcess / stdExcess) * Math.sqrt(252) : 0;
  }

  // Sortino ratio (annualized, downside deviation only)
  let sortinoRatio: number | null = null;
  if (dailyReturns.length >= MIN_OBSERVATIONS) {
    const excess = dailyReturns.map((r) => r - dailyRf);
    const meanExcess = excess.reduce((s, r) => s + r, 0) / excess.length;
    const downside = excess.filter((r) => r < 0);
    if (downside.length > 0) {
      const downsideVar = downside.reduce((s, r) => s + r ** 2, 0) / downside.length;
      const downsideStd = Math.sqrt(downsideVar);
      sortinoRatio = downsideStd > 0 ? (meanExcess / downsideStd) * Math.sqrt(252) : 0;
    } else {
      sortinoRatio = meanExcess > 0 ? Infinity : 0;
    }
  }

  // Max drawdown (from cumulative PnL)
  let peak = 0;
  let maxDd = 0;
  let cumulative = 0;
  for (const t of trades) {
    cumulative += t.pnl;
    if (cumulative > peak) peak = cumulative;
    const dd = peak - cumulative;
    if (dd > maxDd) maxDd = dd;
  }
  const maxDrawdown = peak > 0 ? (maxDd / peak) * 100 : 0;

  // Long / Short breakdown
  function sideStats(side: string) {
    const sideTrades = trades.filter(
      (t) =>
        (t.side ?? t.direction ?? "").toUpperCase() === side.toUpperCase(),
    );
    const sideWins = sideTrades.filter((t) => t.pnl > 0);
    const sidePnl = sideTrades.reduce((s, t) => s + t.pnl, 0);
    return {
      trades: sideTrades.length,
      winRate:
        sideTrades.length > 0
          ? Math.round((sideWins.length / sideTrades.length) * 1000) / 10
          : 0,
      totalPnl: Math.round(sidePnl * 100) / 100,
      avgPnl:
        sideTrades.length > 0
          ? Math.round((sidePnl / sideTrades.length) * 100) / 100
          : 0,
    };
  }

  // Symbol performance
  const symbolMap = new Map<
    string,
    { trades: number; wins: number; pnl: number }
  >();
  for (const t of trades) {
    const sym = t.asset ?? "UNKNOWN";
    const entry = symbolMap.get(sym) ?? { trades: 0, wins: 0, pnl: 0 };
    entry.trades++;
    if (t.pnl > 0) entry.wins++;
    entry.pnl += t.pnl;
    symbolMap.set(sym, entry);
  }

  const symbolPerformance = Array.from(symbolMap.entries())
    .map(([symbol, data]) => ({
      symbol,
      trades: data.trades,
      winRate:
        data.trades > 0
          ? Math.round((data.wins / data.trades) * 1000) / 10
          : 0,
      pnl: Math.round(data.pnl * 100) / 100,
    }))
    .sort((a, b) => b.pnl - a.pnl);

  return {
    totalTrades: trades.length,
    winRate:
      Math.round((wins.length / trades.length) * 1000) / 10,
    totalPnl: Math.round(totalPnl * 100) / 100,
    profitFactor:
      profitFactor === Infinity
        ? 999
        : Math.round(profitFactor * 100) / 100,
    plRatio:
      plRatio === Infinity ? 999 : Math.round(plRatio * 100) / 100,
    sharpeRatio: sharpeRatio !== null ? Math.round(sharpeRatio * 100) / 100 : null,
    sortinoRatio: sortinoRatio !== null && isFinite(sortinoRatio) ? Math.round(sortinoRatio * 100) / 100 : null,
    maxDrawdown: Math.round(maxDrawdown * 100) / 100,
    avgWin: Math.round(avgWin * 100) / 100,
    avgLoss: Math.round(avgLoss * 100) / 100,
    netPnl: Math.round(netPnl * 100) / 100,
    longStats: sideStats("LONG"),
    shortStats: sideStats("SHORT"),
    symbolPerformance,
  };
}

export async function GET() {
  try {
    const tradingData = readJsonWithFallback<TradingData>(
      [TRADING_DATA],
      { recentTrades: [] },
    );

    const trades = tradingData.recentTrades ?? [];
    const computed = computeStats(trades);

    return NextResponse.json({
      success: true,
      ...computed,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Trading stats error:", error);
    return NextResponse.json(
      { success: false, error: "Failed to compute trading stats" },
      { status: 500 },
    );
  }
}
