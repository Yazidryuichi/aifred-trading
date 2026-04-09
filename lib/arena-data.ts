// ─── Arena Competition Data Generator ─────────────────────────
// DISCLAIMER: This data is SIMULATED for demonstration purposes.
// It does NOT represent real trading performance or live competition results.
// Uses deterministic random walk with drift + mean reversion for equity curves.

export interface StrategyInfo {
  id: string;
  name: string;
  model: string;
  color: string;
  colorRgb: string;
  emoji: string;
  status: "active" | "paused";
  equity: number;
  pnl: number;
  pnlPercent: number;
  positions: number;
  totalTrades: number;
  winRate: number;
  sharpeRatio: number;
  maxDrawdown: number;
}

export interface DataPoint {
  time: string;
  hour: number;
  claude: number;
  deepseek: number;
  gemini: number;
}

// Seeded pseudo-random for deterministic output
function seededRandom(seed: number) {
  let s = seed;
  return () => {
    s = (s * 16807 + 0) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

function generateEquityCurve(
  points: number,
  drift: number,
  volatility: number,
  meanReversion: number,
  seed: number
): number[] {
  const rand = seededRandom(seed);
  const curve: number[] = [0];

  for (let i = 1; i < points; i++) {
    const prev = curve[i - 1];
    // Box-Muller for normal distribution
    const u1 = rand();
    const u2 = rand();
    const normal = Math.sqrt(-2 * Math.log(u1 || 0.001)) * Math.cos(2 * Math.PI * u2);

    // Mean-reverting random walk with drift
    const reversion = -meanReversion * prev * 0.001;
    const step = drift + reversion + volatility * normal;

    // Add occasional drawdowns (every ~150 hours)
    let drawdown = 0;
    if (rand() < 0.007) {
      drawdown = -volatility * (2 + rand() * 4);
    }

    curve.push(prev + step + drawdown);
  }

  return curve;
}

function scaleToTarget(curve: number[], target: number): number[] {
  const finalVal = curve[curve.length - 1];
  if (Math.abs(finalVal) < 0.001) return curve.map(() => 0);
  const scale = target / finalVal;
  return curve.map((v) => v * scale);
}

export function generateCompetitionData(): {
  strategies: StrategyInfo[];
  performanceData: DataPoint[];
} {
  const POINTS = 720; // 30 days * 24 hours
  const startDate = new Date("2026-03-02T00:00:00Z");

  // Generate raw curves
  const claudeRaw = generateEquityCurve(POINTS, 0.08, 0.6, 0.3, 42);
  const deepseekRaw = generateEquityCurve(POINTS, 0.07, 1.0, 0.2, 137);
  const geminiRaw = generateEquityCurve(POINTS, 0.04, 0.35, 0.4, 256);

  // Scale to target PnL %
  const claude = scaleToTarget(claudeRaw, 54.6);
  const deepseek = scaleToTarget(deepseekRaw, 41.2);
  const gemini = scaleToTarget(geminiRaw, 28.7);

  // Build time-series data
  const performanceData: DataPoint[] = [];
  for (let i = 0; i < POINTS; i++) {
    const t = new Date(startDate.getTime() + i * 3600000);
    performanceData.push({
      time: t.toISOString(),
      hour: i,
      claude: Math.round(claude[i] * 100) / 100,
      deepseek: Math.round(deepseek[i] * 100) / 100,
      gemini: Math.round(gemini[i] * 100) / 100,
    });
  }

  // Strategy metadata
  const BASE_EQUITY = 100000;
  const strategies: StrategyInfo[] = [
    {
      id: "claude-ensemble",
      name: "Claude Ensemble",
      model: "Claude Opus 4",
      color: "emerald",
      colorRgb: "16, 185, 129",
      emoji: "\u{1F916}",
      status: "active",
      equity: Math.round(BASE_EQUITY * (1 + 54.6 / 100)),
      pnl: Math.round(BASE_EQUITY * 54.6 / 100),
      pnlPercent: 54.6,
      positions: 3,
      totalTrades: 187,
      winRate: 68.4,
      sharpeRatio: 2.31,
      maxDrawdown: 8.2,
    },
    {
      id: "deepseek-momentum",
      name: "DeepSeek Momentum",
      model: "DeepSeek V3",
      color: "blue",
      colorRgb: "59, 130, 246",
      emoji: "\u{1F9E0}",
      status: "active",
      equity: Math.round(BASE_EQUITY * (1 + 41.2 / 100)),
      pnl: Math.round(BASE_EQUITY * 41.2 / 100),
      pnlPercent: 41.2,
      positions: 5,
      totalTrades: 312,
      winRate: 57.1,
      sharpeRatio: 1.87,
      maxDrawdown: 14.6,
    },
    {
      id: "gemini-balanced",
      name: "Gemini Balanced",
      model: "Gemini 2.5 Pro",
      color: "purple",
      colorRgb: "168, 85, 247",
      emoji: "\u{2728}",
      status: "active",
      equity: Math.round(BASE_EQUITY * (1 + 28.7 / 100)),
      pnl: Math.round(BASE_EQUITY * 28.7 / 100),
      pnlPercent: 28.7,
      positions: 2,
      totalTrades: 94,
      winRate: 72.3,
      sharpeRatio: 1.95,
      maxDrawdown: 5.1,
    },
  ];

  return { strategies, performanceData };
}

// Singleton cache so we don't regenerate on every render
let cached: ReturnType<typeof generateCompetitionData> | null = null;
export function getArenaData() {
  if (!cached) cached = generateCompetitionData();
  return cached;
}
