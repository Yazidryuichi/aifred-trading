# QA Report 08: Data Integrity Audit

**Agent:** Data Integrity Analyst
**Date:** 2026-04-01
**Scope:** All data sources, metric provenance, fake/random data identification
**Verdict:** CRITICAL ISSUES FOUND -- headline metrics are derived from seeded random data with no live trade provenance

---

## 1. QA-032: Math.random() Audit

### 1.1 Complete Inventory -- TypeScript (Math.random)

| # | File | Line(s) | Context | Classification |
|---|------|---------|---------|----------------|
| 1 | `lib/execute-trade.ts` | 185, 857 | ID generation (`act_`, `ord_` prefixes) | LEGITIMATE -- unique ID generation |
| 2 | `lib/execute-trade.ts` | 230 | Slippage noise: `1 + (Math.random() - 0.5) * 0.4` | MISLEADING -- adds fake slippage to paper trades, displayed as if real execution quality |
| 3 | `lib/hmm-regime.ts` | 141, 159, 169 | K-means++ initialization (centroid selection) | LEGITIMATE -- algorithm randomization |
| 4 | `lib/record-decision.ts` | 88 | ID generation | LEGITIMATE |
| 5 | `lib/backtester.ts` | 231 | Confidence for neutral regime: `0.4 + Math.random() * 0.15` | MISLEADING -- random confidence injected into regime detection, affects downstream signals |
| 6 | `lib/strategy-learning.ts` | 55 | Weighted random strategy selection | LEGITIMATE -- exploration mechanism |
| 7 | `lib/strategy-learning.ts` | 66 | Fallback confidence: `70 + Math.floor(Math.random() * 15)` | MISLEADING -- generates fake confidence when insufficient data, user sees this as AI analysis |
| 8 | `lib/strategy-learning.ts` | 71 | Confidence variation: `(Math.random() - 0.5) * 6` | MINOR -- small noise on real base value |
| 9 | `app/api/trading/activity/route.ts` | 86 | ID generation | LEGITIMATE |
| 10 | `app/api/trading/activity/route.ts` | 194-225 | **generateTechnicalSignals(), generateSentimentSignals(), generateRiskAssessment()** -- RSI, MACD, FinBERT scores, Kelly sizing, R:R ratios ALL randomly generated | **CRITICAL MISLEADING** -- these fake signals enrich real trade activity entries and appear as genuine AI analysis |
| 11 | `app/api/trading/activity/route.ts` | 271-278 | Seed activity generator: random assets, random scan results | MISLEADING -- fake scan history |
| 12 | `app/api/trading/autoscan/route.ts` | 129 | ID generation | LEGITIMATE |
| 13 | `app/trading/decisions/page.tsx` | 49-60 | **generateMockDecisions()** -- RSI, MACD, FinBERT, Kelly, regime confidence ALL random | **CRITICAL MISLEADING** -- 60 fake decision records with random AI agent outputs displayed as real decision history |
| 14 | `app/api/trading/brokers/route.ts` | 31 | ID generation | LEGITIMATE |
| 15 | `app/api/trading/decisions/route.ts` | 67, 144 | ID generation + random confidence in seed data | MISLEADING |
| 16 | `app/api/trading/brokers/test/route.ts` | 145 | Mock latency delay | LEGITIMATE -- test only |
| 17 | `components/trading/TradingDashboard.tsx` | 91 | ID generation | LEGITIMATE |
| 18 | `components/trading/tabs/ActivityTab.tsx` | 43 | Fallback ID generation | LEGITIMATE |
| 19 | `components/trading/tabs/OverviewTab.tsx` | 273 | Fallback ID generation | LEGITIMATE |
| 20 | `app/api/trading/controls/route.ts` | 38 | ID generation | LEGITIMATE |

### 1.2 Complete Inventory -- Python (random.*)

