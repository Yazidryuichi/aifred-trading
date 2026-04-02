import { NextRequest, NextResponse } from "next/server";
import { existsSync, mkdirSync } from "fs";
import { join } from "path";
import {
  lockedReadModifyWrite,
  readJsonWithFallback,
} from "@/lib/file-lock";

export const dynamic = "force-dynamic";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AssetDecision {
  asset: string;
  action: "buy" | "sell" | "hold" | "close";
  succeeded: boolean;
  confidence?: number;
  reasoning?: string;
}

interface AgentContributions {
  technical?: string;
  sentiment?: string;
  risk?: string;
  regime?: string;
  execution?: string;
}

interface DecisionRecord {
  id: string;
  cycleNumber: number;
  timestamp: string;
  status: "success" | "failure" | "partial";
  inputPrompt: string;
  chainOfThought: string;
  assetDecisions: AssetDecision[];
  agents: AgentContributions;
  durationMs: number;
  modelVersion: string;
}

interface DecisionsFile {
  decisions: DecisionRecord[];
  nextCycleNumber: number;
}

// ---------------------------------------------------------------------------
// File helpers
// ---------------------------------------------------------------------------

const TMP_DIR = "/tmp/aifred-data";
const DATA_DIR = join(process.cwd(), "data");
const DECISIONS_PATH_TMP = join(TMP_DIR, "decisions.json");
const DECISIONS_PATH_DATA = join(DATA_DIR, "decisions.json");
const MAX_ENTRIES = 5000;
const MAX_BODY_SIZE = 50 * 1024; // 50KB

function ensureTmpDir() {
  if (!existsSync(TMP_DIR)) {
    mkdirSync(TMP_DIR, { recursive: true });
  }
}

