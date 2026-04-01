import { NextRequest, NextResponse } from "next/server";
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "fs";
import { join } from "path";
import { detectRegime, MarketRegime } from "@/lib/hmm-regime";
import { calculateConfirmations, type OHLCVCandle } from "@/lib/technical-indicators";
import { loadStats, selectStrategy, computeConfidence } from "@/lib/strategy-learning";
import { executeTrade, type ExecuteTradeParams } from "@/lib/execute-trade";
import { lockedReadModifyWrite, atomicWriteFile } from "@/lib/file-lock";

export const dynamic = "force-dynamic";

// ---------------------------------------------------------------------------
// Constants & Types
// ---------------------------------------------------------------------------

const TMP_DIR = "/tmp/aifred-data";
const DATA_DIR = join(process.cwd(), "data");

const DEFAULT_ASSETS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"];

const CRYPTO_BINANCE: Record<string, string> = {
  "BTC/USDT": "BTCUSDT",
  "ETH/USDT": "ETHUSDT",
  "SOL/USDT": "SOLUSDT",
  "BNB/USDT": "BNBUSDT",
  "XRP/USDT": "XRPUSDT",
  "ADA/USDT": "ADAUSDT",
  "DOGE/USDT": "DOGEUSDT",
  "AVAX/USDT": "AVAXUSDT",
  "DOT/USDT": "DOTUSDT",
  "MATIC/USDT": "MATICUSDT",
};

interface RiskLimits {
  maxPositionSize: number;
  maxConcurrentPositions: number;
  maxDailyLoss: number;
  cooldownHours: number;
  requiredConfirmations: number;
}

const DEFAULT_RISK_LIMITS: RiskLimits = {
  maxPositionSize: 500,
  maxConcurrentPositions: 3,
  maxDailyLoss: 1000,
  cooldownHours: 48,
  requiredConfirmations: 7,
};

interface OpenPosition {
  symbol: string;
  side: string;
  entryPrice: number;
  quantity: number;
  enteredAt: string;
  regime: string;
}

interface ScanResult {
  symbol: string;
  currentPrice: number;
  regime: string;
  regimeConfidence: number;
  confirmationsPassed: number;
  confirmationsRequired: number;
  signal: "ENTER_LONG" | "EXIT" | "HOLD" | "NO_ACTION";
  reason: string;
  riskCheck: {
    passed: boolean;
    blockers: string[];
  };
}

interface TradeSignal {
  type: "enter" | "exit";
  symbol: string;
  side: "LONG" | "SHORT";
  quantity: number;
  reason: string;
  regime: string;
  confidence: number;
}

interface ExecutionResult {
  symbol: string;
  success: boolean;
  mode: string;
  orderId?: string;
  error?: string;
}

interface EnrichedPosition extends OpenPosition {
  currentPrice: number;
  unrealizedPnl: number;
  unrealizedPnlPercent: number;
}

// ---------------------------------------------------------------------------
// Activity log helpers (reused from execute/route.ts pattern)
// ---------------------------------------------------------------------------

function ensureTmpDir() {
  if (!existsSync(TMP_DIR)) mkdirSync(TMP_DIR, { recursive: true });
}

function readActivities(): unknown[] {
  const paths = [join(TMP_DIR, "activity-log.json"), join(DATA_DIR, "activity-log.json")];
  for (const p of paths) {
    if (existsSync(p)) {
      try {
        const data = JSON.parse(readFileSync(p, "utf-8"));
        if (Array.isArray(data)) return data;
      } catch { /* ignore */ }
    }
  }
  return [];
}

