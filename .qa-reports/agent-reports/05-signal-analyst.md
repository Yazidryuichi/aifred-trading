# Signal Flow Analysis Report

**Agent**: 05 -- Signal Flow Analyst  
**Date**: 2026-04-01  
**Scope**: Complete signal path from data ingestion to trade execution  
**Status**: RESEARCH ONLY -- no files modified

---

## 1. Signal Flow Diagram

```
                         MarketDataProvider.get_data()
                                   |
                    +--------------+--------------+
                    |                             |
              Binance (ccxt)              Hyperliquid fallback
              _fetch_crypto()             /USDT -> /USDC:USDC
                    |                             |
                    +-------------+---------------+
                                  |
                       OHLCV DataFrame + compute_indicators()
                       (atr, sma_20/50, ema_12/26, rsi, macd, bb)
                                  |
              +-------------------+-------------------+
              |                   |                   |
    TechnicalAnalysisAgent   SentimentAnalysisAgent   OnChainAggregator
         analyze()               analyze()           generate_signal()
              |                   |                   |
        [60% weight]        [40% weight]         [~18% weight]
              |                   |                   |
              +-------------------+-------------------+
                                  |
                        Orchestrator._fuse_signals()
                         (weighted geometric mean)
                                  |
                     Meta-Reasoning (optional LLM)
                                  |
                     Confidence Threshold Gate (78%)
                                  |
                     RiskGate.evaluate()
                      (tier A+/A/B/C, volatility regime,
                       drawdown, correlation, position sizing)
                                  |
                     ExecutionAgent.execute()
                      (paper mode default)
```

---

## 2. Data Ingestion Layer

**File**: `python/src/datafeeds/market_data_provider.py`

### Binance -> Hyperliquid Fallback (VERIFIED)

The fallback is correctly implemented in `_fetch_crypto()` (lines 359-402):

1. **Primary**: Attempts `exchange.fetch_ohlcv()` on the default exchange (Binance)
2. **Error handling**: Catches `NetworkError`, `ExchangeNotAvailable`, `ExchangeError`, and `BadSymbol`
3. **Fallback trigger**: If `ohlcv` is falsy AND default exchange is not already `hyperliquid`
4. **Symbol mapping**: `asset.replace("/USDT", "/USDC:USDC")` -- correctly maps Binance perp format to Hyperliquid perp format
5. **Lazy init**: Creates `self._hl_fallback` once via `ccxt.hyperliquid()`

### Symbol Mapping Concern

The mapping `"/USDT" -> "/USDC:USDC"` only handles USDT-quoted pairs. If a pair is quoted in something else (e.g., `BTC/BUSD`), the fallback will attempt to fetch `BTC/BUSD` on Hyperliquid, which will fail silently (caught by generic `except Exception`). Not a critical bug since all primary pairs use USDT, but worth noting.

### Indicator Pipeline

`compute_indicators()` adds: ATR(14), SMA(20,50), EMA(12,26), RSI(14), MACD, Bollinger Bands(20,2). All use `min_periods=1` so they never produce NaN rows -- this means early values are smoothed approximations, not true indicators. The technical analysis module re-computes indicators via its own `compute_indicators` from `src.analysis.technical.indicators`, which may differ.

---

## 3. Technical Analysis Signal (60% Weight)

**File**: `python/src/analysis/technical/signals.py`

### Full Pipeline

```
analyze(asset, data)
  -> compute_indicators(data)           # from technical.indicators
  -> compute_rule_signals(df)           # rule-based signals
  -> FeatureEngineer.build_features()   # feature engineering
  -> get_feature_matrix()               # scaled feature matrix
  -> _ensure_initialized(n_features)    # lazy model init
  -> LSTM.predict(latest_seq)           # sequence model
  -> Transformer.predict(latest_seq)    # attention model
  -> PatternCNN.predict(ohlcv_input)    # pattern recognition
  -> EnsembleMetaLearner.predict()      # XGBoost stacking
  -> _apply_signal_gates()              # quality filter
```