function generateId(): string {
  return `dec_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function readDecisionsFile(): DecisionsFile {
  return readJsonWithFallback<DecisionsFile>(
    [DECISIONS_PATH_TMP, DECISIONS_PATH_DATA],
    { decisions: [], nextCycleNumber: 1 },
  );
}

// ---------------------------------------------------------------------------
// Seed data generator — 25 realistic decision records over last 7 days
// ---------------------------------------------------------------------------

function generateSeedDecisions(): DecisionsFile {
  const now = Date.now();
  const SEVEN_DAYS = 7 * 24 * 3600_000;
  const decisions: DecisionRecord[] = [];

  const assets = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "AAPL", "SPY"];

  // Pre-built chain-of-thought templates for realism
  const btcLongCoT = (entry: number, sl: number, tp: number, rsi: string, macdDir: string, oiDelta: string, funding: string, kelly: string) =>
    `1) Position check: No current BTC position. Available margin: $5,200 USDC (48% of equity).\n\n` +
    `2) Market analysis:\n` +
    `- BTC/USDT: 5m/15m/1H all showing higher highs and higher lows\n` +
    `- 1H OI: ${oiDelta}, funding rate: ${funding}\n` +
    `- RSI(14): ${rsi}, MACD: ${macdDir}\n` +
    `- Pattern: "uptrend + accumulation", typical long setup\n\n` +
    `3) Risk management:\n` +
    `- Entry zone: $${entry.toLocaleString()}-$${(entry + 500).toLocaleString()}\n` +
    `- Stop loss: $${sl.toLocaleString()} (ATR-based, 1.5x ATR)\n` +
    `- Take profit: $${tp.toLocaleString()} (2:1 R:R ratio)\n` +
    `- Position size: 0.03 BTC ($${(entry * 0.03).toFixed(0)}, Kelly: ${kelly}% of portfolio)\n\n` +
    `4) Candidate assets scan:\n` +
    `- ETH/USDT: OI -2.1%, price -0.8% → sideways, skip\n` +
    `- SOL/USDT: consolidating near support, wait for breakout\n\n` +
    `=> Strategy: LONG BTC with tight stop. Focus on trend continuation.`;

  const ethLongCoT = (entry: number, sl: number, tp: number, rsi: string, vol: string) =>
    `1) Position check: No current ETH position. Available margin: $4,800 USDC (44% of equity).\n\n` +
    `2) Market analysis:\n` +
    `- ETH/USDT: ascending triangle on 4H, breakout above $${entry.toLocaleString()} resistance\n` +
    `- Volume: ${vol} above 20-period average\n` +
    `- RSI(14): ${rsi}, not overbought, room to run\n` +
    `- ETH/BTC ratio recovering after 3-week downtrend\n\n` +
    `3) Risk management:\n` +
    `- Entry: $${entry.toLocaleString()}\n` +
    `- Stop loss: $${sl.toLocaleString()} (below triangle support)\n` +
    `- Take profit: $${tp.toLocaleString()} (measured move target)\n` +
    `- R:R ratio: ${((tp - entry) / (entry - sl)).toFixed(1)}:1\n\n` +
    `4) Correlation check:\n` +
    `- BTC trending up, supports ETH long thesis\n` +
    `- DeFi TVL increasing, positive for ETH fundamentals\n\n` +
    `=> Strategy: LONG ETH on triangle breakout confirmation.`;

  const solLongCoT = (entry: number, sl: number, tp: number, rsi: string) =>
    `1) Position check: No SOL position open. Portfolio at 62% cash.\n\n` +
    `2) Market analysis:\n` +
    `- SOL/USDT: strong momentum, 3 consecutive green daily candles\n` +
    `- RSI(14): ${rsi}, trending up but not overbought\n` +
    `- Volume profile shows accumulation at $${(entry - 5).toFixed(0)}-$${entry.toFixed(0)} range\n` +
    `- Solana ecosystem TVL at 6-month high\n\n` +
    `3) Risk management:\n` +
    `- Entry: $${entry.toFixed(2)}\n` +
    `- Stop: $${sl.toFixed(2)} (below recent swing low)\n` +
    `- Target: $${tp.toFixed(2)}\n` +
    `- Size: 15 SOL ($${(entry * 15).toFixed(0)}, 2.1% of portfolio)\n\n` +
    `=> Strategy: LONG SOL momentum play, ride ecosystem growth.`;

  const holdCoT = (asset: string, reason: string) =>
    `1) Position check: Scanned ${asset} for entry opportunities.\n\n` +
    `2) Market analysis:\n` +
    `- ${reason}\n` +
    `- No clear directional signal from 7-agent ensemble\n\n` +
    `3) Decision: HOLD — insufficient confidence for new entry.\n` +
    `- Minimum confidence threshold: 78%\n` +
    `- Current confidence: below threshold\n\n` +
    `=> Strategy: Preserve capital, re-evaluate next cycle.`;

  const aaplCoT = (entry: number, sl: number, tp: number) =>
    `1) Position check: No AAPL position. Equity allocation: stocks at 18% (below 30% target).\n\n` +
    `2) Market analysis:\n` +
    `- AAPL trading above all major moving averages (20/50/200 EMA)\n` +
    `- Earnings beat expectations by 8%, revenue guidance raised\n` +
    `- RSI(14): 58.3, MACD histogram positive and expanding\n` +
    `- Institutional flow: net buyer over last 5 sessions\n\n` +
    `3) Risk management:\n` +
    `- Entry: $${entry.toFixed(2)}\n` +
    `- Stop: $${sl.toFixed(2)} (below 20 EMA)\n` +
    `- Target: $${tp.toFixed(2)} (near ATH resistance)\n` +
    `- Position size: 12 shares ($${(entry * 12).toFixed(0)}, Kelly: 1.9%)\n\n` +
    `4) Sector check:\n` +
    `- XLK (tech sector ETF) in uptrend, supports individual stock longs\n\n` +
    `=> Strategy: LONG AAPL on earnings momentum + trend alignment.`;

  const spyCoT = (entry: number, sl: number, tp: number) =>
    `1) Portfolio check: Current SPY allocation at 0%. Macro screen initiated.\n\n` +
    `2) Market analysis:\n` +
    `- SPY approaching all-time highs with breadth confirmation\n` +
    `- VIX at 14.2 — low implied volatility, favorable for long positions\n` +
    `- Advance-decline line making new highs\n` +
    `- Fed minutes dovish, supporting risk assets\n\n` +
    `3) Risk management:\n` +
    `- Entry: $${entry.toFixed(2)}\n` +
    `- Stop: $${sl.toFixed(2)} (1.2% risk, below 10-day EMA)\n` +
    `- Target: $${tp.toFixed(2)} (projected move from triangle)\n` +
    `- Size: 5 shares ($${(entry * 5).toFixed(0)}, 2.4% of portfolio)\n\n` +
    `=> Strategy: LONG SPY on breadth confirmation + low VIX environment.`;

  const failureCoT = (asset: string, errMsg: string) =>
    `1) Attempted to execute trade on ${asset}.\n\n` +
    `2) Execution error:\n` +
    `- ${errMsg}\n\n` +
    `3) Recovery: Order not filled. No position opened. Will retry next cycle if signal persists.`;

  // Define seed decision templates
  interface SeedTemplate {
    hoursAgo: number;
    status: "success" | "failure" | "partial";
    assetDecisions: AssetDecision[];
    cot: string;
    prompt: string;
    agents: AgentContributions;
    durationMs: number;
  }

  const templates: SeedTemplate[] = [
    // --- Cycle 1: BTC long (7 days ago) ---
    {
      hoursAgo: 168,
      status: "success",
      assetDecisions: [
        { asset: "BTC/USDT", action: "buy", succeeded: true, confidence: 89, reasoning: "Strong uptrend + accumulation pattern" },
        { asset: "ETH/USDT", action: "hold", succeeded: true, confidence: 52, reasoning: "Sideways, insufficient signal" },
        { asset: "SOL/USDT", action: "hold", succeeded: true, confidence: 48, reasoning: "Consolidating near support" },
      ],
      cot: btcLongCoT(87500, 86200, 91000, "54.2", "bullish crossover on 1H", "+$7.12M (+0.61%)", "+0.0089%", "2.8"),
      prompt: "Market data as of 2026-03-25T08:00:00Z — BTC: $87,480 | ETH: $3,420 | SOL: $138.50 | Portfolio: $10,800 USDC | Open positions: none",
      agents: {
        technical: "BTC 5m/15m/1H all higher highs. MACD bullish crossover on 1H. RSI(14)=54.2, neutral with bullish momentum. EMA20>EMA50 on all timeframes. Volume +35% above 20-period average.",
        sentiment: "FinBERT score: 0.82 (bullish). Social media sentiment: 72% positive. Fear & Greed Index: 65 (Greed). Whale wallet accumulation detected: +1,200 BTC moved to cold storage in 24h.",
        risk: "Kelly criterion suggests 2.8% position size. Max drawdown tolerance: 3%. Current portfolio heat: 0% (no open positions). VaR(95%): -$324 on proposed position.",
        regime: "HMM classifies current market as MODERATE BULL with 78% confidence. Regime persistence: 12 days. Transition probability to BEAR: 8%. Recommended: full position sizing for longs.",
        execution: "Optimal entry zone: $87,500-$88,000 based on VWAP and order book depth. Estimated slippage: 3.2 bps. Recommended order type: limit at $87,550 with 5-minute timeout to market.",
      },
      durationMs: 12400,
    },
    // --- Cycle 2: Hold all (6.5 days ago) ---
    {
      hoursAgo: 156,
      status: "success",
      assetDecisions: [
        { asset: "BTC/USDT", action: "hold", succeeded: true, confidence: 45, reasoning: "Already positioned, managing existing trade" },
        { asset: "ETH/USDT", action: "hold", succeeded: true, confidence: 58, reasoning: "No clear breakout signal" },
        { asset: "SOL/USDT", action: "hold", succeeded: true, confidence: 42, reasoning: "Still consolidating" },
        { asset: "AAPL", action: "hold", succeeded: true, confidence: 61, reasoning: "Pre-earnings, waiting for catalyst" },
        { asset: "SPY", action: "hold", succeeded: true, confidence: 55, reasoning: "Range-bound near resistance" },
      ],
      cot: holdCoT("all assets", "BTC position already open. ETH choppy. SOL consolidating. Stocks pre-earnings — high event risk. No new entries warranted."),
      prompt: "Market data as of 2026-03-25T20:00:00Z — BTC: $88,120 (+0.7%) | ETH: $3,435 (+0.4%) | SOL: $139.20 | AAPL: $188.90 | SPY: $520.80 | Open: BTC LONG 0.03 @ $87,550",
      agents: {
        technical: "BTC trending within expected range. ETH stuck at $3,440 resistance. SOL Bollinger Bands squeezing — breakout imminent but direction unclear. AAPL approaching earnings, IV elevated.",
        sentiment: "FinBERT: neutral (0.54). Market sentiment mixed ahead of FOMC minutes. Crypto Fear & Greed: 62. No significant whale movements detected.",
        risk: "Portfolio heat: 24% (BTC position). Remaining margin adequate for 1 additional position. Recommend waiting for cleaner setups. Daily VaR: -$156.",
        regime: "Regime: MODERATE BULL (73% confidence, down from 78%). No regime transition detected. Holding pattern expected for 6-12 hours.",
      },
      durationMs: 9800,
    },
    // --- Cycle 3: BTC close + ETH long (6 days ago) ---
    {
      hoursAgo: 144,
      status: "success",
      assetDecisions: [
        { asset: "BTC/USDT", action: "close", succeeded: true, confidence: 82, reasoning: "Take profit hit at $91,000" },
        { asset: "ETH/USDT", action: "buy", succeeded: true, confidence: 84, reasoning: "Triangle breakout confirmed with volume" },
        { asset: "SOL/USDT", action: "hold", succeeded: true, confidence: 56, reasoning: "Breakout not confirmed yet" },
      ],
      cot: `1) BTC position management:\n- Current: LONG 0.03 BTC @ $87,550\n- Price now: $91,050 — TP zone reached\n- Closing position: +$105 realized (+3.99%)\n\n2) New opportunity scan:\n` +
        ethLongCoT(3520, 3420, 3720, "56.8", "+22%"),
      prompt: "Market data as of 2026-03-26T08:00:00Z — BTC: $91,050 | ETH: $3,518 | SOL: $141.30 | Open: BTC LONG 0.03 @ $87,550 (unrealized: +$105)",
      agents: {
        technical: "BTC hit TP zone at $91K, momentum waning on 4H. ETH breaking ascending triangle at $3,520 with +22% volume surge. SOL coiling but no trigger yet.",
        sentiment: "FinBERT: bullish (0.78). ETH Dencun upgrade narrative gaining traction. Social volume for ETH up 45% in 24h. BTC sentiment cooling after rally.",
        risk: "BTC TP hit — lock profits. New ETH position: Kelly 2.2%, well within limits. Portfolio heat will rotate from BTC to ETH. Max concurrent risk: 26%.",
        regime: "BTC: transitioning to SIDEWAYS (62% confidence). ETH: MODERATE BULL (80% confidence). Cross-asset rotation detected: capital flowing BTC → ETH.",
        execution: "BTC close: market order at $91,050, est. slippage 2.8 bps. ETH entry: limit at $3,520, order book depth strong at this level.",
      },
      durationMs: 18200,
    },
    // --- Cycle 4: SOL long (5.5 days ago) ---
    {
      hoursAgo: 132,
      status: "success",
      assetDecisions: [
        { asset: "ETH/USDT", action: "hold", succeeded: true, confidence: 72, reasoning: "Position active, trending favorably" },
        { asset: "SOL/USDT", action: "buy", succeeded: true, confidence: 86, reasoning: "Breakout confirmed with ecosystem momentum" },
        { asset: "BTC/USDT", action: "hold", succeeded: true, confidence: 48, reasoning: "No position, awaiting pullback entry" },
      ],
      cot: solLongCoT(142.35, 136.80, 155.00, "61.5"),
      prompt: "Market data as of 2026-03-26T20:00:00Z — BTC: $90,200 | ETH: $3,545 (+0.7%) | SOL: $142.10 | Open: ETH LONG 1.0 @ $3,520",
      agents: {
        technical: "SOL Bollinger squeeze resolved to upside. RSI(14)=61.5, strong momentum. Volume +55% above average. All moving averages aligned bullish.",
        sentiment: "FinBERT: bullish (0.85). Solana DeFi TVL at 6-month high. Jupiter DEX volume surging. Developer activity metrics positive.",
        risk: "Adding SOL brings portfolio heat to 48%. Within risk tolerance (max 60%). Kelly: 2.1% for SOL. Combined position correlation: 0.72 (moderate, acceptable).",
        regime: "SOL: STRONG BULL (85% confidence). Ecosystem momentum supporting price action. Regime persistence estimate: 5-8 days.",
        execution: "SOL entry: limit at $142.35. Order book thin above $143 — expect some slippage if market order. Recommended: aggressive limit with 2-min timeout.",
      },
      durationMs: 14600,
    },
    // --- Cycle 5: AAPL long (5 days ago) ---
    {
      hoursAgo: 120,
      status: "success",
      assetDecisions: [
        { asset: "AAPL", action: "buy", succeeded: true, confidence: 81, reasoning: "Post-earnings breakout + institutional buying" },
        { asset: "SPY", action: "hold", succeeded: true, confidence: 64, reasoning: "Near resistance, wait for confirmation" },
        { asset: "ETH/USDT", action: "hold", succeeded: true, confidence: 70, reasoning: "Position active, at +1.2%" },
        { asset: "SOL/USDT", action: "hold", succeeded: true, confidence: 74, reasoning: "Position active, trending up" },
      ],
      cot: aaplCoT(189.45, 184.50, 198.00),
      prompt: "Market data as of 2026-03-27T14:30:00Z — AAPL: $189.20 (post-earnings +3.2%) | SPY: $521.40 | ETH: $3,562 | SOL: $144.80 | Open: ETH LONG, SOL LONG",
      agents: {
        technical: "AAPL gap up on earnings, holding above VWAP. RSI(14)=58.3 — room to run. MACD bullish, volume 2.3x average. SPY stalling at $522 resistance.",
        sentiment: "FinBERT: bullish (0.76). AAPL earnings beat by 8%, raised guidance. Institutional flow tracker: 5 consecutive days of net buying. Options flow bullish.",
        risk: "AAPL position: Kelly 1.9%. Total portfolio heat including crypto: 52%. Equity allocation moving toward 30% target. Risk/reward: 1.7:1.",
        regime: "US equities: MODERATE BULL (74% confidence). Tech sector outperforming. VIX at 15.2, supportive for long positions.",
        execution: "AAPL entry: market order at open, expected fill near $189.45. Average spread: $0.01. Institutional participation high — good liquidity.",
      },
      durationMs: 11300,
    },
    // --- Cycle 6: Failed SOL order (4.5 days ago) ---
    {
      hoursAgo: 108,
      status: "partial",
      assetDecisions: [
        { asset: "SOL/USDT", action: "sell", succeeded: false, confidence: 77, reasoning: "Attempted to add to SOL position but order rejected — insufficient margin" },
        { asset: "ETH/USDT", action: "hold", succeeded: true, confidence: 68, reasoning: "Position active, consolidating" },
        { asset: "AAPL", action: "hold", succeeded: true, confidence: 75, reasoning: "Position active, +0.8% from entry" },
      ],
      cot: failureCoT("SOL/USDT", "Attempted to increase SOL LONG position by 10 SOL. Rejected: available margin $1,200 insufficient for $1,425 required. Portfolio heat at 55% — near limit."),
      prompt: "Market data as of 2026-03-27T20:00:00Z — SOL: $146.50 (+2.9%) | ETH: $3,548 (-0.4%) | AAPL: $190.80 | Open: ETH LONG, SOL LONG, AAPL LONG",
      agents: {
        technical: "SOL momentum strong but portfolio fully allocated. ETH consolidating in range. AAPL holding gains.",
        sentiment: "FinBERT: bullish (0.80). SOL ecosystem continues to attract capital. Market breadth positive.",
        risk: "MARGIN WARNING: Portfolio heat at 55%, approaching 60% limit. Cannot add new positions without closing existing ones. Recommend: hold and manage.",
        regime: "SOL: STRONG BULL persists. ETH: SIDEWAYS transition in progress. AAPL: MODERATE BULL.",
        execution: "SOL add-on rejected: insufficient margin. No order sent to exchange. Retry condition: close ETH or reduce position sizes.",
      },
      durationMs: 8400,
    },
    // --- Cycle 7: Hold cycle (4 days ago) ---
    {
      hoursAgo: 96,
      status: "success",
      assetDecisions: [
        { asset: "BTC/USDT", action: "hold", succeeded: true, confidence: 52, reasoning: "No entry signal, waiting for pullback" },
        { asset: "ETH/USDT", action: "hold", succeeded: true, confidence: 66, reasoning: "Position at breakeven, monitoring" },
        { asset: "SOL/USDT", action: "hold", succeeded: true, confidence: 78, reasoning: "Position profitable, trailing stop active" },
        { asset: "AAPL", action: "hold", succeeded: true, confidence: 73, reasoning: "Trending up, let winner run" },
        { asset: "SPY", action: "hold", succeeded: true, confidence: 58, reasoning: "Still range-bound" },
      ],
      cot: holdCoT("portfolio", "All positions within expected ranges. No new signals meeting 78% confidence threshold. Focus on risk management of existing positions."),
      prompt: "Market data as of 2026-03-28T08:00:00Z — BTC: $89,800 | ETH: $3,525 | SOL: $148.20 | AAPL: $191.20 | SPY: $521.80 | Open: ETH, SOL, AAPL LONGs",
      agents: {
        technical: "All positions trending within channels. No major technical events. BTC pulled back from $91K to $89.8K — potential support at $89K.",
        sentiment: "FinBERT: neutral-bullish (0.62). Market in wait-and-see mode ahead of NFP data. Crypto sentiment stable.",
        risk: "Portfolio heat: 52%. All stops in place. Combined unrealized PnL: +$312 (+2.9%). No rebalancing needed. Daily VaR: -$245.",
        regime: "Multi-asset: MODERATE BULL (68% avg confidence). No regime transitions imminent. Low volatility environment.",
      },
      durationMs: 9200,
    },
    // --- Cycle 8: ETH close + SPY long (3.5 days ago) ---
    {
      hoursAgo: 84,
      status: "success",
      assetDecisions: [
        { asset: "ETH/USDT", action: "close", succeeded: true, confidence: 79, reasoning: "Momentum fading, close at +2.8% before regime transition" },
        { asset: "SPY", action: "buy", succeeded: true, confidence: 82, reasoning: "Breakout above $522 with breadth confirmation" },
        { asset: "BTC/USDT", action: "hold", succeeded: true, confidence: 55, reasoning: "No setup" },
      ],
      cot: `1) ETH position review:\n- LONG 1.0 ETH @ $3,520, current: $3,618\n- Unrealized: +$98 (+2.8%)\n- Regime shifting to SIDEWAYS — close before momentum loss\n\n2) SPY opportunity:\n` +
        spyCoT(522.50, 516.20, 535.00),
      prompt: "Market data as of 2026-03-28T20:00:00Z — ETH: $3,618 | SPY: $522.30 | BTC: $89,500 | SOL: $149.80 | AAPL: $192.10 | Open: ETH, SOL, AAPL LONGs",
      agents: {
        technical: "ETH momentum waning on 4H — MACD histogram shrinking. SPY breaking $522 resistance with strong A/D line. VIX declining to 14.2.",
        sentiment: "FinBERT: neutral (0.58) for ETH, bullish (0.74) for equities. Macro environment supportive: Fed dovish tilt confirmed.",
        risk: "ETH close frees margin. SPY entry maintains portfolio heat at 48%. Rotation from crypto to equities diversifies risk. Correlation benefit.",
        regime: "ETH: transitioning MODERATE BULL → SIDEWAYS (58%→42%). SPY: MODERATE BULL (76%). Cross-asset regime suggests equity rotation.",
        execution: "ETH close: market at $3,618, est. slip 3.5 bps. SPY entry: limit at $522.50 during RTH. Strong institutional participation.",
      },
      durationMs: 16800,
    },
    // --- Cycle 9: SOL close with profit (3 days ago) ---
    {
      hoursAgo: 72,
      status: "success",
      assetDecisions: [
        { asset: "SOL/USDT", action: "close", succeeded: true, confidence: 85, reasoning: "Trailing stop hit at $152.40, locking in +7% gain" },
        { asset: "BTC/USDT", action: "hold", succeeded: true, confidence: 62, reasoning: "Pullback to $88K, watching for support" },
        { asset: "AAPL", action: "hold", succeeded: true, confidence: 77, reasoning: "Trending up, approaching target" },
        { asset: "SPY", action: "hold", succeeded: true, confidence: 74, reasoning: "New position, early in trade" },
      ],
      cot: `1) SOL trailing stop triggered:\n- LONG 15 SOL @ $142.35, trailing stop hit at $152.40\n- Realized PnL: +$150.75 (+7.06%)\n- SOL pulled back from $155.80 high — correct exit\n\n2) Portfolio review:\n- Remaining positions: AAPL LONG, SPY LONG\n- Portfolio heat reduced to 32%\n- Available for new entries if signals emerge\n\n3) BTC scan:\n- Pulled back to $88,000 support zone\n- Not yet at entry level — need RSI below 45 or MACD bullish cross\n\n=> Strategy: Hold existing, SOL profit locked. Watch BTC for re-entry.`,
      prompt: "Market data as of 2026-03-29T08:00:00Z — SOL: $152.40 (trailing stop triggered) | BTC: $88,000 | AAPL: $193.50 | SPY: $523.80 | Open: SOL LONG (closing), AAPL LONG, SPY LONG",
      agents: {
        technical: "SOL hit trailing stop after pullback from $155.80. Healthy profit-taking. BTC at $88K support — MACD flat, wait for signal. AAPL and SPY trending.",
        sentiment: "FinBERT: neutral (0.55). Post-rally consolidation across crypto. Equities supported by macro backdrop.",
        risk: "SOL close locks +$150.75 profit. Portfolio heat drops to 32%. Excellent risk posture for new opportunities. Realized PnL this week: +$354.",
        regime: "SOL: transition to SIDEWAYS confirmed. BTC: NEUTRAL (55%). Equities: MODERATE BULL (72%).",
        execution: "SOL trailing stop: filled at $152.40 via limit. Slippage: 1.8 bps (favorable). Net proceeds credited.",
      },
      durationMs: 11900,
    },
    // --- Cycle 10: BTC long re-entry (2.5 days ago) ---
    {
      hoursAgo: 60,
      status: "success",
      assetDecisions: [
        { asset: "BTC/USDT", action: "buy", succeeded: true, confidence: 87, reasoning: "Bounce from $88K support with volume confirmation" },
        { asset: "AAPL", action: "hold", succeeded: true, confidence: 79, reasoning: "Approaching TP at $198, monitoring closely" },
        { asset: "SPY", action: "hold", succeeded: true, confidence: 76, reasoning: "Trending, +0.6% from entry" },
      ],
      cot: btcLongCoT(88200, 86800, 92500, "47.8", "bullish crossover on 4H", "+$5.8M (+0.48%)", "+0.0072%", "3.1"),
      prompt: "Market data as of 2026-03-29T20:00:00Z — BTC: $88,150 | ETH: $3,480 | SOL: $149.20 | AAPL: $194.80 | SPY: $524.60 | Open: AAPL LONG, SPY LONG",
      agents: {
        technical: "BTC bounced off $88K support with +28% volume surge. MACD bullish crossover on 4H. RSI(14)=47.8, rebounding from oversold area on 1H. EMA20 acting as dynamic support.",
        sentiment: "FinBERT: bullish (0.79). Institutional BTC accumulation resumed. MicroStrategy added 2,500 BTC. Fear & Greed: 58 (transitioning to Greed).",
        risk: "BTC re-entry: Kelly 3.1%. Portfolio heat will increase to 54% — within tolerance. Stop at $86,800 limits max loss to $42. Combined portfolio risk manageable.",
        regime: "BTC: transitioning NEUTRAL → MODERATE BULL (71% confidence). Support bounce is classic regime shift trigger. Expect trend continuation.",
        execution: "BTC entry: limit at $88,200. Order book shows strong bids at $88,000-$88,100. Estimated fill: within 30 seconds.",
      },
      durationMs: 13500,
    },
    // --- Cycle 11: Hold + monitor (2 days ago) ---
    {
      hoursAgo: 48,
      status: "success",
      assetDecisions: [
        { asset: "BTC/USDT", action: "hold", succeeded: true, confidence: 80, reasoning: "New position trending well, +1.2%" },
        { asset: "AAPL", action: "hold", succeeded: true, confidence: 81, reasoning: "At $196.50, approaching $198 TP" },
        { asset: "SPY", action: "hold", succeeded: true, confidence: 75, reasoning: "Steady uptrend" },
        { asset: "ETH/USDT", action: "hold", succeeded: true, confidence: 54, reasoning: "Sideways, no entry signal" },
        { asset: "SOL/USDT", action: "hold", succeeded: true, confidence: 59, reasoning: "Post-exit consolidation" },
      ],
      cot: holdCoT("portfolio", "BTC trending favorably (+1.2%). AAPL nearing TP at $198. SPY steady. No new signals above threshold. Portfolio well-positioned."),
      prompt: "Market data as of 2026-03-30T14:00:00Z — BTC: $89,250 | AAPL: $196.50 | SPY: $525.40 | ETH: $3,490 | SOL: $148.80 | Open: BTC LONG, AAPL LONG, SPY LONG",
      agents: {
        technical: "All positions trending within expectations. BTC above entry, AAPL approaching TP. No divergence signals detected.",
        sentiment: "FinBERT: bullish (0.71). Weekend approaching — crypto volume expected to decline. Equity sentiment stable.",
        risk: "Portfolio heat: 54%. All stops active. Unrealized PnL: +$428 (+3.96%). AAPL approaching TP — prepare for exit execution.",
        regime: "Multi-asset: MODERATE BULL consensus (72% avg). Weekend regime historically more volatile for crypto — tighten stops.",
      },
      durationMs: 8900,
    },
    // --- Cycle 12: AAPL TP hit + ETH re-entry (1.5 days ago) ---
    {
      hoursAgo: 36,
      status: "success",
      assetDecisions: [
        { asset: "AAPL", action: "close", succeeded: true, confidence: 88, reasoning: "Take profit hit at $198.10, +4.6% gain" },
        { asset: "ETH/USDT", action: "buy", succeeded: true, confidence: 83, reasoning: "Dencun upgrade catalyst + technical breakout above $3,520" },
        { asset: "BTC/USDT", action: "hold", succeeded: true, confidence: 82, reasoning: "Position active, trending up" },
        { asset: "SPY", action: "hold", succeeded: true, confidence: 76, reasoning: "Position active, steady trend" },
      ],
      cot: `1) AAPL take profit:\n- LONG 12 shares @ $189.45, TP hit at $198.10\n- Realized PnL: +$103.80 (+4.56%)\n- Clean exit at resistance level\n\n2) ETH opportunity:\n` +
        ethLongCoT(3525, 3440, 3700, "55.2", "+18%") +
        `\n\n3) Active positions: BTC LONG (+2.8%), SPY LONG (+0.9%)\n=> Rotate AAPL profits into ETH. Maintain BTC and SPY.`,
      prompt: "Market data as of 2026-03-31T02:00:00Z — AAPL: $198.10 (TP hit) | ETH: $3,522 | BTC: $90,600 | SPY: $527.20 | Open: BTC LONG, AAPL LONG (closing), SPY LONG",
      agents: {
        technical: "AAPL hit $198 resistance/TP perfectly. ETH breaking above $3,520 with Dencun upgrade momentum. Volume +18% on ETH. BTC strong at $90.6K.",
        sentiment: "FinBERT: ETH bullish (0.81), driven by upgrade narrative. AAPL neutral post-TP (0.55). BTC steady (0.72).",
        risk: "AAPL exit frees $2,273. ETH re-entry: Kelly 2.0%. Portfolio rotation maintains heat at 50%. Realized gains this week: +$458.",
        regime: "ETH: back to MODERATE BULL (77%). Upgrade catalyst provides fundamental support. BTC: MODERATE BULL (74%). SPY: MODERATE BULL (71%).",
        execution: "AAPL close: market at $198.10, perfect TP fill. ETH entry: limit at $3,525. Good liquidity at this level.",
      },
      durationMs: 15400,
    },
    // --- Cycle 13: Failure — API timeout (1 day ago) ---
    {
      hoursAgo: 24,
      status: "failure",
      assetDecisions: [
        { asset: "BTC/USDT", action: "sell", succeeded: false, confidence: 76, reasoning: "Attempted partial close but exchange API timed out" },
        { asset: "ETH/USDT", action: "hold", succeeded: true, confidence: 71, reasoning: "Position active" },
        { asset: "SPY", action: "hold", succeeded: true, confidence: 73, reasoning: "Position active" },
      ],
      cot: failureCoT("BTC/USDT", "Exchange API returned 504 Gateway Timeout after 30 seconds. Network congestion detected — Binance API latency at 4,200ms (normal: <200ms). BTC position remains open. Will retry partial close next cycle."),
      prompt: "Market data as of 2026-03-31T08:00:00Z — BTC: $91,200 | ETH: $3,548 | SPY: $526.80 | Open: BTC LONG, ETH LONG, SPY LONG",
      agents: {
        technical: "BTC at $91.2K — approaching resistance at $91.5K. Partial profit-taking recommended but execution failed.",
        sentiment: "FinBERT: neutral-bullish (0.66). Market in indecision zone near key levels.",
        risk: "BTC position at +3.4% unrealized. Attempted partial close to lock gains. API failure means full exposure maintained. Monitor closely.",
        regime: "BTC: MODERATE BULL but approaching overbought on daily. Transition probability to SIDEWAYS increasing to 22%.",
        execution: "EXECUTION FAILURE: Binance API 504 timeout at 2026-03-31T08:12:34Z. Retry queued for next cycle. Fallback: manual close if price drops below $90K.",
      },
      durationMs: 34200,
    },
    // --- Cycle 14: BTC partial close success (20 hours ago) ---
    {
      hoursAgo: 20,
      status: "success",
      assetDecisions: [
        { asset: "BTC/USDT", action: "sell", succeeded: true, confidence: 83, reasoning: "Partial close 50% at $91,350, locking in +3.6% on half position" },
        { asset: "ETH/USDT", action: "hold", succeeded: true, confidence: 74, reasoning: "Position active at +0.7%" },
        { asset: "SPY", action: "hold", succeeded: true, confidence: 72, reasoning: "Steady, no action needed" },
      ],
      cot: `1) BTC partial close (retry from failed cycle):\n- LONG 0.03 BTC @ $88,200\n- Current: $91,350 (+3.57%)\n- Closing 50%: sell 0.015 BTC\n- Realized on half: +$47.25\n- Remaining: 0.015 BTC with stop raised to $89,500 (breakeven+)\n\n2) ETH monitoring:\n- LONG 1.0 @ $3,525, current $3,548 (+0.65%)\n- Holding, no exit signal\n\n3) SPY steady at $527\n\n=> Strategy: De-risk BTC, let remaining run with protected stop. Hold ETH and SPY.`,
      prompt: "Market data as of 2026-03-31T12:00:00Z — BTC: $91,350 | ETH: $3,548 | SPY: $527.10 | Open: BTC LONG 0.03, ETH LONG 1.0, SPY LONG 5",
      agents: {
        technical: "BTC holding $91K but momentum slowing on 1H. MACD histogram flattening. Partial close prudent. ETH stable. SPY grinding higher.",
        sentiment: "FinBERT: neutral-bullish (0.64). Crypto weekend volume declining as expected. No major catalysts until Monday.",
        risk: "BTC partial close reduces portfolio heat from 54% to 42%. Stop on remaining BTC raised to $89,500 (breakeven+). Risk profile improved significantly.",
        regime: "BTC: MODERATE BULL (65%, declining). Weekend risk elevated. Partial de-risk aligns with regime uncertainty.",
        execution: "BTC partial close: 0.015 BTC sold at $91,350 via limit. Fill confirmed. Slippage: 1.2 bps. Remaining 0.015 BTC stop updated.",
      },
      durationMs: 12100,
    },
    // --- Cycle 15: Hold cycle (16 hours ago) ---
    {
      hoursAgo: 16,
      status: "success",
      assetDecisions: [
        { asset: "BTC/USDT", action: "hold", succeeded: true, confidence: 68, reasoning: "Reduced position, monitoring weekend price action" },
        { asset: "ETH/USDT", action: "hold", succeeded: true, confidence: 72, reasoning: "Position active, approaching TP zone" },
        { asset: "SOL/USDT", action: "hold", succeeded: true, confidence: 54, reasoning: "No re-entry signal" },
        { asset: "SPY", action: "hold", succeeded: true, confidence: 71, reasoning: "Weekend, markets closed" },
      ],
      cot: holdCoT("all positions", "Weekend mode: reduced activity. BTC half-position with protected stop. ETH approaching TP zone. SPY markets closed. No new entries during low-liquidity period."),
      prompt: "Market data as of 2026-03-31T16:00:00Z — BTC: $91,100 | ETH: $3,565 | SOL: $150.20 | Open: BTC LONG 0.015, ETH LONG 1.0, SPY LONG 5",
      agents: {
        technical: "Weekend consolidation. BTC range-bound $90.8K-$91.5K. ETH slowly grinding up. Low volume across all crypto pairs.",
        sentiment: "FinBERT: neutral (0.56). Weekend social media volume down 40%. No breaking news or catalysts.",
        risk: "Portfolio heat: 42%. All protected with stops. Weekend liquidity thin — avoid new entries. VaR estimate unreliable due to low volume.",
        regime: "Weekend regime: LOW CONVICTION. Historical weekend moves are noise. Recommend patience.",
      },
      durationMs: 8600,
    },
    // --- Cycle 16: ETH close + BTC trailing stop (12 hours ago) ---
    {
      hoursAgo: 12,
      status: "success",
      assetDecisions: [
        { asset: "ETH/USDT", action: "close", succeeded: true, confidence: 84, reasoning: "Take profit at $3,680, +4.4% gain" },
        { asset: "BTC/USDT", action: "hold", succeeded: true, confidence: 70, reasoning: "Trailing stop tightened to $90,200" },
        { asset: "SPY", action: "hold", succeeded: true, confidence: 72, reasoning: "Weekend, maintaining position" },
      ],
      cot: `1) ETH take profit:\n- LONG 1.0 ETH @ $3,525, current $3,680\n- Realized PnL: +$155.00 (+4.40%)\n- Dencun upgrade rally delivered target\n\n2) BTC management:\n- Remaining 0.015 BTC @ $88,200\n- Current $91,400, trailing stop → $90,200\n- Let it ride with protection\n\n3) Weekly performance:\n- Closed trades: BTC (+3.99%), SOL (+7.06%), AAPL (+4.56%), ETH (+4.40%)\n- Total realized: +$614\n- Win rate: 100% (4/4 closed trades)\n\n=> Excellent week. Maintain discipline, don't overtrade.`,
      prompt: "Market data as of 2026-03-31T20:00:00Z — ETH: $3,680 | BTC: $91,400 | SPY: $527.10 | Open: BTC LONG 0.015, ETH LONG (closing), SPY LONG 5",
      agents: {
        technical: "ETH reached TP zone at $3,680. Momentum indicators showing exhaustion on 4H. BTC range-bound but holding. Perfect time to bank ETH profits.",
        sentiment: "FinBERT: ETH neutral (0.54, post-rally cooling). BTC steady (0.65). Weekend wind-down.",
        risk: "ETH close: +$155 realized. Weekly realized PnL now +$614. Portfolio heat drops to 28%. Outstanding risk positions: BTC 0.015 + SPY 5 shares.",
        regime: "ETH: SIDEWAYS post-rally (confirmed). BTC: MODERATE BULL (63%). Weekly summary: all regime calls were accurate.",
        execution: "ETH close: market at $3,680. Clean fill at TP. BTC trailing stop updated to $90,200 via OCO order.",
      },
      durationMs: 14200,
    },
    // --- Cycle 17: New BTC long signal (8 hours ago) ---
    {
      hoursAgo: 8,
      status: "success",
      assetDecisions: [
        { asset: "BTC/USDT", action: "hold", succeeded: true, confidence: 72, reasoning: "Partial position active, trailing stop protecting gains" },
        { asset: "ETH/USDT", action: "hold", succeeded: true, confidence: 58, reasoning: "Post-exit, watching for re-entry below $3,550" },
        { asset: "SOL/USDT", action: "hold", succeeded: true, confidence: 63, reasoning: "Forming bull flag, not triggered yet" },
        { asset: "SPY", action: "hold", succeeded: true, confidence: 70, reasoning: "Pre-market Monday, await open" },
      ],
      cot: holdCoT("all assets", "Sunday evening scan. BTC trailing stop active at $90,200. ETH needs pullback for re-entry. SOL bull flag forming but not triggered. SPY pre-market Monday — wait for open to assess."),
      prompt: "Market data as of 2026-04-01T00:00:00Z — BTC: $91,600 | ETH: $3,640 | SOL: $151.40 | SPY: $527.10 (Friday close) | Open: BTC LONG 0.015, SPY LONG 5",
      agents: {
        technical: "BTC edging up to $91.6K. SOL forming bull flag — breakout above $153 triggers buy. ETH in post-rally pullback zone. Pre-market futures flat.",
        sentiment: "FinBERT: neutral-bullish (0.62). Sunday evening crypto volume picking up. Asia session starting. Moderate interest.",
        risk: "Portfolio heat: 28%. Well below 60% limit. Ready for 2-3 new positions if signals trigger Monday. Weekly performance: +5.7% realized.",
        regime: "BTC: MODERATE BULL (67%). SOL: forming MODERATE BULL (probability 62%). Monday often brings regime clarity.",
      },
      durationMs: 9400,
    },
    // --- Cycle 18: Monday morning scan (4 hours ago) ---
    {
      hoursAgo: 4,
      status: "success",
      assetDecisions: [
        { asset: "BTC/USDT", action: "hold", succeeded: true, confidence: 75, reasoning: "Position active at $91,800, trailing stop at $90,200" },
        { asset: "SOL/USDT", action: "buy", succeeded: true, confidence: 84, reasoning: "Bull flag breakout above $153 confirmed" },
        { asset: "SPY", action: "hold", succeeded: true, confidence: 71, reasoning: "Pre-market slightly positive" },
        { asset: "ETH/USDT", action: "hold", succeeded: true, confidence: 61, reasoning: "No clean entry yet" },
      ],
      cot: `1) SOL bull flag breakout:\n- Flag pattern: 3-day consolidation $148-$153\n- Breakout: price at $153.40, above flag resistance\n- Volume: +32% on breakout candle\n- RSI(14): 63.2, confirming momentum\n\n2) Entry plan:\n- Entry: $153.50 (market)\n- Stop: $148.00 (below flag support)\n- Target: $165.00 (measured move from flag pole)\n- Size: 12 SOL ($1,842, Kelly: 2.3%)\n- R:R: 2.1:1\n\n3) Portfolio update:\n- Adding SOL brings heat to 42%\n- BTC trailing, SPY holding\n\n=> Strategy: LONG SOL on bull flag breakout. Clean technical setup with defined risk.`,
      prompt: "Market data as of 2026-04-01T04:00:00Z — SOL: $153.40 (breakout!) | BTC: $91,800 | ETH: $3,620 | SPY futures: +0.3% | Open: BTC LONG 0.015, SPY LONG 5",
      agents: {
        technical: "SOL bull flag breakout confirmed! Price above $153 with volume surge. RSI 63.2, MACD histogram expanding. Measured move target: $165. BTC steady. SPY futures green.",
        sentiment: "FinBERT: SOL bullish (0.83). Ecosystem news: major NFT platform launching on Solana. Social buzz increasing. Crypto Fear & Greed: 64.",
        risk: "SOL entry: Kelly 2.3%. Portfolio heat increases to 42%. Three positions (BTC, SOL, SPY) — diversified across crypto and equities. Acceptable correlation.",
        regime: "SOL: STRONG BULL (82% confidence, upgraded). Bull flag breakouts in STRONG BULL regimes have 73% historical success rate.",
        execution: "SOL entry: market at $153.50. Breakout volume confirms institutional participation. Fill expected within seconds.",
      },
      durationMs: 11800,
    },
    // --- Cycle 19: Latest monitoring cycle (2 hours ago) ---
    {
      hoursAgo: 2,
      status: "success",
      assetDecisions: [
        { asset: "BTC/USDT", action: "hold", succeeded: true, confidence: 73, reasoning: "Position +3.6%, trailing stop at $90,500" },
        { asset: "SOL/USDT", action: "hold", succeeded: true, confidence: 80, reasoning: "New position at +1.2%, strong momentum" },
        { asset: "SPY", action: "hold", succeeded: true, confidence: 72, reasoning: "Awaiting market open" },
        { asset: "ETH/USDT", action: "hold", succeeded: true, confidence: 57, reasoning: "Watching for setup" },
        { asset: "AAPL", action: "hold", succeeded: true, confidence: 62, reasoning: "Evaluating re-entry after TP exit" },
      ],
      cot: `1) Portfolio status:\n- BTC LONG 0.015 @ $88,200 → $91,850 (+4.14%) — trailing stop $90,500\n- SOL LONG 12 @ $153.50 → $155.30 (+1.17%) — stop at $148\n- SPY LONG 5 @ $522.50 → $527+ — awaiting Monday open\n\n2) Risk summary:\n- Portfolio heat: 42%\n- Unrealized PnL: +$86 (BTC $54.75, SOL $21.60, SPY ~$23)\n- Weekly realized: +$614\n- Total week performance: +$700 estimated\n\n3) No new entries. All positions managed. Next scan in 2 hours.\n\n=> Strategy: Maintain positions, let winners run with trailing stops.`,
      prompt: "Market data as of 2026-04-01T06:00:00Z — BTC: $91,850 | SOL: $155.30 | ETH: $3,610 | SPY: $527+ (pre-market) | Open: BTC LONG 0.015, SOL LONG 12, SPY LONG 5",
      agents: {
        technical: "All positions trending favorably. BTC grinding up. SOL post-breakout momentum strong. No reversal signals on any timeframe.",
        sentiment: "FinBERT: bullish (0.72). Monday morning optimism. Asia session crypto volume healthy. Pre-market equities slightly green.",
        risk: "Portfolio in excellent shape. Heat: 42%. All stops active and protecting gains. Weekly performance on track for best week in 3 months.",
        regime: "BTC: MODERATE BULL (68%). SOL: STRONG BULL (80%). SPY: MODERATE BULL (71%). All regimes aligned — bullish consensus across portfolio.",
        execution: "No executions needed. All orders managed. Next evaluation: 2026-04-01T08:00:00Z.",
      },
      durationMs: 8200,
    },
    // --- Cycle 20: Most recent (30 minutes ago) ---
    {
      hoursAgo: 0.5,
      status: "success",
      assetDecisions: [
        { asset: "BTC/USDT", action: "hold", succeeded: true, confidence: 74, reasoning: "Trailing stop tightened to $91,000 as price tests $92K" },
        { asset: "SOL/USDT", action: "hold", succeeded: true, confidence: 82, reasoning: "Strong breakout continuation, +2.3% from entry" },
        { asset: "SPY", action: "hold", succeeded: true, confidence: 73, reasoning: "Market opening in 1 hour, pre-market +0.4%" },
        { asset: "ETH/USDT", action: "hold", succeeded: true, confidence: 60, reasoning: "Consolidating, no entry trigger" },
      ],
      cot: `1) Real-time scan:\n- BTC testing $92K resistance — tighten trailing stop to $91K\n- SOL at $157.10, +2.35% from entry, strong momentum\n- SPY pre-market +0.4%, expecting gap up at open\n- ETH consolidating $3,600-$3,640 range\n\n2) Key levels to watch:\n- BTC: break above $92K → target $95K, fail → back to $90K support\n- SOL: $160 next resistance (measured move midpoint)\n- SPY: $530 round number resistance at open\n\n3) Risk check:\n- All stops in place\n- Portfolio heat: 42%\n- No margin concerns\n\n=> Strategy: Hold all. BTC approaching key resistance — be ready to close if $92K rejection is sharp. SOL and SPY on autopilot.`,
      prompt: "Market data as of 2026-04-01T07:30:00Z — BTC: $92,020 | SOL: $157.10 | ETH: $3,625 | SPY pre-market: $529.20 (+0.4%) | Open: BTC 0.015, SOL 12, SPY 5",
      agents: {
        technical: "BTC testing $92K — key resistance. RSI(14)=68.2, approaching overbought but not there yet. SOL momentum continues. SPY pre-market gap up.",
        sentiment: "FinBERT: bullish (0.74). Monday morning flows typically favor continuation. Institutional pre-market buying detected on SPY.",
        risk: "All positions profitable. BTC trailing stop tightened to $91K to protect +$42 on remaining position. Total portfolio unrealized: +$142.",
        regime: "BTC: MODERATE BULL (66%, at regime edge). $92K test will determine if upgrade to STRONG BULL or reversal to SIDEWAYS. Critical moment.",
        execution: "No orders pending. Trailing stops active. Next automated scan: 2026-04-01T08:00:00Z. Manual override available via kill switch.",
      },
      durationMs: 9100,
    },
  ];

  let cycleNumber = 1;

  for (const t of templates) {
    const timestamp = new Date(now - t.hoursAgo * 3600_000).toISOString();
    decisions.push({
      id: generateId(),
      cycleNumber,
      timestamp,
      status: t.status,
      inputPrompt: t.prompt,
      chainOfThought: t.cot,
      assetDecisions: t.assetDecisions,
      agents: t.agents,
      durationMs: t.durationMs,
      modelVersion: "v2.0",
    });
    cycleNumber++;
  }

  decisions.sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );

  return { decisions, nextCycleNumber: cycleNumber };
}

