import { NextResponse } from "next/server";
import { loadStats } from "@/lib/strategy-learning";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const stats = loadStats();

    // Sort by win rate descending
    const sorted = [...stats].sort((a, b) => b.ema_win_rate - a.ema_win_rate);

    // Compute selection probabilities
    const weights = sorted.map(s => Math.exp(Math.max(0.40, s.ema_win_rate) * 3));
    const sum = weights.reduce((a, b) => a + b, 0);
    const probabilities = weights.map(w => w / sum);

    const enriched = sorted.map((s, i) => ({
      ...s,
      selection_probability: Math.round(probabilities[i] * 100),
      rank: i + 1,
    }));

    return NextResponse.json({
      success: true,
      stats: enriched,
      total_trades: stats.reduce((a, s) => a + s.total_trades, 0),
      overall_win_rate: stats.reduce((a, s) => a + s.winning_trades, 0) / Math.max(1, stats.reduce((a, s) => a + s.total_trades, 0)),
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    return NextResponse.json({ success: false, error: "Failed to load stats" }, { status: 500 });
  }
}