### When `_ML_AVAILABLE = False` (CRITICAL PATH)

Lines 245-260: Returns a **HOLD signal with confidence 0.0** and metadata `"reason": "ml_models_unavailable"`. This means:

- The technical agent contributes NOTHING to the fused signal
- It still provides indicator metadata (RSI, MACD, BB%, ADX, volume_ratio) but these are informational only
- The signal is `direction=HOLD, confidence=0.0`

### Signal Gating (lines 301-364)

Three gates applied sequentially:
1. **Minimum confidence**: 75% (hardcoded `MIN_CONFIDENCE_THRESHOLD`)
2. **Minimum confluences**: 4 (with +5% at 5 confluences, +10% at 6+)
3. **Kill zone adjustment**: +15% in institutional sessions, -15% outside

These gates can only DOWNGRADE a signal to HOLD; they never upgrade it.

### Ensemble Meta-Learner

**File**: `python/src/analysis/technical/ensemble.py`

- Uses XGBoost as stacking meta-learner
- Requires 80% ensemble agreement (`MIN_ENSEMBLE_AGREEMENT = 0.80`)
- Signal tiers: A+ (>85%), A (>75%), B (>65%), C (<65%)
- Dynamic model weights via EMA of recent accuracy
- Needs 15+ trades before EMA weights activate

---

## 4. Sentiment Signal (40% Weight)

**File**: `python/src/analysis/sentiment/sentiment_signals.py`

### Sub-Component Weights

```
finbert:  0.32  (FinBERT text classification)
llm:      0.40  (Claude API deep analysis)
social:   0.08  (Reddit via PRAW)
event:    0.20  (Event detection)
```

### FinBERT (`finbert_model.py`)
- Model: ProsusAI/finbert
- Platt-scaling confidence calibration
- Source quality multipliers (institutional: 1.5x, forum: 0.4x)
- Multi-timeframe decay with configurable half-lives
- Noise filtering via distribution entropy

### LLM Analyzer (`llm_analyzer.py`)
- Uses `claude-sonnet-4-5-20250929` via Anthropic API
- Dual-speed: deep chain-of-thought for urgency >= 5, fast prompt otherwise
- Falls back to FinBERT if `ANTHROPIC_API_KEY` is missing
- Confidence is multiplied by source reliability (0.6-1.0) and information quality (0.3-1.0)
- Maximum theoretical LLM confidence: 1.0 * 1.0 * 1.0 = 1.0 (unlikely in practice)

### Social Aggregator (`social_aggregator.py`)
- Uses PRAW (Reddit API) -- requires `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`
- Default subreddits: `cryptocurrency`, `bitcoin`, `wallstreetbets`
- Spam filtering, deduplication (MD5 content hash, 6h TTL)
- Engagement quality scoring (upvote ratio + comments + text length)
- Subreddit quality tiers (r/investing: 0.8, r/wallstreetbets: 0.4)
- Mention velocity tracking with acceleration

### Consensus Mechanism
- Requires `_MIN_CONSENSUS_SOURCES = 3` sources agreeing for undampened signal
- Without consensus: signal strength dampened by 50%, confidence dampened by 50%
- With only 2 sources available, consensus is mathematically IMPOSSIBLE (need 3 agreeing)
- This is a significant constraint on realistic confidence output

### Contrarian Override
- Fear & Greed <= 15 + bearish consensus = contrarian buy
- Fear & Greed >= 90 + bullish consensus = contrarian sell
- Applies 0.7x confidence multiplier on contrarian signals

---

## 5. On-Chain Signal

**File**: `python/src/analysis/onchain/onchain_aggregator.py`

### Data Sources
- **DeFiLlama**: TVL trend, stablecoin flows, DEX volumes (no API key required)
- **Etherscan** (`etherscan_onchain.py`): Whale transfers, exchange flow, gas prices

