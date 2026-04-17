"""Whale activity detector using Hyperliquid OI and volume analysis.

When OI increases sharply but price moves little = accumulation (whale building position)
When OI decreases sharply but price moves little = distribution (whale exiting)
When OI increases AND price moves sharply = momentum (whale + retail aligned)
"""

import logging
import time
from typing import Dict, Optional
from collections import deque

logger = logging.getLogger(__name__)


class WhaleSignal:
    """Detected whale activity signal."""
    def __init__(self, signal_type: str, strength: float, direction: str, details: str):
        self.signal_type = signal_type  # "accumulation", "distribution", "momentum"
        self.strength = strength  # 0.0-1.0
        self.direction = direction  # "bullish", "bearish", "neutral"
        self.details = details


class WhaleDetector:
    """Detect whale activity from OI vs price divergence patterns."""

    def __init__(self, hl_market_data=None):
        self._hl_data = hl_market_data
        self._price_history: Dict[str, deque] = {}  # symbol -> deque of (timestamp, price)
        self._cache: Dict[str, WhaleSignal] = {}
        self._cache_time: Dict[str, float] = {}
        self.CACHE_TTL = 120  # 2 min

    def record_price(self, symbol: str, price: float) -> None:
        """Record a price data point for a symbol."""
        if symbol not in self._price_history:
            self._price_history[symbol] = deque(maxlen=100)
        self._price_history[symbol].append({"price": price, "time": time.time()})

    def detect(self, symbol: str) -> Optional[WhaleSignal]:
        """Detect whale activity for a symbol.

        Logic:
        - Get OI change from hl_market_data (already computed)
        - Get price change over same period
        - Compare: if OI change >> price change = whale accumulation/distribution
        """
        now = time.time()
        cached = self._cache.get(symbol)
        if cached and (now - self._cache_time.get(symbol, 0)) < self.CACHE_TTL:
            return cached

        if not self._hl_data:
            return None

        try:
            oi_delta = self._hl_data.get_oi_delta(symbol)
            if not oi_delta or "4h" not in oi_delta or oi_delta["4h"] is None:
                return None

            oi_4h_change = abs(oi_delta["4h"])

            # Get price change over 4h
            prices = self._price_history.get(symbol, deque())
            if len(prices) < 2:
                return None

            current_price = prices[-1]["price"]
            four_hours_ago = now - 4 * 3600
            old_prices = [p for p in prices if p["time"] <= four_hours_ago + 600]
            if not old_prices:
                old_price = prices[0]["price"]
            else:
                old_price = old_prices[-1]["price"]

            if old_price <= 0:
                return None

            price_4h_change = abs((current_price - old_price) / old_price * 100)

            # Detect patterns
            signal = None
            oi_direction = oi_delta["4h"]  # signed
            price_direction = (current_price - old_price) / old_price * 100  # signed

            if oi_4h_change > 3.0 and price_4h_change < 1.0:
                # OI moving but price isn't = whale accumulation/distribution
                if oi_direction > 0:
                    signal = WhaleSignal("accumulation", min(oi_4h_change / 10, 1.0), "bullish",
                        f"OI +{oi_direction:.1f}% but price only {price_direction:+.1f}% — silent accumulation")
                else:
                    signal = WhaleSignal("distribution", min(oi_4h_change / 10, 1.0), "bearish",
                        f"OI {oi_direction:.1f}% but price only {price_direction:+.1f}% — silent distribution")

            elif oi_4h_change > 5.0 and price_4h_change > 2.0:
                # Both OI and price moving = momentum (whale + retail)
                direction = "bullish" if price_direction > 0 else "bearish"
                signal = WhaleSignal("momentum", min(oi_4h_change / 10, 1.0), direction,
                    f"OI {oi_direction:+.1f}% AND price {price_direction:+.1f}% — whale-driven momentum")

            if signal:
                self._cache[symbol] = signal
                self._cache_time[symbol] = now
                logger.info("Whale signal [%s]: %s (%s, strength=%.2f) — %s",
                    symbol, signal.signal_type, signal.direction, signal.strength, signal.details)

            return signal

        except Exception as e:
            logger.debug("Whale detection failed for %s: %s", symbol, e)
            return None

    def get_summary(self, symbol: str) -> str:
        """Get a human-readable whale summary for Telegram/logging."""
        signal = self.detect(symbol)
        if not signal:
            return "no whale activity"
        return f"{signal.signal_type} ({signal.direction}, strength={signal.strength:.0%})"
