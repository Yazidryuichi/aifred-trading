# Risk Management Audit Report

**Auditor:** Risk Management Auditor (Agent 04)
**Date:** 2026-04-01
**Scope:** All risk management systems in `python/src/risk/`
**Account Size:** $10.80 (micro capital)

---

## Executive Summary

The AIFred risk management system is **well-architected** with genuine defense-in-depth across 5+ layers. The Kelly Criterion formula is correct, fractional Kelly is properly applied, and the account safety module provides hard non-overridable limits as a last line of defense. The system is **safe for live trading with $10.80**, though several configuration inconsistencies and minor vulnerabilities should be addressed.

**Overall Grade: B+**

---

## 1. Five-Layer Defense-in-Depth

### Layer 1: `position_sizer.py` -- Grade: A-

**Correct:**
- Kelly formula: `f* = (p*b - q) / b` -- mathematically correct (line 28)
- Fractional Kelly (half-Kelly default 0.5) correctly applied (line 122)
- Division-by-zero guarded: returns 0.0 if `avg_loss <= 0` or `avg_win <= 0` (line 23)
- Negative Kelly handled: `max(f, 0.0)` prevents negative sizing (line 29)
- Tier-based multipliers correctly scale: A+ (1.0), A (0.75), B (0.5), C (0.25)
- Stop-distance-based risk budget cap with 10% maximum stop distance clamp
- Confidence normalization maps 0-100 to 0.2-1.0 multiplier range

**Win streak multiplier discrepancy (VULNERABILITY):**
- `default.yaml` lines 107-110 define `wins_3: 1.20`, `wins_5: 1.30` (aggressive boosts)
- `position_sizer.py` line 70 hardcodes `wins_3: 1.05` (conservative, capped)
- The hardcoded code OVERRIDES the config, which is actually the SAFER behavior
- However, this config-vs-code mismatch is confusing and should be reconciled

**Loss streak protection is solid:**
- 2+ losses: 0.60x (40% reduction)
- 4+ losses: 0.40x (60% reduction)
- 6+ losses: 0.20x (80% reduction, near halt)

### Layer 2: `stop_manager.py` -- Grade: A

**Correct:**
- ATR-based stops with regime adaptation: low (0.75x), normal (1.0x), high (1.25x), extreme (1.5x)
- Trailing stop never moves backwards (only tightens) -- verified for both LONG and SHORT
- Breakeven move at 1x ATR profit
- Partial take-profit at 1R (50% close, move stop to breakeven)
- Time-based stop at 36 hours for unprofitable positions (prevents capital lock-up)
- R-multiple take-profit at 2R and 3R
- BB-middle exit for mean reversion strategies
- Hard max loss check validates stop-loss risk per trade

**No issues found.** This is one of the strongest modules.

### Layer 3: `portfolio_monitor.py` -- Grade: B+

**Correct:**
- Tracks exposure by asset class and individual asset
- Enforces max concurrent positions (configurable)
- Enforces max asset class exposure (default 30%)
- Enforces max single asset exposure (default 20%)
- Portfolio value guard: rejects if total value <= 0

**Minor gap:**
- No real-time margin monitoring. For Hyperliquid leveraged positions, the module tracks notional value but does not check margin health or liquidation distance. With 2x leverage and a $10.80 account, liquidation distance should be monitored.

### Layer 4: `drawdown_manager.py` -- Grade: A

**Correct:**
- Daily drawdown limit (5% default, triggers 24h pause)
- Weekly drawdown limit (10% default, triggers 72h pause)
- Anti-revenge trading: 3+ consecutive losses within 2 hours triggers 4h cooldown
- Heat check: if last 5 trades are net negative, switches to A+ only mode
- Recovery mode: >5% drawdown activates 50% sizing for next 10 trades
- Deep recovery: >10% drawdown scales from 0.25x to 1.0x based on recovery progress
- Daily trade limit (8 trades in live config) prevents overtrading
- All drawdown events logged for analysis

**Well-designed behavioral safeguards.** The anti-revenge trading and heat check mechanisms are genuinely thoughtful.

### Layer 5: `risk_gate.py` -- Grade: A-