### Etherscan Details
- Works without API key at 1 req/5sec (free tier)
- With `ETHERSCAN_API_KEY`: 5 req/sec
- Whale threshold: >= 100 ETH
- Exchange flow: tracks 14 known exchange hot wallets
- Caching: gas=2min, transfers=5min, holders=1hr

### Component Weights for Composite Confidence
```
tvl_trend:       0.25
stablecoin_flow: 0.20
whale_activity:  0.20
exchange_flow:   0.15
gas_activity:    0.10
dex_volume:      0.10
```

### When Etherscan Is Missing
If `ETHERSCAN_API_KEY` is not set, Etherscan still works (free tier), just slower. If the API is unreachable, each component returns `confidence=0.0` and is excluded from the weighted average. DeFiLlama components (TVL, stablecoins, DEX) still contribute.

---

## 6. Signal Fusion (The Core)

**File**: `python/src/orchestrator.py`, method `_fuse_signals()` (lines 1227-1391)

### Weight Configuration
```
tech_weight:    0.60  (configurable, degradation-adjustable)
sent_weight:    0.40  (configurable, degradation-adjustable)
onchain_weight: 0.18  (when available, re-normalizes tech+sent)
```

### Fusion Logic

**Both signals present (normal case)**:
1. Convert directions to numeric: STRONG_BUY=1.0, BUY=0.5, HOLD=0.0, SELL=-0.5, STRONG_SELL=-1.0
2. If on-chain available: re-normalize tech+sent to make room for 18% on-chain
3. Fused direction = weighted average of numeric directions
4. Fused confidence = **geometric mean**: `(tech_conf ^ tech_w) * (sent_conf ^ sent_w) * 100`
5. Agreement bonus: aligned signals get 1.35x boost; conflicting signals get 0.50x penalty

**Only tech signal available**:
- `confidence = tech_signal.confidence * tech_weight * 0.7` (single-signal penalty)
- With tech_weight=0.60: effective confidence = original * 0.42

**Only sentiment signal available**:
- `confidence = sentiment_signal.confidence * sent_weight * 0.7` (single-signal penalty)
- With sent_weight=0.40: effective confidence = original * 0.28

**Neither signal available**: Returns `None` (no trade)

### Critical Bug in Confidence Formula

The geometric mean formula `(tech_conf ^ 0.6) * (sent_conf ^ 0.4) * 100` treats confidence values as percentages (0-100). For example:

- tech_conf=85%, sent_conf=70%: `85^0.6 * 70^0.4 * 100 = 21.42 * 8.80 * 100` ... this does NOT work as expected.

Wait -- re-examining: the confidence values on Signal objects are in percentage (0-100). So `85^0.6 = 21.42` and `70^0.4 = 8.80`, giving `21.42 * 8.80 * 100 = ~18,850`. This would be clamped to 100 by `min(100.0, ...)` at line 1370.

Actually this formula is a **weighted geometric mean on percentages**, which is mathematically unusual. For it to produce meaningful results, the confidence needs to be near 1.0 (i.e., 0-1 scale). If confidence is on a 0-100 scale, the formula is broken -- it will always produce numbers >> 100 that get clamped. Let me verify the scale.

The orchestrator threshold is `min_confidence = 78` (line 196), and the technical agent returns confidence in percentage (0-100). The sentiment agent explicitly converts to percentage at line 304: `confidence_pct = min(100.0, max(0.0, final_confidence * 100.0))`.

**Conclusion**: Both signals produce confidence on a 0-100 scale. The geometric mean formula `(85^0.6) * (70^0.4) * 100` = `21.42 * 8.80 * 100 = 18,850` -- this will always be clamped to 100.0. The formula essentially always produces maximum confidence when both signals have non-trivial confidence. This is a **significant bug** -- the confidence fusion provides no discrimination. The only thing that modulates the fused confidence is the agreement multiplier (1.35x or 0.50x), but since the base is already clamped to 100, even the penalty still produces 50+.

