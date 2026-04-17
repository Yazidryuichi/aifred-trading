"""Hyperliquid market data client -- Open Interest and Funding Rate.

Fetches OI and funding rate data from Hyperliquid's public info API.
Used by OnChainAggregator to add leverage/derivatives signals to the
on-chain signal pipeline.

Features:
- Sync (requests-based) for easy integration with sync callers
- 60s cache TTL on fetch results
- OI snapshot history (deque, maxlen=24) for delta computation
- Graceful error handling -- returns empty dict on failure
"""

import logging
import time
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_API_URL = "https://api.hyperliquid.xyz/info"
_CACHE_TTL = 60  # seconds
_REQUEST_TIMEOUT = 15  # seconds


class HyperliquidMarketData:
    """Fetches OI and funding rate data from Hyperliquid's public API.

    Usage::

        client = HyperliquidMarketData()
        data = client.fetch_funding_and_oi(["BTC/USDT", "ETH/USDT"])
        # -> {"BTC": {"funding_rate": 0.0001, "open_interest": 123456.0, "mark_price": 67000.0}, ...}

        client.record_snapshot()  # call each cycle
        delta = client.get_oi_delta("BTC")
        # -> {"1h": 2.5, "4h": 5.1, "24h": -1.2}
    """

    def __init__(self, request_timeout: int = _REQUEST_TIMEOUT):
        self._timeout = request_timeout

        # Cache
        self._cache: Optional[Dict[str, Dict[str, float]]] = None
        self._cache_time: float = 0.0

        # OI snapshot history: list of (timestamp, {symbol: oi_value})
        self._oi_snapshots: deque = deque(maxlen=24)

    # ------------------------------------------------------------------
    # Symbol mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """Map 'BTC/USDT' -> 'BTC' for Hyperliquid API."""
        return symbol.split("/")[0].upper()

    # ------------------------------------------------------------------
    # Core fetch
    # ------------------------------------------------------------------

    def fetch_funding_and_oi(
        self, symbols: List[str]
    ) -> Dict[str, Dict[str, float]]:
        """Fetch funding rate and OI for the given symbols.

        Args:
            symbols: List of symbols like ["BTC/USDT", "ETH/USDT"].

        Returns:
            Dict keyed by bare symbol (e.g. "BTC") with::

                {
                    "funding_rate": float,   # per-8h rate
                    "open_interest": float,   # in USD
                    "mark_price": float,
                }

            Returns empty dict on failure.
        """
        # Check cache
        now = time.monotonic()
        if self._cache is not None and (now - self._cache_time) < _CACHE_TTL:
            target_syms = {self._normalize_symbol(s) for s in symbols}
            # Return cached subset if all requested symbols are present
            if target_syms.issubset(self._cache.keys()):
                logger.debug("HyperliquidMarketData: cache hit")
                return {k: v for k, v in self._cache.items() if k in target_syms}

        # Fetch from API
        try:
            resp = requests.post(
                _API_URL,
                json={"type": "metaAndAssetCtxs"},
                headers={"Content-Type": "application/json"},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            logger.warning("HyperliquidMarketData: fetch failed: %s", exc)
            return {}
        except (ValueError, TypeError) as exc:
            logger.warning("HyperliquidMarketData: JSON parse failed: %s", exc)
            return {}

        # Parse response -- format is [meta_info, [asset_ctx, ...]]
        if not isinstance(data, list) or len(data) < 2:
            logger.warning(
                "HyperliquidMarketData: unexpected response structure"
            )
            return {}

        meta_info = data[0]
        asset_ctxs = data[1]

        # Build symbol -> index mapping from meta universe
        universe = meta_info.get("universe", [])
        if not universe or not asset_ctxs:
            logger.warning("HyperliquidMarketData: empty universe or asset contexts")
            return {}

        result: Dict[str, Dict[str, float]] = {}
        target_syms = {self._normalize_symbol(s) for s in symbols}

        for i, asset_info in enumerate(universe):
            sym = asset_info.get("name", "")
            if not sym:
                continue

            if i >= len(asset_ctxs):
                break

            ctx = asset_ctxs[i]

            try:
                funding_rate = float(ctx.get("funding", 0))
                open_interest = float(ctx.get("openInterest", 0))
                mark_price = float(ctx.get("markPx", 0))
            except (ValueError, TypeError):
                continue

            # Store all symbols in cache, filter for return
            result[sym] = {
                "funding_rate": funding_rate,
                "open_interest": open_interest * mark_price,  # convert to USD
                "mark_price": mark_price,
            }

        # Update cache with full result set
        self._cache = result
        self._cache_time = now

        logger.info(
            "HyperliquidMarketData: fetched %d assets from Hyperliquid",
            len(result),
        )

        # Filter to requested symbols
        return {k: v for k, v in result.items() if k in target_syms}

    # ------------------------------------------------------------------
    # OI snapshot management
    # ------------------------------------------------------------------

    def record_snapshot(self) -> None:
        """Record current OI values as a snapshot for delta computation.

        Should be called once per trading cycle (e.g. every hour).
        """
        if self._cache is None:
            logger.debug("HyperliquidMarketData: no cached data for snapshot")
            return

        oi_values = {
            sym: data["open_interest"]
            for sym, data in self._cache.items()
        }

        self._oi_snapshots.append({
            "timestamp": datetime.utcnow(),
            "oi": oi_values,
        })

        logger.debug(
            "HyperliquidMarketData: recorded OI snapshot (%d symbols, %d snapshots stored)",
            len(oi_values),
            len(self._oi_snapshots),
        )

    def get_oi_delta(self, symbol: str) -> Dict[str, float]:
        """Compute OI percentage change over 1h, 4h, and 24h windows.

        Args:
            symbol: Symbol like "BTC/USDT" or "BTC".

        Returns:
            {"1h": pct_change, "4h": pct_change, "24h": pct_change}
            Values are percentage changes (e.g. 5.0 means +5%).
            Returns empty dict if insufficient data.
        """
        sym = self._normalize_symbol(symbol)

        if not self._oi_snapshots:
            return {}

        # Get current OI
        if self._cache is None or sym not in self._cache:
            return {}

        current_oi = self._cache[sym]["open_interest"]
        if current_oi <= 0:
            return {}

        now = datetime.utcnow()
        result: Dict[str, float] = {}

        # Look back through snapshots for each time window
        windows = {"1h": 1, "4h": 4, "24h": 24}

        for label, hours_back in windows.items():
            target_time = now.timestamp() - (hours_back * 3600)
            best_snapshot = None
            best_diff = float("inf")

            for snapshot in self._oi_snapshots:
                snap_ts = snapshot["timestamp"].timestamp()
                diff = abs(snap_ts - target_time)
                if diff < best_diff and sym in snapshot["oi"]:
                    best_diff = diff
                    best_snapshot = snapshot

            if best_snapshot is not None and sym in best_snapshot["oi"]:
                old_oi = best_snapshot["oi"][sym]
                if old_oi > 0:
                    pct_change = ((current_oi - old_oi) / old_oi) * 100.0
                    result[label] = round(pct_change, 2)

        return result