**Correct:**
- 14-step evaluation pipeline, ordered by impact
- Signal tier gating: B and C tiers always rejected
- After 3 consecutive losses: requires A+ with >85% confidence
- HIGH volatility regime: requires A+ signals only
- EXTREME volatility: no new trades allowed (close all or hedge)
- Correlation limit enforcement via CorrelationTracker
- Hard max loss verification before approval
- Stop-loss required (rejects if stop_loss <= 0)
- Kill zone time-of-day adjustments (never reject, only scale confidence)
- ADX momentum filter rejects counter-trend trades in strong trends
- Recovery mode sizing applied
- Complete decision logging with timestamps

**One concern with REGIME_CONFIDENCE_ADJUSTMENTS logic:**
- The adjustment is applied by *subtracting* the regime adjustment from the effective confidence before comparison (line 351: `adjusted_confidence_for_check = effective_confidence - regime_adj`). In HIGH vol, `regime_adj = +10`, so this effectively lowers the confidence by 10 for the scoring check. This is conceptually correct (raising the bar), but the naming (`adjusted_confidence_for_check`) could cause confusion, and this adjustment is ONLY used for the risk-scoring step (lines 354-358), NOT for the tier classification. The tier is classified from raw confidence before regime adjustment, which means the regime adjustment does not actually change tier gating. This is a design choice (tier gating uses raw confidence, regime raises the risk score) but could be made more explicit.

---

## 2. Dynamic Kelly (`dynamic_kelly.py`) -- Grade: A-

**Formula verification:**
- Line 133: `kelly_raw = max(0.0, (win_rate * b - (1 - win_rate)) / b)` -- CORRECT
- This is equivalent to `f* = (p*b - q) / b` where `q = 1 - p`
- Division by zero protected: `if b > 0 else 0.0`
- Negative Kelly clamped to 0.0 with `max(0.0, ...)`

**Fractional Kelly:**
- Default 50% fractional multiplier (line 54)
- Applied at line 134: `fractional = kelly_raw * self.fractional_multiplier`

**Calibration:**
- Rolling window: last 50 trades within 30 days
- Minimum 20 samples before calibration is trusted (`is_calibrated`)
- Falls back to default parameters when uncalibrated (win_rate=0.55, avg_win=2.0, avg_loss=1.0)
- Thread-safe with `threading.Lock`
- SQLite persistence for trade history

**Position size computation includes:**
- Tier multiplier (A+: 1.0, A: 0.75, B: 0.5, C: 0.0)
- Confidence scaling: `(confidence - 70) / 30` mapped to 0-1
- Volatility regime multiplier: low=1.05, normal=1.0, high=0.7, extreme=0.3
- Drawdown shrinkage: ramps from 1.0 to 0.2 between 3%-8% drawdown
- Clamped between min_position_pct (0.5%) and max_position_pct (5%)

**Minor concern:** Confidence scaling (`(confidence - 70) / 30`) means any confidence below 70 produces a 0.0 scale factor, making the position size exactly `min_position_pct`. This is aggressive but safe -- it means even A-tier signals at 75% get only a 0.167x confidence scale, resulting in very small positions. This may be TOO conservative for A-tier signals.

---

## 3. Volatility Regime (`volatility_regime.py`) -- Grade: A

**VIX-based detection:**
- VIX < 20: LOW
- VIX 20-30: NORMAL
- VIX 30-45: HIGH
- VIX >= 45: EXTREME

**ATR percentile detection:**
- Percentile < 30: LOW
- Percentile 30-80: NORMAL
- Percentile 80-95: HIGH
- Percentile >= 95: EXTREME

**Fear & Greed override:** Index <= 20 forces EXTREME regime (takes priority).

**Regime transition alerts:**
- `RegimeTransitionDetector` tracks all transitions
- Danger levels: LOW -> EXTREME = CRITICAL, LOW -> HIGH = HIGH
- Warnings logged for HIGH/CRITICAL transitions

**Regime adjustments correctly applied to:**
- Position size multiplier: 1.05 (low), 1.0 (normal), 0.5 (high), 0.0 (extreme)
- Stop multiplier: 0.75 (low), 1.0 (normal), 1.25 (high), 1.5 (extreme)
- Max positions: 12, 10, 5, 0
- A+ only requirement in HIGH and EXTREME

**No issues found.** Comprehensive and well-integrated.

---

## 4. Risk Gate Signal Tiers -- Grade: A-