### Post-Fusion Pipeline

1. **Degradation penalty**: Subtracted from confidence (configurable)
2. **Meta-reasoning** (optional): LLM can adjust confidence and position size
3. **Confidence threshold**: Must exceed 78% (configurable `min_confidence_threshold`)
4. **Risk gate**: Tier-based (A+ >= 85%, A >= 75%, B >= 60%, C < 60%)
5. **Execution**: Paper mode by default (`exec_cfg.mode == "paper"`)

---

## 7. Execution Path

### Risk Gate (`risk_gate.py`)
- Classifies signal into tier: A+ (>=85), A (>=75), B (>=60), C (<60)
- B and C tiers are rejected by default
- Volatility regime adjustments: low=-5, normal=0, high=+10, extreme=+20
- Checks: drawdown limits, correlation exposure, position sizing

### Paper vs Live Mode
- Controlled by `execution.mode` config (default: "paper")
- Set at orchestrator init (line 205): `self._paper_mode = exec_cfg.get("mode", "paper") == "paper"`
- Passed to execution agent at construction

### Circuit Breakers
- Max daily trades: 20
- Max daily loss: 5%
- Max consecutive failures: 3
- Auto-reset daily

---

## 8. Bottleneck Analysis

### Critical Bottleneck 1: Geometric Mean Confidence Formula (SEVERITY: HIGH)

The formula `(tech_conf^tech_w) * (sent_conf^sent_w) * 100` on 0-100 scale values is mathematically broken. It produces values >>100 that get clamped. This means:
- Every dual-signal fusion produces ~100% confidence before agreement adjustment
- The 0.50x conflict penalty still yields ~50%, which passes the 78% threshold? No -- 100 * 0.50 = 50 which FAILS the threshold. So conflicting signals are correctly filtered.
- But aligned signals ALWAYS pass regardless of individual signal strength (100 * 1.35 = 100, clamped).

**Impact**: The system cannot distinguish between a weak-aligned signal (tech=62%, sent=55%) and a strong-aligned signal (tech=95%, sent=90%). Both produce 100% fused confidence.

**Fix needed**: Normalize confidence to 0-1 scale before geometric mean, then multiply by 100 after.

### Critical Bottleneck 2: Consensus Impossible with 2 Sources (SEVERITY: MEDIUM)

`_MIN_CONSENSUS_SOURCES = 3` requires 3 agreeing sources. But in practice:
- FinBERT requires news_items (may be empty)
- LLM requires news_items AND events (subset of news)
- Social requires Reddit API credentials
- Event requires news_items

If only FinBERT + social are available, max agreeing sources = 2. Consensus is impossible, so signal is dampened by 50%.

### Critical Bottleneck 3: ML Unavailability Kills Technical Signal (SEVERITY: HIGH)

When `_ML_AVAILABLE = False`:
- Technical agent returns `direction=HOLD, confidence=0.0`
- Orchestrator fusion: if tech=HOLD with conf=0, and sentiment exists, fused direction leans heavily toward sentiment
- But with the broken geometric mean: `0^0.6 * sent_conf^0.4 * 100 = 0` -- fused confidence = 0
- Signal is immediately rejected by threshold gate

**This means**: Without ML libraries (torch, tensorflow, xgboost), the system CANNOT trade at all, even with valid sentiment signals. The technical signal's 0.0 confidence zeroes out the geometric mean.

### Bottleneck 4: Binance Geo-Block (SEVERITY: MEDIUM, MITIGATED)

The Hyperliquid fallback correctly mitigates Binance being blocked. Symbol mapping is clean. The only gap is non-USDT pairs, which are rare for the configured assets.

---

## 9. Realistic Confidence Projections

### Scenario A: Full Stack (All Services Available, ML Trained)