// ---------------------------------------------------------------------------
// GET /api/trading/decisions
// ---------------------------------------------------------------------------

export async function GET(request: NextRequest) {
  try {
    let file = readDecisionsFile();

    // Seed if empty
    if (file.decisions.length === 0) {
      file = generateSeedDecisions();
      ensureTmpDir();
      await lockedReadModifyWrite<DecisionsFile>(
        DECISIONS_PATH_TMP,
        () => file,
      );
    }

    const url = new URL(request.url);
    const limit = Math.min(
      Math.max(parseInt(url.searchParams.get("limit") || "5", 10) || 5, 1),
      100,
    );
    const offset = Math.max(
      parseInt(url.searchParams.get("offset") || "0", 10) || 0,
      0,
    );
    const statusFilter = url.searchParams.get("status");
    const assetFilter = url.searchParams.get("asset")?.toUpperCase();

    let filtered = file.decisions;

    if (statusFilter && ["success", "failure", "partial"].includes(statusFilter)) {
      filtered = filtered.filter((d) => d.status === statusFilter);
    }

    if (assetFilter) {
      filtered = filtered.filter((d) =>
        d.assetDecisions.some((ad) =>
          ad.asset.toUpperCase().includes(assetFilter),
        ),
      );
    }

    // Sort newest first
    filtered.sort(
      (a, b) =>
        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
    );

    const total = filtered.length;
    const page = filtered.slice(offset, offset + limit);

    return NextResponse.json({ decisions: page, total });
  } catch (error) {
    console.error("Decisions GET error:", error);
    return NextResponse.json(
      { error: "Failed to load decisions" },
      { status: 500 },
    );
  }
}