**Tier thresholds (verified in `risk_gate.py` lines 24-29):**
- A+: >= 85 confidence
- A: >= 75 confidence
- B: >= 60 confidence (REJECTED by default)
- C: < 60 confidence (ALWAYS rejected)

**`live.yaml` `min_confidence_threshold: 85`:**
- This value is used in the orchestrator, NOT directly in the risk gate
- The risk gate independently rejects B and C tiers
- The orchestrator's threshold of 85 means only A+ signals pass the orchestrator
- Combined effect: live mode is A+ only at the orchestrator level, with the risk gate providing independent validation

**Regime confidence adjustments (verified):**
- Low vol: -5 (slightly easier to pass)
- Normal: 0
- High vol: +10 (harder to pass)
- Extreme: +20 (much harder)

**IMPORTANT NOTE:** These regime adjustments in the risk gate are applied to the risk scoring step, NOT to tier classification. The tier is always classified from raw confidence. This means:
- A signal at 85% confidence in HIGH vol is still classified as A+ (tier from raw confidence)
- But its risk score increases due to the regime penalty
- The risk gate already blocks non-A+ signals in HIGH vol via a separate check (line 260)

This is safe because the HIGH vol A+-only check is a hard gate, not dependent on the scoring adjustment.

---

## 5. Account Safety (`account_safety.py`) -- Grade: A

**This is the final, non-overridable gate. Grade reflects its critical importance.**

**Hard limits (cannot be loosened by config):**
- Daily loss: max 2% (HARD_DAILY_LOSS_PCT)
- Weekly loss: max 5% (HARD_WEEKLY_LOSS_PCT)
- Max position: 5% of account (HARD_MAX_POSITION_PCT)
- Max total exposure: 30% of account (HARD_MAX_EXPOSURE_PCT)
- Max concurrent positions: 5 (HARD_MAX_POSITIONS)

**Config can only tighten (verified lines 65-84):** Uses `min()` to compare config vs hard constants.

**Live config tightens further:**
- `safety.max_positions: 2` (tightened from 5)
- All other limits match hard defaults

**Kill switch:**
- `activate_kill_switch(reason)` blocks all trades immediately
- Thread-safe with `threading.Lock`
- Telegram alert on activation
- Must be manually deactivated
- Persists until explicit deactivation

**Daily/weekly counter resets:**
- Daily reset at midnight UTC
- Weekly reset on Monday or after 7 days

**For $10.80 account:**
- Daily loss limit: $0.216 (2% of $10.80)
- Weekly loss limit: $0.54 (5% of $10.80)
- Max position: $0.54 (5% of $10.80)
- Max exposure: $3.24 (30% of $10.80)
- These are very tight limits, appropriate for micro capital

---

## 6. Live Trading Safeguards -- Grade: A-

**Kill switch implementation (verified in `orchestrator.py`):**
- `kill_switch(reason)` method activates AccountSafety kill switch
- Stops the scan loop
- Closes ALL open positions with reason `kill_switch:{reason}`
- File-based kill switch support: creates/detects a kill file for external triggers
- Telegram notification on activation

**Emergency position close (verified in `orchestrator.py`):**
- Kill switch iterates all positions and calls `close_position()` on each
- Results tracked per position with success/failure logging

**Balance checks before order (verified in `execution_engine.py`):**
- `check_trade_allowed()` is called BEFORE every trade execution (line 144)
- Checks: kill switch, daily loss, weekly loss, position size, exposure, max positions
- If ANY check fails, trade is BLOCKED

**Integration is solid.** The execution engine imports AccountSafety and calls `check_trade_allowed()` as the FIRST check before any order.

---

## Vulnerabilities Found

### V1: Config vs Code Streak Multiplier Mismatch (LOW risk)
- **Location:** `default.yaml` lines 107-110 vs `position_sizer.py` line 70
- **Issue:** Config says `wins_3: 1.20` but code hardcodes `1.05`. Code wins (safer), but the config is misleading.
- **Impact:** LOW -- the code is safer than the config suggests. Anyone reading the config would believe win streaks boost sizing by 20-30%, when in reality the boost is capped at 5%.
- **Fix:** Update `default.yaml` to match the actual code behavior.