| # | File | Line(s) | Context | Classification |
|---|------|---------|---------|----------------|
| 1 | `python/seed_demo_data.py` | 99-266 | **Entire file** -- generates 250 fake trades with random prices, PnL, confidence, RSI, strategies, reasoning text | **CRITICAL MISLEADING** -- this is the source of ALL dashboard metrics |
| 2 | `python/src/optimizer/autoresearch.py` | 300-358 | Hyperparameter search space sampling | LEGITIMATE -- optimization algorithm |
| 3 | `python/src/optimizer/strategy_tournament.py` | 242 | Performance noise for tournament | LEGITIMATE -- simulation |
| 4 | `python/src/execution/paper_trader.py` | 65 | Slippage noise: `1.0 + (random.random() - 0.5) * 0.4` | MINOR -- paper trading simulation |
| 5 | `python/src/utils/resilience.py` | 384, 464 | Jitter for retry backoff | LEGITIMATE -- standard retry pattern |

### 1.3 Summary

- **LEGITIMATE:** 14 occurrences (ID generation, algorithm randomization, retry jitter)
- **MISLEADING:** 8 occurrences (fake signals displayed as AI analysis, fake metrics)
- **CRITICAL MISLEADING:** 3 major systems (`seed_demo_data.py`, `generateTechnicalSignals()`, `generateMockDecisions()`)

---

## 2. Performance Metrics Provenance

### 2.1 "Sharpe 7.31" -- FAKE

**Source chain:**
1. `python/seed_demo_data.py` generates 250 random trades with biased win rate (65-95% probability, line 214-215)
2. `python/export_trading_data.py` reads those trades from `data/trading.db`, computes Sharpe ratio using trade-level returns (NOT daily returns), writes to `data/trading-data.json`
3. `data/trading-data.json` line 7: `"sharpeRatio": 7.31`
4. `app/api/trading/stats/route.ts` reads this file and serves it

**Why 7.31 is impossible:** The Sharpe is calculated per-trade (not per-day) with `sqrt(252)` annualization. With 242 trades biased toward wins over 30 days, the mean/stddev ratio is artificially inflated. A real portfolio Sharpe above 3.0 is exceptional; 7.31 is fantasy.

**Formula correctness:** The `export_trading_data.py` Sharpe formula (line 70) uses population-level variance on per-trade returns with `sqrt(252)` annualization -- this is mathematically incorrect for trade-level (not time-series) data. The `app/api/trading/stats/route.ts` version (line 77-78) uses per-trade P&L with `sqrt(252)`, same error.

### 2.2 "Win Rate 78.1%" -- FAKE

**Source chain:**
1. `seed_demo_data.py` line 214: `win_prob = 0.65 + win_boost` where `win_boost = (confidence - 68) / 100`. Since confidence ranges 68-98, win probability ranges 0.65 to 0.95.
2. The script deliberately engineers a high win rate: "# Optimized: 72% win rate (was 62%)" (line 211)
3. Exported as `"winRate": 78.1` in `trading-data.json` line 4

**Verdict:** This is a tuned parameter in a random data generator, not a measured trading outcome.

### 2.3 "$54.6K P&L" -- FAKE (two separate fakes)

**Source 1 -- Overview Tab:** `data/trading-data.json` line 3: `"totalPnl": 54602.76` -- computed from 242 seeded trades.

**Source 2 -- Arena page:** `lib/arena-data.ts` line 93: `scaleToTarget(claudeRaw, 54.6)` -- hardcoded target PnL% of 54.6% scaled onto a procedurally generated random-walk equity curve (seeded PRNG, seed=42). The "Claude Ensemble" strategy with 68.4% win rate, 2.31 Sharpe, 187 trades is entirely fabricated in lines 112-129.

### 2.4 Sortino Ratio -- FABRICATED

`components/trading/tabs/OverviewTab.tsx` line 413:
```typescript
sub={`Sortino: ${(summary.sharpeRatio * 1.3).toFixed(2)}`}
```
The Sortino ratio displayed in the UI is literally `Sharpe * 1.3` -- a completely fabricated number with no calculation behind it. The Python backend has a proper Sortino implementation (`python/src/risk/risk_metrics.py` lines 40-65) but it is never used for the dashboard display.

---

## 3. Dashboard Data Sources

### 3.1 `data/trading-data.json` -- SEEDED, NOT REAL

- Generated by `python/export_trading_data.py` reading from `data/trading.db`
- `data/trading.db` is created by `python/seed_demo_data.py` which deletes any existing DB (line 151-152) and writes 250 random trades
- Contains summary metrics, equity curve, per-asset/strategy/tier breakdowns, and 50 recent trades
- **No mechanism exists to populate this file from real trades**

