"""Macro signal layer — gates trading based on broad market conditions.

Inspired by AI-Trader (HKUDS) benchmark findings: macro awareness was
the strongest differentiator between winning and losing AI models.
"""

import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Breadth thresholds: what fraction of tracked assets need to be up/down
# for the market to be considered bullish-/bearish-biased.
_BREADTH_LONG_THRESHOLD = 0.60
_BREADTH_SHORT_THRESHOLD = 0.40
_BREADTH_MIN_SAMPLE = 5  # require this many assets with usable history


class MacroVerdict(Enum):
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    DEFENSIVE = "defensive"


class MacroSignal:
    """Evaluates broad market conditions from BTC momentum, funding rates, and OI trends.

    Cache: 5 min TTL (macro changes slowly).
    """

    CACHE_TTL = 300  # 5 minutes

    def __init__(self, hl_market_data=None):
        """
        Args:
            hl_market_data: HyperliquidMarketData instance for funding/OI data.
        """
        self._hl_data = hl_market_data
        self._btc_prices: list = []  # store recent BTC prices for momentum calc
        self._cache: Optional[MacroVerdict] = None
        self._cache_time: float = 0
        # Per-asset price history for cross-sectional breadth ("% of scanned
        # assets trending up"). Fed from the orchestrator's existing price
        # loop — no extra exchange calls.
        self._asset_prices: Dict[str, List[Dict[str, float]]] = {}

    def record_btc_price(self, price: float) -> None:
        """Record a BTC price data point. Called each scan cycle."""
        self._btc_prices.append({"price": price, "time": time.time()})
        # Keep last 168 entries (~7 days at 1h intervals, or ~168 min at 1 min)
        if len(self._btc_prices) > 200:
            self._btc_prices = self._btc_prices[-168:]

    def record_asset_price(self, asset: str, price: float) -> None:
        """Record a price point for any scanned asset. Used for cross-sectional
        breadth (what fraction of the traded basket is trending up).

        Buffer is capped at ~48h of data; older samples are pruned.
        """
        if price is None or price <= 0:
            return
        now = time.time()
        hist = self._asset_prices.setdefault(asset, [])
        hist.append({"price": float(price), "time": now})
        # Prune: keep samples within 48h, cap total to 200 per asset.
        cutoff = now - 48 * 3600
        if len(hist) > 200 or (hist and hist[0]["time"] < cutoff):
            self._asset_prices[asset] = [p for p in hist if p["time"] >= cutoff][-200:]

    def _return_over(self, asset: str, window_seconds: float) -> Optional[float]:
        """Return the price change (current vs oldest price within window) for one asset,
        as a fraction (0.05 == +5%). None if not enough history."""
        hist = self._asset_prices.get(asset, [])
        if len(hist) < 2:
            return None
        now = time.time()
        target = now - window_seconds
        # Find the oldest entry at or before the target time
        older = [p for p in hist if p["time"] <= target + 300]  # 5-min tolerance
        base = older[-1]["price"] if older else hist[0]["price"]
        current = hist[-1]["price"]
        if base <= 0:
            return None
        return (current - base) / base

    def compute_breadth(self) -> Dict[str, Any]:
        """Compute market breadth across all tracked assets.

        Returns a dict with:
          - up_1h_pct / up_24h_pct: fraction of assets with positive return over window
          - sample_1h / sample_24h: how many assets had enough history to count
          - bias: "long" (> long_threshold up), "short" (< short_threshold up), or "neutral"
        """
        up_1h = n_1h = 0
        up_24h = n_24h = 0
        for asset in self._asset_prices:
            r1 = self._return_over(asset, 3600.0)
            if r1 is not None:
                n_1h += 1
                if r1 > 0:
                    up_1h += 1
            r24 = self._return_over(asset, 86400.0)
            if r24 is not None:
                n_24h += 1
                if r24 > 0:
                    up_24h += 1

        pct_1h = (up_1h / n_1h) if n_1h > 0 else None
        pct_24h = (up_24h / n_24h) if n_24h > 0 else None

        # Use 1h for primary bias (reacts faster); fall back to 24h if not enough
        # 1h samples yet (early in a restart). Below min-sample threshold = neutral.
        primary = pct_1h if (pct_1h is not None and n_1h >= _BREADTH_MIN_SAMPLE) else pct_24h
        primary_n = n_1h if (pct_1h is not None and n_1h >= _BREADTH_MIN_SAMPLE) else n_24h

        if primary is None or (primary_n or 0) < _BREADTH_MIN_SAMPLE:
            bias = "neutral"
        elif primary >= _BREADTH_LONG_THRESHOLD:
            bias = "long"
        elif primary <= _BREADTH_SHORT_THRESHOLD:
            bias = "short"
        else:
            bias = "neutral"

        return {
            "up_1h_pct": round(pct_1h, 3) if pct_1h is not None else None,
            "up_24h_pct": round(pct_24h, 3) if pct_24h is not None else None,
            "sample_1h": n_1h,
            "sample_24h": n_24h,
            "bias": bias,
        }

    def _btc_7d_return(self) -> Optional[float]:
        """Calculate BTC 7-day return percentage."""
        if len(self._btc_prices) < 2:
            return None
        now = time.time()
        seven_days_ago = now - 7 * 24 * 3600
        # Find oldest price within 7 days
        old_prices = [p for p in self._btc_prices if p["time"] <= seven_days_ago + 3600]
        if not old_prices:
            # Not enough history, use oldest available
            old_price = self._btc_prices[0]["price"]
        else:
            old_price = old_prices[-1]["price"]
        current_price = self._btc_prices[-1]["price"]
        if old_price <= 0:
            return None
        return ((current_price - old_price) / old_price) * 100

    def check_fast_risk_off(self) -> bool:
        """Return True if BTC dropped >3% in the last 24 hours.

        Uses the stored _btc_prices list. Requires at least 2 data points
        with the oldest being within ~24h window.
        """
        if len(self._btc_prices) < 2:
            return False

        now = time.time()
        twenty_four_hours_ago = now - 24 * 3600

        # Find the oldest price within the 24h window
        old_prices = [p for p in self._btc_prices if p["time"] <= twenty_four_hours_ago + 3600]
        if not old_prices:
            # Use oldest available if all data is within 24h
            old_price = self._btc_prices[0]["price"]
        else:
            old_price = old_prices[-1]["price"]

        current_price = self._btc_prices[-1]["price"]
        if old_price <= 0:
            return False

        change_pct = ((current_price - old_price) / old_price) * 100
        if change_pct < -3.0:
            logger.warning(
                "Fast risk-off triggered: BTC dropped %.2f%% in 24h (%.2f -> %.2f)",
                change_pct, old_price, current_price,
            )
            return True
        return False

    def evaluate(self) -> MacroVerdict:
        """Evaluate macro conditions. Returns cached result if within TTL."""
        now = time.time()
        if self._cache is not None and (now - self._cache_time) < self.CACHE_TTL:
            return self._cache

        verdict = self._compute_verdict()
        self._cache = verdict
        self._cache_time = now
        logger.info("Macro verdict: %s", verdict.value)
        return verdict

    def _compute_verdict(self) -> MacroVerdict:
        """Core logic: combine BTC momentum + avg funding + OI trend."""
        signals = {"bullish": 0, "bearish": 0}
        reasons = []

        # 1. BTC 7-day momentum
        btc_return = self._btc_7d_return()
        if btc_return is not None:
            if btc_return < -5.0:
                signals["bearish"] += 2  # strong weight for BTC trend
                reasons.append(f"BTC 7d return {btc_return:.1f}% (bearish)")
            elif btc_return > 5.0:
                signals["bullish"] += 2
                reasons.append(f"BTC 7d return {btc_return:.1f}% (bullish)")
            else:
                reasons.append(f"BTC 7d return {btc_return:.1f}% (neutral)")

        # 2. Aggregate funding rate
        if self._hl_data:
            try:
                # Get funding for major assets
                major_symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
                data = self._hl_data.fetch_funding_and_oi(major_symbols)
                if data:
                    funding_rates = [v.get("funding_rate", 0) for v in data.values() if v]
                    if funding_rates:
                        avg_funding = sum(funding_rates) / len(funding_rates)
                        if avg_funding < -0.01:
                            signals["bearish"] += 1
                            reasons.append(f"Avg funding {avg_funding*100:.4f}% (negative)")
                        elif avg_funding > 0.02:
                            signals["bearish"] += 1  # extreme positive = overleveraged
                            reasons.append(f"Avg funding {avg_funding*100:.4f}% (overleveraged)")
                        elif avg_funding > 0:
                            signals["bullish"] += 1
                            reasons.append(f"Avg funding {avg_funding*100:.4f}% (healthy)")

                    # 3. Aggregate OI trend
                    oi_changes = []
                    for sym in major_symbols:
                        delta = self._hl_data.get_oi_delta(sym)
                        if delta and "4h" in delta and delta["4h"] is not None:
                            oi_changes.append(delta["4h"])

                    if oi_changes:
                        avg_oi_change = sum(oi_changes) / len(oi_changes)
                        if avg_oi_change < -10.0:
                            signals["bearish"] += 2  # rapid deleveraging
                            reasons.append(f"Avg OI 4h change {avg_oi_change:.1f}% (deleveraging)")
                        elif avg_oi_change < -5.0:
                            signals["bearish"] += 1
                            reasons.append(f"Avg OI 4h change {avg_oi_change:.1f}% (declining)")
                        elif avg_oi_change > 5.0:
                            signals["bullish"] += 1
                            reasons.append(f"Avg OI 4h change {avg_oi_change:.1f}% (expanding)")
            except Exception as e:
                logger.debug("Macro: failed to get funding/OI data: %s", e)

        # 4. Cross-sectional asset breadth (what fraction of the traded basket
        # is trending up). Adds one vote per direction when breadth is decisive.
        breadth = self.compute_breadth()
        if breadth["sample_1h"] >= _BREADTH_MIN_SAMPLE:
            if breadth["bias"] == "long":
                signals["bullish"] += 1
                reasons.append(
                    f"Breadth {int((breadth['up_1h_pct'] or 0)*100)}% up on 1h (bullish)"
                )
            elif breadth["bias"] == "short":
                signals["bearish"] += 1
                reasons.append(
                    f"Breadth {int((breadth['up_1h_pct'] or 0)*100)}% up on 1h (bearish)"
                )

        # Compute verdict
        bull_score = signals["bullish"]
        bear_score = signals["bearish"]

        if bear_score >= 3:
            verdict = MacroVerdict.DEFENSIVE
        elif bear_score >= 2 and bull_score == 0:
            verdict = MacroVerdict.DEFENSIVE
        elif bull_score >= 3:
            verdict = MacroVerdict.BULLISH
        elif bull_score >= 2 and bear_score == 0:
            verdict = MacroVerdict.BULLISH
        else:
            verdict = MacroVerdict.NEUTRAL

        logger.info("Macro analysis: bull=%d bear=%d → %s (%s)",
                     bull_score, bear_score, verdict.value, "; ".join(reasons) if reasons else "no data")

        return verdict

    def get_summary(self) -> Dict:
        """Get macro state summary for Telegram alerts and logging."""
        verdict = self.evaluate()
        btc_return = self._btc_7d_return()
        breadth = self.compute_breadth()
        return {
            "verdict": verdict.value,
            "btc_7d_return": round(btc_return, 2) if btc_return is not None else None,
            "breadth_bias": breadth["bias"],
            "breadth_up_1h_pct": breadth["up_1h_pct"],
            "breadth_sample_1h": breadth["sample_1h"],
        }