### V2: Risk Config Key Mismatch (LOW risk)
- **Location:** `default.yaml` uses `atr_stop_multiplier` (line 83) but `stop_manager.py` reads `stop_loss_atr_multiplier` (line 40)
- **Issue:** The stop manager falls back to default (2.0) because the key name doesn't match.
- **Impact:** LOW -- the default of 2.0 is the same as the intended config value of 2.0, so no actual behavioral difference. But if someone changes the config expecting it to take effect, it won't.
- **Fix:** Align the key name in either the config or the code.

### V3: No Margin/Liquidation Monitoring (MEDIUM risk)
- **Location:** `portfolio_monitor.py`, `account_safety.py`
- **Issue:** With Hyperliquid 2x leverage enabled in `live.yaml`, there is no explicit liquidation distance monitoring. The position sizing limits prevent overleveraging, but there is no runtime check that a position is approaching its liquidation price.
- **Impact:** MEDIUM -- at 2x leverage with tiny positions on a $10.80 account, the risk of liquidation is mitigated by the 5% max position limit ($0.54 max). But as the account grows, this gap becomes more relevant.
- **Fix:** Add liquidation distance check in the position monitoring loop.

### V4: `live.yaml` `risk.max_position_pct: 10.0` Conflicts with Safety (LOW risk)
- **Location:** `live.yaml` line 21 sets `risk.max_position_pct: 10.0`
- **Issue:** This is used by `position_sizer.py` as `max_position_pct`, allowing up to 10% of portfolio per position in the sizing calculation. However, `account_safety.py` hard-caps at 5%. The safety layer wins, but the risk config is set higher than the safety hard cap.
- **Impact:** LOW -- the safety layer correctly blocks oversized positions. But the config is misleading.
- **Fix:** Set `risk.max_position_pct` to 5.0 or lower to match the safety hard cap.

### V5: Dynamic Kelly Confidence Scaling Aggressiveness (LOW risk)
- **Location:** `dynamic_kelly.py` line 153
- **Issue:** Confidence scaling `(signal_confidence - 70) / 30` means A-tier signals at 75% get only 0.167x scaling, resulting in near-minimum positions. This is very conservative but may cause the system to under-trade even quality setups.
- **Impact:** LOW -- this is a profitability concern, not a safety concern. The system is overly cautious rather than overly aggressive.

---

## Component Grade Summary

| Component | Grade | Notes |
|-----------|-------|-------|
| `position_sizer.py` | A- | Kelly correct, config mismatch on streaks |
| `stop_manager.py` | A | ATR-based, trailing, partial exits, time stops |
| `portfolio_monitor.py` | B+ | Solid exposure tracking, no margin monitoring |
| `drawdown_manager.py` | A | Anti-revenge, heat check, recovery mode |
| `risk_gate.py` | A- | 14-step pipeline, comprehensive gating |
| `dynamic_kelly.py` | A- | Correct formula, calibration from history |
| `volatility_regime.py` | A | VIX + ATR + F&G, transition alerts |
| `account_safety.py` | A | Hard limits, kill switch, non-overridable |
| `correlation_tracker.py` | A- | Pairwise correlation, regime change detection |
| `risk_metrics.py` | A | Sharpe, Sortino, VaR, rolling windows |
| Live integration | A- | Kill switch, balance checks before orders |

---

## Verdict: Safe for Live Trading with $10.80?

**YES -- with caveats.**

The system has genuine defense-in-depth with multiple independent safety layers. Even if the risk gate fails, the account safety module provides hard, non-overridable limits that prevent catastrophic loss. The kill switch is properly implemented and integrated.

For a $10.80 account:
- Maximum daily loss: $0.216 (2%)
- Maximum single position: $0.54 (5% hard cap)
- Maximum exposure: $3.24 (30%)
- Effective position sizes will be much smaller due to Kelly + fractional Kelly + tier scaling + confidence normalization
- With only A+ signals allowed (live mode), very few trades will pass

**The primary risk is not the risk management system -- it is exchange fees and slippage on micro-sized positions, which may erode the account regardless of trade quality.**

**Recommended fixes before scaling capital:**
1. Reconcile the streak multiplier config vs code mismatch (V1)
2. Fix the ATR stop multiplier key name (V2)
3. Add liquidation distance monitoring for leveraged positions (V3)
4. Align `risk.max_position_pct` with the safety hard cap (V4)