### 3.2 `data/activity-log.json` -- SEEDED ON FIRST ACCESS

- `app/api/trading/activity/route.ts` line 584: `if (activities.length === 0) { activities = generateSeedActivities(); }`
- `generateSeedActivities()` creates ~15 hardcoded-but-random-enriched activities (trade executions, scans, signals)
- The `enrichTradeDetails()` function (line 164) backfills missing technical/sentiment/risk fields with `Math.random()` values
- Real activities CAN be appended via POST, but seed data is never cleared

### 3.3 API Routes Returning Demo/Fake Data

| Route | Data Source | Real or Fake |
|-------|-----------|--------------|
| `/api/trading/stats` | `trading-data.json` | FAKE -- from seed script |
| `/api/trading/performance` | `trading-data.json` | FAKE |
| `/api/trading/equity-history` | `trading-data.json` equityCurve | FAKE |
| `/api/trading` | `trading-data.json` | FAKE |
| `/api/trading/activity` | Seeds on empty, enriches with random signals | MIXED -- real POSTs possible, but initial data is fake |
| `/api/trading/decisions` | Seeds 25 fake decisions if empty | MIXED |
| `/api/trading/hyperliquid` | Live Hyperliquid API | REAL (when configured) |
| `/api/trading/positions` | Hyperliquid or fallback to trading-data.json | MIXED |
| `/api/trading/broker-status` | Live connectivity check | REAL |

### 3.4 Arena Competition Data -- ENTIRELY FABRICATED

`lib/arena-data.ts` generates fake competition data for "Claude Ensemble", "DeepSeek Momentum", and "Gemini Balanced" using seeded random walks with hardcoded target returns (54.6%, 41.2%, 28.7%). The comment on line 2 says "Generates realistic competition data" -- this is simulation presented as competition results.

---

## 4. Live vs Demo Data Separation

### 4.1 Toggle Mechanism Exists

- `stores/viewMode.ts` provides a `"live" | "demo"` toggle (defaults to `"live"`)
- `components/trading/HeroMetrics.tsx` shows a "DEMO" badge when in demo mode (line 93-96)
- `components/trading/PositionsTable.tsx` shows live Hyperliquid positions vs demo positions
- `components/AccountSummaryBar.tsx` switches between Hyperliquid data and `trading-data.json`

### 4.2 Disclaimers Present (Partial)

Found disclaimers in:
- `components/trading/tabs/OverviewTab.tsx` lines 370-386: "DEMO DATA -- Simulated Backtest" banner
- `components/trading/tabs/OverviewTab.tsx` line 523: equity curve disclaimer
- `components/trading/tabs/RegimeTab.tsx` line 328-332: "DEMO DATA -- Simulated results"
- `components/trading/HeroMetrics.tsx`: "DEMO" badge on metric cards

### 4.3 Critical Gaps in Separation

1. **Default mode is "live" but data is fake:** `viewMode.ts` defaults to `mode: "live"` (line 13), but when Hyperliquid is not connected, the dashboard silently falls back to `trading-data.json` data. A user sees "LIVE" mode showing seeded data.

2. **Decisions page has no disclaimer:** `app/trading/decisions/page.tsx` uses `ALL_MOCK = generateMockDecisions(60)` (line 67) with zero disclaimer. Users see 60 fake AI decision records with fabricated RSI, MACD, FinBERT scores, and Kelly sizing.

3. **Activity log blends real and fake:** When the activity log is empty, it seeds with fake data. Subsequent real activities are appended. There is no visual distinction between seeded entries and real ones.

4. **Strategy learning uses hardcoded fake stats:** `lib/strategy-learning.ts` lines 23-28 contain `DEFAULT_STATS` with fabricated trade counts (48, 52, 61, 44, 37 trades) and win rates. These are used when no persistent stats exist.

5. **Arena page shows no disclaimer:** The competition between "Claude", "DeepSeek", and "Gemini" strategies with fabricated equity curves and Sharpe ratios has no "demo" or "simulated" warning.

6. **Can a user see seeded data as real? YES.** If Hyperliquid is not configured, the dashboard defaults to "live" mode, shows no Hyperliquid connection, but still displays the seeded metrics ($54.6K P&L, 78.1% win rate, Sharpe 7.31) without any automatic demo mode switch or warning.