// ---------------------------------------------------------------------------
// POST /api/trading/decisions
// ---------------------------------------------------------------------------

export async function POST(request: NextRequest) {
  try {
    const rawBody = await request.text();
    if (rawBody.length > MAX_BODY_SIZE) {
      return NextResponse.json(
        { error: "Request body too large (max 50KB)" },
        { status: 413 },
      );
    }

    const body = JSON.parse(rawBody) as Partial<DecisionRecord>;

    // Validate required fields
    if (!body.status || !["success", "failure", "partial"].includes(body.status)) {
      return NextResponse.json(
        { error: "status is required and must be success, failure, or partial" },
        { status: 400 },
      );
    }
    if (!body.chainOfThought) {
      return NextResponse.json(
        { error: "chainOfThought is required" },
        { status: 400 },
      );
    }
    if (!Array.isArray(body.assetDecisions) || body.assetDecisions.length === 0) {
      return NextResponse.json(
        { error: "assetDecisions array is required and must not be empty" },
        { status: 400 },
      );
    }

    ensureTmpDir();

    const result = await lockedReadModifyWrite<DecisionsFile>(
      DECISIONS_PATH_TMP,
      (current) => {
        const file: DecisionsFile = current ?? { decisions: [], nextCycleNumber: 1 };

        // If empty, seed first so cycle numbers make sense
        if (file.decisions.length === 0) {
          const seeded = generateSeedDecisions();
          file.decisions = seeded.decisions;
          file.nextCycleNumber = seeded.nextCycleNumber;
        }

        const newDecision: DecisionRecord = {
          id: generateId(),
          cycleNumber: file.nextCycleNumber,
          timestamp: body.timestamp || new Date().toISOString(),
          status: body.status!,
          inputPrompt: body.inputPrompt || "",
          chainOfThought: body.chainOfThought!,
          assetDecisions: body.assetDecisions!,
          agents: body.agents || {},
          durationMs: body.durationMs || 0,
          modelVersion: body.modelVersion || "v2.0",
        };

        file.decisions.push(newDecision);
        file.nextCycleNumber++;

        // Rolling cap
        if (file.decisions.length > MAX_ENTRIES) {
          file.decisions = file.decisions.slice(-MAX_ENTRIES);
        }

        // Stash the new decision for return — attach to file temporarily
        (file as DecisionsFile & { _new: DecisionRecord })._new = newDecision;

        return file;
      },
    );

    const newDecision = (result as DecisionsFile & { _new: DecisionRecord })._new;

    return NextResponse.json({ success: true, decision: newDecision });
  } catch (error) {
    console.error("Decisions POST error:", error);
    return NextResponse.json(
      { error: "Failed to record decision" },
      { status: 500 },
    );
  }
}