```
Technical:  85% (trained LSTM+Transformer+CNN ensemble, in kill zone)
Sentiment:  72% (FinBERT + LLM + Reddit + Events, with consensus)
On-chain:   65% (DeFiLlama + Etherscan)

Fusion (geometric mean, 0-100 scale):
  = (85^0.49) * (72^0.33) * (65^0.18) * 100
  = [CLAMPED TO 100]
  * 1.35 (agreement bonus) = 100% (clamped)

After meta-reasoning: ~90-95% (LLM may reduce)
After threshold: PASS (>78%)
Risk tier: A+ (>85%)
```

Realistic maximum: **95-100%** (but the 100% is an artifact of the broken formula)

### Scenario B: Current Realistic State (Binance Blocked, No ML, Reddit New)

```
Technical:  0% confidence (ML unavailable, returns HOLD)
Sentiment:  ~45% (FinBERT only if no news, or FinBERT+social with no consensus dampening)
On-chain:   ~50% (DeFiLlama works, Etherscan on free tier)

Fusion: tech=HOLD/0%, sentiment exists
  -> Single-signal path: sent_conf * 0.40 * 0.70 = 45 * 0.28 = 12.6%

After threshold: FAIL (12.6% < 78%)
```

**The system CANNOT produce an actionable trade signal in this state.**

### Scenario C: ML Available But Untrained, Good Sentiment Data

```
Technical:  ~60% (untrained models produce noisy predictions)
Sentiment:  ~65% (FinBERT + LLM, no Reddit, no consensus)
On-chain:   ~40%

Fusion: (60^0.6) * (65^0.4) * 100 = 12.3 * 8.15 * 100 = ~10,024 -> clamped to 100
  * 1.35 (if aligned) = 100%
  * 0.50 (if conflicting) = 50%

Aligned: 100% -> PASS
Conflicting: 50% -> FAIL
```

### Can the System Reach 85% (A+ Threshold)?

**With broken formula**: YES, trivially. Any two aligned signals with non-zero confidence produce 100% after clamping. The A+ threshold is meaningless.

**With corrected formula** (confidence / 100 before geometric mean):
```
Corrected: (0.85^0.6) * (0.72^0.4) * 100
         = 0.907 * 0.886 * 100
         = 80.3%
         * 1.35 = 108.4 -> 100% (clamped, still too high)

Better: (0.70^0.6) * (0.55^0.4) * 100
      = 0.793 * 0.769 * 100
      = 61.0%
      * 1.35 = 82.3% -- borderline A, not A+
```

With a corrected formula, reaching A+ requires both tech >= 80% and sentiment >= 70% with alignment. This is achievable but requires trained ML models and multi-source sentiment consensus.

---

## 10. Summary of Findings

| Finding | Severity | Location |
|---------|----------|----------|
| Geometric mean on 0-100 scale produces meaningless confidence | HIGH | `orchestrator.py:1351` |
| ML unavailable = zero-confidence tech signal kills all trades | HIGH | `signals.py:245-260` + fusion formula |
| Sentiment consensus requires 3 sources, often only 2 available | MEDIUM | `sentiment_signals.py:57` |
| Hyperliquid fallback working correctly | OK | `market_data_provider.py:377-392` |
| On-chain gracefully degrades when Etherscan is slow | OK | `onchain_aggregator.py:112-127` |
| Paper mode is default, safe for testing | OK | `orchestrator.py:205` |
| Single-signal penalty (0.7x) stacks with weight, too aggressive | LOW | `orchestrator.py:1281,1298` |

### Priority Fixes

1. **Fix the confidence fusion formula**: Normalize to 0-1 scale before geometric mean, multiply by 100 after. This is the single highest-impact bug in the entire signal pipeline.

2. **Handle ML-unavailable tech signals in fusion**: When tech returns HOLD/0%, treat it as "absent" rather than "zero confidence." Route to the single-signal path for sentiment instead of letting it zero out the geometric mean.

3. **Lower consensus threshold**: Reduce `_MIN_CONSENSUS_SOURCES` from 3 to 2, or make it relative to available sources (`>= ceil(available_sources * 0.5)`).