---

## 5. Audit Trail

### 5.1 SHA-256 Hash Chain Implementation

`python/src/monitoring/audit_trail.py` implements a proper append-only, hash-chained audit trail:
- Records stored in JSONL format with daily rotation (`audit_YYYY-MM-DD.jsonl`)
- Each record includes `previous_hash` and `record_hash` (truncated to 16 hex chars)
- `verify_chain()` method validates hash continuity and content integrity
- Hash is SHA-256 of JSON-serialized record (with `record_hash` field removed before hashing)
- Records include: trade decisions, position closures, safety events, system events
- Supports full trade context: technical signal, sentiment signal, fused signal, meta reasoning, risk state

### 5.2 Implementation Quality

- **Correct:** Hash chain logic is sound. Records are append-only. `_restore_last_hash()` rebuilds chain state on restart.
- **Minor issue:** Hash is truncated to 16 hex chars (64 bits) instead of full 256 bits. This reduces collision resistance but is acceptable for tamper detection (not cryptographic security).
- **Gap:** The file handle is kept open (`self._current_file`) but `flush()` is called after each write. If the process crashes between write and flush, the last record could be lost.

### 5.3 Production Usage

The audit trail is integrated into the Python trading engine. However, the Next.js frontend dashboard does NOT read from audit trail files. The dashboard reads from `trading-data.json` (seeded data). The audit trail exists in a parallel data path that is disconnected from the UI.

---

## 6. Export & Reporting Formulas

### 6.1 `python/export_trading_data.py` -- Formula Audit

| Metric | Formula | Correct? | Issue |
|--------|---------|----------|-------|
| Win Rate | `wins / closed * 100` | Yes | N/A |
| Avg Win/Loss | `gross / count` | Yes | N/A |
| Profit Factor | `gross_wins / gross_losses` | Yes | N/A |
| Max Drawdown | Peak-to-trough on cumulative equity | Yes | N/A |
| Sharpe Ratio | `(mean_return / std_return) * sqrt(252)` | **WRONG** | Uses per-trade returns, not periodic (daily) returns. Annualizes with sqrt(252) which assumes daily periodicity. With 242 trades in 30 days (~8 trades/day), this massively overstates the ratio. |
| Sortino Ratio | Not calculated | **MISSING** | Only displayed as `Sharpe * 1.3` in the frontend |
| Equity Curve | Cumulative P&L from $100K starting | Correct | But data is from seeded trades |

### 6.2 `python/src/risk/risk_metrics.py` -- Properly Implemented

The Python risk module has correct implementations of Sharpe (with risk-free rate adjustment, ddof=1) and Sortino (downside-only deviation). These are used in the backtesting engine and walk-forward optimizer but are NOT connected to the dashboard export pipeline.

### 6.3 `app/api/trading/stats/route.ts` -- Same Sharpe Bug

Line 77-78: `(meanPnl / stdDev) * Math.sqrt(252)` -- same per-trade annualization error as the Python export script.

---

## 7. REAL vs FAKE Classification Summary

| Displayed Metric/Data | Source | Classification | User-Facing? |
|----------------------|--------|----------------|-------------|
| $54,602.76 Total P&L | seed_demo_data.py | **FAKE** | Yes -- headline metric |
| 78.1% Win Rate | seed_demo_data.py | **FAKE** | Yes -- headline metric |
| Sharpe 7.31 | export_trading_data.py (wrong formula on fake data) | **FAKE + WRONG** | Yes -- headline metric |
| Max Drawdown 0.59% | export_trading_data.py on fake data | **FAKE** | Yes |
| Profit Factor 10.26 | export_trading_data.py on fake data | **FAKE** | Yes |
| Sortino (displayed) | `Sharpe * 1.3` | **FABRICATED** | Yes |
| Equity Curve | 242 seeded trades cumulated | **FAKE** | Yes -- chart |
| Arena: Claude +54.6% | Hardcoded target in arena-data.ts | **FAKE** | Yes |
| Arena: DeepSeek +41.2% | Hardcoded target in arena-data.ts | **FAKE** | Yes |
| Arena: Gemini +28.7% | Hardcoded target in arena-data.ts | **FAKE** | Yes |
| Decision History (60 entries) | generateMockDecisions() | **FAKE** | Yes -- no disclaimer |
| Activity Log (initial) | generateSeedActivities() + random enrichment | **FAKE** | Yes |
| Strategy Stats (default) | DEFAULT_STATS hardcoded array | **FAKE** | Yes -- used for strategy selection |
| Technical Signals in activity | Math.random() RSI, MACD, etc. | **FAKE** | Yes -- looks like real AI output |
| Sentiment Signals in activity | Math.random() FinBERT, Fear&Greed | **FAKE** | Yes -- looks like real AI output |
| Hyperliquid positions | Live API | **REAL** | Yes (when connected) |
| Hyperliquid balance | Live API | **REAL** | Yes (when connected) |
| Audit trail records | Real trade engine | **REAL** | No -- not shown in UI |