function appendActivity(entry: Record<string, unknown>) {
  const activityPath = join(TMP_DIR, "activity-log.json");
  lockedReadModifyWrite<unknown[]>(
    activityPath,
    (current) => {
      const activities = Array.isArray(current)
        ? current
        : readActivities(); // fallback to multi-path read if /tmp file missing
      activities.push({
        id: `act_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
        timestamp: new Date().toISOString(),
        ...entry,
      });
      return activities.slice(-500);
    },
  ).catch((e) => {
    console.error("Failed to append activity:", e);
  });
}

// ---------------------------------------------------------------------------
// Market data helpers
// ---------------------------------------------------------------------------

async function fetchKlines(symbol: string): Promise<OHLCVCandle[]> {
  const binSym = symbol.replace("/", "");
  const url = `https://api.binance.us/api/v3/klines?symbol=${encodeURIComponent(binSym)}&interval=1h&limit=200`;
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
    if (!res.ok) return [];
    const data: unknown[][] = await res.json();
    return data.map((k) => ({
      timestamp: k[0] as number,
      open: parseFloat(k[1] as string),
      high: parseFloat(k[2] as string),
      low: parseFloat(k[3] as string),
      close: parseFloat(k[4] as string),
      volume: parseFloat(k[5] as string),
    }));
  } catch {
    return [];
  }
}

async function getLivePrice(symbol: string): Promise<number> {
  const binSym = symbol.replace("/", "");
  try {
    const res = await fetch(
      `https://api.binance.us/api/v3/ticker/price?symbol=${encodeURIComponent(binSym)}`,
      { signal: AbortSignal.timeout(5000) },
    );
    if (res.ok) {
      const data = await res.json();
      const price = parseFloat(data.price);
      if (price > 0) return price;
    }
  } catch { /* fallback */ }
  return 0;
}

// ---------------------------------------------------------------------------
// Regime classification helpers
// ---------------------------------------------------------------------------

const BULLISH_REGIMES = new Set(["strong_bull", "bull", "moderate_bull"]);
const BEARISH_REGIMES = new Set(["bear", "crash", "choppy"]);

function isBullish(regime: string): boolean {
  return BULLISH_REGIMES.has(regime);
}

function isBearish(regime: string): boolean {
  return BEARISH_REGIMES.has(regime);
}

// ---------------------------------------------------------------------------
// Daily PnL tracking (simple /tmp persistence)
// ---------------------------------------------------------------------------

interface DailyPnlRecord {
  date: string;
  pnl: number;
  exitCount: number;
  lastExits: Record<string, string>; // symbol -> ISO timestamp of last exit
}

function loadDailyPnl(): DailyPnlRecord {
  const today = new Date().toISOString().slice(0, 10);
  const path = join(TMP_DIR, "daily-pnl.json");
  try {
    if (existsSync(path)) {
      const data: DailyPnlRecord = JSON.parse(readFileSync(path, "utf-8"));
      if (data.date === today) return data;
    }
  } catch { /* ignore */ }
  return { date: today, pnl: 0, exitCount: 0, lastExits: {} };
}

function saveDailyPnl(record: DailyPnlRecord) {
  ensureTmpDir();
  // Use atomic write to prevent corruption from concurrent requests
  atomicWriteFile(join(TMP_DIR, "daily-pnl.json"), JSON.stringify(record, null, 2)).catch((e) => {
    console.error("Failed to save daily PnL:", e);
  });
}

// ---------------------------------------------------------------------------
// Core scan logic for a single asset
// ---------------------------------------------------------------------------

async function scanAsset(
  symbol: string,
  openPositions: OpenPosition[],
  riskLimits: RiskLimits,
  dailyPnl: DailyPnlRecord,
): Promise<{ scanResult: ScanResult; signal: TradeSignal | null }> {
  const binSym = CRYPTO_BINANCE[symbol];
  if (!binSym) {
    return {
      scanResult: {
        symbol,
        currentPrice: 0,
        regime: "unknown",
        regimeConfidence: 0,
        confirmationsPassed: 0,
        confirmationsRequired: riskLimits.requiredConfirmations,
        signal: "NO_ACTION",
        reason: `Symbol ${symbol} is not a supported crypto pair`,
        riskCheck: { passed: false, blockers: ["Unsupported symbol"] },
      },
      signal: null,
    };
  }

  // Fetch regime and klines in parallel
  const [regimeResult, klines, currentPrice] = await Promise.all([
    detectRegime(binSym).catch((err: Error) => {
      console.error(`Regime detection failed for ${symbol}:`, err.message);
      return null;
    }),
    fetchKlines(symbol),
    getLivePrice(symbol),
  ]);

  const regime = regimeResult?.currentRegime ?? "unknown";
  const regimeConfidence = regimeResult?.regimeConfidence ?? 0;
  const price = currentPrice > 0 ? currentPrice : (klines.length > 0 ? klines[klines.length - 1].close : 0);

  // Run confirmations
  let confirmationsPassed = 0;
  if (klines.length >= 55) {
    const analysis = calculateConfirmations(klines);
    confirmationsPassed = analysis.passed;
  }

  // Check if we have an open position for this symbol
  const existingPosition = openPositions.find((p) => p.symbol === symbol);

  // Risk checks
  const blockers: string[] = [];

  // Check cooldown
  const cooldownMs = riskLimits.cooldownHours * 60 * 60 * 1000;
  const lastExit = dailyPnl.lastExits[symbol];
  if (lastExit) {
    const timeSinceExit = Date.now() - new Date(lastExit).getTime();
    if (timeSinceExit < cooldownMs) {
      const hoursRemaining = Math.ceil((cooldownMs - timeSinceExit) / (60 * 60 * 1000));
      blockers.push(`Cooldown active: ${hoursRemaining}h remaining after last exit`);
    }
  }

  // Check max concurrent positions (only relevant for new entries)
  if (!existingPosition && openPositions.length >= riskLimits.maxConcurrentPositions) {
    blockers.push(`Max concurrent positions reached (${openPositions.length}/${riskLimits.maxConcurrentPositions})`);
  }

  // Check daily loss limit
  if (dailyPnl.pnl <= -riskLimits.maxDailyLoss) {
    blockers.push(`Daily loss limit reached ($${Math.abs(dailyPnl.pnl).toFixed(2)} / $${riskLimits.maxDailyLoss})`);
  }

  // Determine signal
  let signalType: "ENTER_LONG" | "EXIT" | "HOLD" | "NO_ACTION" = "NO_ACTION";
  let reason = "";
  let tradeSignal: TradeSignal | null = null;

  if (existingPosition) {
    // We have an open position - check for exit
    if (isBearish(regime)) {
      signalType = "EXIT";
      reason = `Regime flipped to ${regime} - exit open ${existingPosition.side} position`;
      tradeSignal = {
        type: "exit",
        symbol,
        side: existingPosition.side as "LONG" | "SHORT",
        quantity: existingPosition.quantity,
        reason,
        regime,
        confidence: regimeConfidence,
      };
    } else {
      signalType = "HOLD";
      reason = `Holding ${existingPosition.side} position - regime: ${regime}, no exit trigger`;
    }
  } else {
    // No open position - check for entry
    if (isBullish(regime) && confirmationsPassed >= riskLimits.requiredConfirmations) {
      if (blockers.length === 0) {
        signalType = "ENTER_LONG";
        reason = `Bullish regime (${regime}) with ${confirmationsPassed}/8 confirmations passed`;

        // Calculate position size
        const positionSizeUsd = Math.min(riskLimits.maxPositionSize, price > 0 ? riskLimits.maxPositionSize : 0);
        const quantity = price > 0 ? positionSizeUsd / price : 0;

        tradeSignal = {
          type: "enter",
          symbol,
          side: "LONG",
          quantity: parseFloat(quantity.toFixed(8)),
          reason,
          regime,
          confidence: regimeConfidence,
        };
      } else {
        signalType = "NO_ACTION";
        reason = `Entry conditions met but blocked: ${blockers.join("; ")}`;
      }
    } else if (isBullish(regime)) {
      signalType = "NO_ACTION";
      reason = `Bullish regime (${regime}) but only ${confirmationsPassed}/${riskLimits.requiredConfirmations} confirmations passed`;
    } else {
      signalType = "NO_ACTION";
      reason = `Regime is ${regime} - not bullish, waiting`;
    }
  }

  return {
    scanResult: {
      symbol,
      currentPrice: price,
      regime,
      regimeConfidence,
      confirmationsPassed,
      confirmationsRequired: riskLimits.requiredConfirmations,
      signal: signalType,
      reason,
      riskCheck: {
        passed: blockers.length === 0,
        blockers,
      },
    },
    signal: tradeSignal,
  };
}

// ---------------------------------------------------------------------------
// Execute a trade signal (paper mode by default)
// ---------------------------------------------------------------------------

async function executeSignal(
  signal: TradeSignal,
  mode: "paper" | "live",
  brokerId?: string,
  credentials?: Record<string, string>,
): Promise<ExecutionResult> {
  try {
    // Determine the effective side: if exiting, flip the side for the order
    const effectiveSide: "LONG" | "SHORT" =
      signal.type === "exit"
        ? (signal.side === "LONG" ? "SHORT" : "LONG")
        : signal.side;

    const params: ExecuteTradeParams = {
      symbol: signal.symbol,
      side: effectiveSide,
      quantity: signal.quantity,
      orderType: "market",
      mode,
      brokerId: mode === "live" ? brokerId : undefined,
      credentials: mode === "live" ? credentials : undefined,
    };

    // Call the shared execution logic directly — no HTTP round-trip needed.
    // The autoscan endpoint is already auth-protected by middleware,
    // so we don't need to re-authenticate for the execute call.
    const result = await executeTrade(params);

    return {
      symbol: signal.symbol,
      success: result.data.success as boolean ?? false,
      mode,
      orderId: result.data.orderId as string | undefined,
      error: result.data.success ? undefined : ((result.data.message as string) ?? "Execution failed"),
    };
  } catch (err) {
    return {
      symbol: signal.symbol,
      success: false,
      mode,
      error: err instanceof Error ? err.message : "Unknown execution error",
    };
  }
}

// ---------------------------------------------------------------------------
// GET handler - simple status check
// ---------------------------------------------------------------------------

export async function GET() {
  return NextResponse.json({
    status: "ready",
    description: "Autonomous trading scan endpoint",
    usage: "POST with assets, mode, and optional autoExecute flag",
    defaultAssets: DEFAULT_ASSETS,
    defaultRiskLimits: DEFAULT_RISK_LIMITS,
  });
}

// ---------------------------------------------------------------------------
// POST handler - autonomous scan
// ---------------------------------------------------------------------------

export async function POST(request: NextRequest) {
  const scanStartTime = Date.now();

  try {
    const body = await request.json().catch(() => ({}));

    const {
      assets = DEFAULT_ASSETS,
      autoExecute = false,
      mode = "paper",
      brokerId,
      credentials,
      riskLimits: userRiskLimits,
      openPositions: inputPositions = [],
    } = body as {
      assets?: string[];
      autoExecute?: boolean;
      mode?: "paper" | "live";
      brokerId?: string;
      credentials?: Record<string, string>;
      riskLimits?: Partial<RiskLimits>;
      openPositions?: OpenPosition[];
    };

    // Merge user risk limits with defaults
    const riskLimits: RiskLimits = { ...DEFAULT_RISK_LIMITS, ...userRiskLimits };

    // Validate autoExecute + live requirements
    if (autoExecute && mode === "live" && !brokerId) {
      return NextResponse.json(
        { success: false, message: "brokerId is required for live auto-execution" },
        { status: 400 },
      );
    }

    // Load daily PnL tracking
    const dailyPnl = loadDailyPnl();

    // Load strategy stats for confidence scoring
    const strategyStats = loadStats();

    // Determine which symbols are in cooldown
    const coolingDown: string[] = [];
    const cooldownMs = riskLimits.cooldownHours * 60 * 60 * 1000;
    for (const [sym, exitTime] of Object.entries(dailyPnl.lastExits)) {
      if (Date.now() - new Date(exitTime).getTime() < cooldownMs) {
        coolingDown.push(sym);
      }
    }

    // -----------------------------------------------------------------------
    // Scan all assets in parallel
    // -----------------------------------------------------------------------
    const scanPromises = assets.map((symbol) =>
      scanAsset(symbol, inputPositions, riskLimits, dailyPnl).catch((err) => {
        console.error(`Scan failed for ${symbol}:`, err);
        return {
          scanResult: {
            symbol,
            currentPrice: 0,
            regime: "error",
            regimeConfidence: 0,
            confirmationsPassed: 0,
            confirmationsRequired: riskLimits.requiredConfirmations,
            signal: "NO_ACTION" as const,
            reason: `Scan error: ${err instanceof Error ? err.message : String(err)}`,
            riskCheck: { passed: false, blockers: ["Scan failed"] },
          },
          signal: null,
        };
      }),
    );

    const scanResults = await Promise.all(scanPromises);

    // Collect results and signals
    const allScanResults: ScanResult[] = scanResults.map((r) => r.scanResult);
    const allSignals: TradeSignal[] = scanResults
      .map((r) => r.signal)
      .filter((s): s is TradeSignal => s !== null);

    // -----------------------------------------------------------------------
    // Execute signals if autoExecute is true
    // -----------------------------------------------------------------------
    const executions: ExecutionResult[] = [];

    if (autoExecute && allSignals.length > 0) {
      const executionPromises = allSignals.map((signal) =>
        executeSignal(signal, mode, brokerId, credentials),
      );
      const executionResults = await Promise.all(executionPromises);
      executions.push(...executionResults);
    }

    // -----------------------------------------------------------------------
    // Update open positions based on signals
    // -----------------------------------------------------------------------
    const updatedPositions: OpenPosition[] = [...inputPositions];

    for (const signal of allSignals) {
      if (signal.type === "enter") {
        // Only add if execution succeeded (or not auto-executing)
        const execution = executions.find((e) => e.symbol === signal.symbol);
        if (!autoExecute || (execution && execution.success)) {
          const scanResult = allScanResults.find((r) => r.symbol === signal.symbol);
          updatedPositions.push({
            symbol: signal.symbol,
            side: signal.side,
            entryPrice: scanResult?.currentPrice ?? 0,
            quantity: signal.quantity,
            enteredAt: new Date().toISOString(),
            regime: signal.regime,
          });
        }
      } else if (signal.type === "exit") {
        // Remove the position
        const idx = updatedPositions.findIndex((p) => p.symbol === signal.symbol);
        if (idx >= 0) {
          const exitedPosition = updatedPositions[idx];
          const scanResult = allScanResults.find((r) => r.symbol === signal.symbol);
          const exitPrice = scanResult?.currentPrice ?? 0;

          // Calculate realized PnL
          if (exitPrice > 0 && exitedPosition.entryPrice > 0) {
            const pnl =
              exitedPosition.side === "LONG"
                ? (exitPrice - exitedPosition.entryPrice) * exitedPosition.quantity
                : (exitedPosition.entryPrice - exitPrice) * exitedPosition.quantity;
            dailyPnl.pnl += pnl;
          }

          // Record exit time for cooldown
          dailyPnl.lastExits[signal.symbol] = new Date().toISOString();
          dailyPnl.exitCount++;

          updatedPositions.splice(idx, 1);
        }
      }
    }

    // Save updated daily PnL
    saveDailyPnl(dailyPnl);

    // -----------------------------------------------------------------------
    // Enrich positions with current prices and unrealized PnL
    // -----------------------------------------------------------------------
    const enrichedPositions: EnrichedPosition[] = updatedPositions.map((pos) => {
      const scanResult = allScanResults.find((r) => r.symbol === pos.symbol);
      const currentPrice = scanResult?.currentPrice ?? pos.entryPrice;
      const priceDiff =
        pos.side === "LONG"
          ? currentPrice - pos.entryPrice
          : pos.entryPrice - currentPrice;
      const unrealizedPnl = priceDiff * pos.quantity;
      const unrealizedPnlPercent =
        pos.entryPrice > 0 ? (priceDiff / pos.entryPrice) * 100 : 0;

      return {
        ...pos,
        currentPrice,
        unrealizedPnl: parseFloat(unrealizedPnl.toFixed(2)),
        unrealizedPnlPercent: parseFloat(unrealizedPnlPercent.toFixed(2)),
      };
    });

    // -----------------------------------------------------------------------
    // Calculate next scan time (every 1 hour)
    // -----------------------------------------------------------------------
    const nextScanAt = new Date(Date.now() + 60 * 60 * 1000).toISOString();

    // -----------------------------------------------------------------------
    // Log scan to activity
    // -----------------------------------------------------------------------
    const signalSummary = allSignals.length > 0
      ? allSignals.map((s) => `${s.type.toUpperCase()} ${s.side} ${s.symbol}`).join(", ")
      : "No signals";

    appendActivity({
      type: "autoscan_completed",
      severity: allSignals.length > 0 ? "info" : "debug",
      title: `Autoscan: ${assets.length} assets scanned`,
      message: `Scanned ${assets.length} assets in ${Date.now() - scanStartTime}ms. Signals: ${signalSummary}. Positions: ${enrichedPositions.length} open.`,
      details: {
        assets,
        signalCount: allSignals.length,
        signals: allSignals,
        executionCount: executions.length,
        positionsOpen: enrichedPositions.length,
        dailyPnl: dailyPnl.pnl,
        autoExecute,
        mode,
        scanDurationMs: Date.now() - scanStartTime,
      },
    });

    // -----------------------------------------------------------------------
    // Build response
    // -----------------------------------------------------------------------
    const response: Record<string, unknown> = {
      success: true,
      timestamp: new Date().toISOString(),
      scanResults: allScanResults,
      signals: allSignals,
      openPositions: enrichedPositions,
      riskStatus: {
        dailyPnl: parseFloat(dailyPnl.pnl.toFixed(2)),
        positionsOpen: enrichedPositions.length,
        maxPositions: riskLimits.maxConcurrentPositions,
        coolingDown,
      },
      nextScanAt,
    };

    if (autoExecute) {
      response.executions = executions;
    }

    return NextResponse.json(response);
  } catch (error) {
    console.error("Autoscan error:", error);

    appendActivity({
      type: "autoscan_error",
      severity: "error",
      title: "Autoscan failed",
      message: `Autoscan crashed: ${error instanceof Error ? error.message : String(error)}`,
    });

    return NextResponse.json(
      {
        success: false,
        message: `Autoscan failed: ${error instanceof Error ? error.message : "Unknown error"}`,
        timestamp: new Date().toISOString(),
      },
      { status: 500 },
    );
  }
}