---

## 8. Critical Findings

### CRITICAL-01: All headline metrics are derived from seeded random data
The numbers $54.6K P&L, 78.1% win rate, Sharpe 7.31 are computed from 250 randomly generated trades in `seed_demo_data.py`. The seed script deliberately biases wins (65-95% probability) and uses asymmetric P&L (wins up to +5.5%, losses capped at -2.2%). This produces impossibly good metrics.

### CRITICAL-02: Sharpe ratio formula is mathematically incorrect
Both `export_trading_data.py` and `app/api/trading/stats/route.ts` compute Sharpe using per-trade returns annualized with `sqrt(252)`. This is wrong -- Sharpe should use time-series returns (daily/weekly). The same error exists in both Python and TypeScript.

### CRITICAL-03: Sortino ratio is fabricated as Sharpe * 1.3
`components/trading/tabs/OverviewTab.tsx` line 413 displays Sortino as a constant multiple of Sharpe with no actual downside deviation calculation.

### CRITICAL-04: Fake AI signals presented as real analysis
`generateTechnicalSignals()`, `generateSentimentSignals()`, and `generateRiskAssessment()` in `app/api/trading/activity/route.ts` produce random RSI values, random FinBERT scores, and random Kelly sizing that are attached to activity entries. These look identical to real AI analysis output.

### CRITICAL-05: No automatic demo mode when Hyperliquid is disconnected
The view mode defaults to "live" but silently falls back to seeded data. There is no forced switch to demo mode when no live data source is available.

### CRITICAL-06: Decisions page has zero disclaimer
60 mock decisions with fabricated AI agent outputs (RSI, MACD, FinBERT, Kelly, regime confidence) are shown without any "demo" or "simulated" label.

### HIGH-01: Arena competition data is entirely procedural
Three "AI strategies" competing with fabricated equity curves and hardcoded performance targets. No disclaimer.

### HIGH-02: Audit trail is disconnected from dashboard
The well-implemented SHA-256 hash-chained audit trail in Python never feeds the Next.js dashboard. Real trade decisions logged by the Python engine are invisible to users.

### MEDIUM-01: Strategy learning system bootstraps from fabricated defaults
`DEFAULT_STATS` in `strategy-learning.ts` contains fake trade histories that influence live strategy selection until enough real trades accumulate.

---

## 9. Recommendations

1. **Add forced demo mode:** When Hyperliquid (or any live broker) is not connected, force `viewMode` to "demo" and prevent switching to "live".
2. **Add disclaimers to all pages:** Decisions page, Arena page, and any page showing seeded data must display clear "SIMULATED DATA" warnings.
3. **Fix Sharpe calculation:** Use daily returns (aggregate trades by day) for Sharpe computation, not per-trade returns.
4. **Compute Sortino properly:** Either use the Python `risk_metrics.py` implementation or port it to TypeScript. Remove the `* 1.3` hack.
5. **Connect audit trail to dashboard:** Surface real audit trail records in the UI alongside or instead of seeded data.
6. **Clearly label all seed functions:** Rename `generateSeedActivities` to `generateDemoActivities` and tag all output with a `demo: true` field.
7. **Separate demo data visually:** Use a distinct color scheme or persistent banner for demo data vs live data.

---

*Report generated by Data Integrity Analyst. All findings are research-only; no files were modified.*
