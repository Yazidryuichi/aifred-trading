"""DeFiLlama API client for on-chain DeFi metrics.

Free, no API key required.  Provides:
- TVL by protocol and chain
- Stablecoin market-cap / flow data
- DEX aggregate volumes
- Yield / APY pool data

All HTTP calls are async (aiohttp) with:
- Per-endpoint rate limiting (conservative 30 req/min)
- Response caching with configurable TTL
- Timeouts and structured error handling
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Base URLs (all public, no auth)
# ---------------------------------------------------------------------------
_BASE_URL = "https://api.llama.fi"
_STABLECOINS_URL = "https://stablecoins.llama.fi"
_YIELDS_URL = "https://yields.llama.fi"

# ---------------------------------------------------------------------------
# Cache TTLs (seconds)
# ---------------------------------------------------------------------------
_TTL_TVL = 3600          # 1 hour  -- TVL changes slowly
_TTL_CHAINS = 3600       # 1 hour
_TTL_STABLECOINS = 3600  # 1 hour
_TTL_DEX_VOLUMES = 300   # 5 min   -- volumes shift faster
_TTL_YIELDS = 300        # 5 min

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
_MIN_REQUEST_INTERVAL = 2.0  # seconds between requests (30 req/min)
_REQUEST_TIMEOUT = 15        # seconds


@dataclass
class CacheEntry:
    """Simple TTL cache entry."""
    data: Any
    fetched_at: float
    ttl: float

    @property
    def is_expired(self) -> bool:
        return (time.monotonic() - self.fetched_at) >= self.ttl


@dataclass
class TVLSnapshot:
    """TVL data for a protocol or chain at a point in time."""
    name: str
    tvl: float
    change_1d: Optional[float] = None
    change_7d: Optional[float] = None
    category: str = ""
    chains: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class StablecoinFlow:
    """Stablecoin market data snapshot."""
    name: str
    symbol: str
    peg_type: str  # e.g. "peggedUSD"
    circulating: float
    change_1d: Optional[float] = None
    change_7d: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DEXVolumeSnapshot:
    """Aggregate DEX volume data."""
    total_24h: float
    change_1d: Optional[float] = None
    protocols: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class YieldPool:
    """Yield / APY data for a single pool."""
    pool_id: str
    project: str
    chain: str
    symbol: str
    tvl_usd: float
    apy: float
    apy_base: Optional[float] = None
    apy_reward: Optional[float] = None
    il_risk: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


class DeFiLlamaClient:
    """Async client for the DeFiLlama public API.

    Features:
    - Lazy session creation (created on first request)
    - Response caching with per-endpoint TTL
    - Rate limiting to stay well under free-tier limits
    - Timeout and retry on transient errors
    """

    def __init__(
        self,
        request_timeout: int = _REQUEST_TIMEOUT,
        min_request_interval: float = _MIN_REQUEST_INTERVAL,
    ):
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        self._min_interval = min_request_interval
        self._last_request_time = 0.0
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, CacheEntry] = {}

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazily create and return the shared aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                },
            )
        return self._session

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Rate limiting & caching helpers
    # ------------------------------------------------------------------

    async def _rate_limit(self) -> None:
        """Async rate limiter -- sleep if requests are too fast."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.monotonic()

    def _get_cached(self, key: str) -> Optional[Any]:
        """Return cached data if still valid, else None."""
        entry = self._cache.get(key)
        if entry and not entry.is_expired:
            logger.debug("Cache hit for %s", key)
            return entry.data
        return None

    def _set_cached(self, key: str, data: Any, ttl: float) -> None:
        self._cache[key] = CacheEntry(data=data, fetched_at=time.monotonic(), ttl=ttl)

    # ------------------------------------------------------------------
    # Low-level GET with error handling
    # ------------------------------------------------------------------

    async def _get(self, url: str) -> Optional[Any]:
        """Perform a rate-limited GET request with error handling.

        Returns parsed JSON on success, None on failure.
        """
        await self._rate_limit()
        session = await self._get_session()

        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 429:
                    logger.warning("DeFiLlama rate limited (429), backing off")
                    await asyncio.sleep(10.0)
                    return None
                else:
                    body = await resp.text()
                    logger.warning(
                        "DeFiLlama %s returned %d: %s",
                        url, resp.status, body[:200],
                    )
                    return None
        except asyncio.TimeoutError:
            logger.warning("DeFiLlama request timed out: %s", url)
            return None
        except aiohttp.ClientError as exc:
            logger.warning("DeFiLlama request failed: %s -- %s", url, exc)
            return None

    # ------------------------------------------------------------------
    # TVL endpoints
    # ------------------------------------------------------------------

    async def get_protocols(self) -> List[TVLSnapshot]:
        """Fetch TVL data for all tracked protocols.

        GET https://api.llama.fi/v2/protocols
        """
        cache_key = "protocols"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        raw = await self._get(f"{_BASE_URL}/v2/protocols")
        if raw is None:
            return []

        results: List[TVLSnapshot] = []
        for item in raw:
            try:
                results.append(TVLSnapshot(
                    name=item.get("name", ""),
                    tvl=float(item.get("tvl", 0)),
                    change_1d=item.get("change_1d"),
                    change_7d=item.get("change_7d"),
                    category=item.get("category", ""),
                    chains=item.get("chains", []),
                ))
            except (ValueError, TypeError):
                continue

        self._set_cached(cache_key, results, _TTL_TVL)
        logger.info("Fetched %d protocols from DeFiLlama", len(results))
        return results

    async def get_chains(self) -> List[TVLSnapshot]:
        """Fetch TVL data aggregated by chain.

        GET https://api.llama.fi/v2/chains
        """
        cache_key = "chains"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        raw = await self._get(f"{_BASE_URL}/v2/chains")
        if raw is None:
            return []

        results: List[TVLSnapshot] = []
        for item in raw:
            try:
                results.append(TVLSnapshot(
                    name=item.get("name", ""),
                    tvl=float(item.get("tvl", 0)),
                    category="chain",
                ))
            except (ValueError, TypeError):
                continue

        self._set_cached(cache_key, results, _TTL_CHAINS)
        logger.info("Fetched %d chains from DeFiLlama", len(results))
        return results

    async def get_protocol_tvl(self, protocol_slug: str) -> Optional[Dict[str, Any]]:
        """Fetch historical TVL for a specific protocol.

        GET https://api.llama.fi/protocol/{slug}
        """
        cache_key = f"protocol:{protocol_slug}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        raw = await self._get(f"{_BASE_URL}/protocol/{protocol_slug}")
        if raw is None:
            return None

        self._set_cached(cache_key, raw, _TTL_TVL)
        return raw

    # ------------------------------------------------------------------
    # Stablecoin endpoints
    # ------------------------------------------------------------------

    async def get_stablecoins(self) -> List[StablecoinFlow]:
        """Fetch stablecoin circulating supply and flow data.

        GET https://stablecoins.llama.fi/stablecoins
        """
        cache_key = "stablecoins"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        raw = await self._get(f"{_STABLECOINS_URL}/stablecoins")
        if raw is None:
            return []

        peg_data = raw.get("peggedAssets", [])
        results: List[StablecoinFlow] = []

        for item in peg_data:
            try:
                # Extract circulating from the nested structure
                circulating = 0.0
                circ_data = item.get("circulating", {})
                if isinstance(circ_data, dict):
                    circulating = float(circ_data.get("peggedUSD", 0))
                elif isinstance(circ_data, (int, float)):
                    circulating = float(circ_data)

                results.append(StablecoinFlow(
                    name=item.get("name", ""),
                    symbol=item.get("symbol", ""),
                    peg_type=item.get("pegType", "unknown"),
                    circulating=circulating,
                    change_1d=item.get("change_1d"),
                    change_7d=item.get("change_7d"),
                ))
            except (ValueError, TypeError):
                continue

        self._set_cached(cache_key, results, _TTL_STABLECOINS)
        logger.info("Fetched %d stablecoins from DeFiLlama", len(results))
        return results

    # ------------------------------------------------------------------
    # DEX volume endpoints
    # ------------------------------------------------------------------

    async def get_dex_volumes(self) -> Optional[DEXVolumeSnapshot]:
        """Fetch aggregate DEX trading volume data.

        GET https://api.llama.fi/overview/dexs
        """
        cache_key = "dex_volumes"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        raw = await self._get(f"{_BASE_URL}/overview/dexs")
        if raw is None:
            return None

        total_24h = float(raw.get("total24h", 0))
        change_1d = raw.get("change_1d")

        # Extract top protocols by volume
        protocols = []
        for p in raw.get("protocols", [])[:20]:
            protocols.append({
                "name": p.get("name", ""),
                "volume_24h": float(p.get("total24h", 0)),
                "change_1d": p.get("change_1d"),
            })

        result = DEXVolumeSnapshot(
            total_24h=total_24h,
            change_1d=change_1d,
            protocols=protocols,
        )

        self._set_cached(cache_key, result, _TTL_DEX_VOLUMES)
        logger.info("DEX 24h volume: $%.2fM", total_24h / 1e6)
        return result

    # ------------------------------------------------------------------
    # Yield endpoints
    # ------------------------------------------------------------------

    async def get_yield_pools(
        self,
        min_tvl: float = 1_000_000,
        max_results: int = 100,
    ) -> List[YieldPool]:
        """Fetch yield / APY pool data, filtered by minimum TVL.

        GET https://yields.llama.fi/pools
        """
        cache_key = f"yields:{min_tvl}:{max_results}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        raw = await self._get(f"{_YIELDS_URL}/pools")
        if raw is None:
            return []

        pool_data = raw.get("data", [])
        results: List[YieldPool] = []

        for item in pool_data:
            try:
                tvl = float(item.get("tvlUsd", 0))
                if tvl < min_tvl:
                    continue

                results.append(YieldPool(
                    pool_id=item.get("pool", ""),
                    project=item.get("project", ""),
                    chain=item.get("chain", ""),
                    symbol=item.get("symbol", ""),
                    tvl_usd=tvl,
                    apy=float(item.get("apy", 0)),
                    apy_base=item.get("apyBase"),
                    apy_reward=item.get("apyReward"),
                    il_risk=item.get("ilRisk"),
                ))

                if len(results) >= max_results:
                    break
            except (ValueError, TypeError):
                continue

        self._set_cached(cache_key, results, _TTL_YIELDS)
        logger.info("Fetched %d yield pools (min TVL $%.0f)", len(results), min_tvl)
        return results

    # ------------------------------------------------------------------
    # Derived analytics
    # ------------------------------------------------------------------

    async def get_total_tvl(self) -> float:
        """Get the aggregate TVL across all tracked chains."""
        chains = await self.get_chains()
        return sum(c.tvl for c in chains)

    async def get_tvl_trend(self) -> Tuple[str, float]:
        """Determine TVL trend direction from protocol-level 1d/7d changes.

        Returns:
            (trend, magnitude) where trend is "rising" | "falling" | "stable"
            and magnitude is the average percentage change.
        """
        protocols = await self.get_protocols()
        if not protocols:
            return "stable", 0.0

        # Weight by TVL -- large protocols matter more
        total_tvl = sum(p.tvl for p in protocols if p.tvl > 0)
        if total_tvl == 0:
            return "stable", 0.0

        weighted_change = 0.0
        counted_tvl = 0.0
        for p in protocols:
            if p.tvl > 0 and p.change_1d is not None:
                weighted_change += p.change_1d * p.tvl
                counted_tvl += p.tvl

        if counted_tvl == 0:
            return "stable", 0.0

        avg_change = weighted_change / counted_tvl

        if avg_change > 2.0:
            return "rising", avg_change
        elif avg_change < -2.0:
            return "falling", avg_change
        else:
            return "stable", avg_change

    async def get_stablecoin_net_flow(self) -> Tuple[str, float]:
        """Determine net stablecoin flow direction.

        Rising stablecoin supply = capital inflow (bullish).
        Falling stablecoin supply = capital outflow (bearish).

        Returns:
            (direction, total_change_pct)
        """
        stables = await self.get_stablecoins()
        if not stables:
            return "balanced", 0.0

        total_circ = sum(s.circulating for s in stables if s.circulating > 0)
        if total_circ == 0:
            return "balanced", 0.0

        weighted_change = 0.0
        counted_circ = 0.0
        for s in stables:
            if s.circulating > 0 and s.change_7d is not None:
                weighted_change += s.change_7d * s.circulating
                counted_circ += s.circulating

        if counted_circ == 0:
            return "balanced", 0.0

        avg_change = weighted_change / counted_circ

        if avg_change > 1.0:
            return "inflow", avg_change
        elif avg_change < -1.0:
            return "outflow", avg_change
        else:
            return "balanced", avg_change

    async def get_average_yield(self, chain: Optional[str] = None) -> float:
        """Get TVL-weighted average yield across pools.

        High yields in a rising market = strong DeFi sentiment.
        Compressing yields = risk-off / capital rotation.
        """
        pools = await self.get_yield_pools()
        if not pools:
            return 0.0

        if chain:
            pools = [p for p in pools if p.chain.lower() == chain.lower()]

        total_tvl = sum(p.tvl_usd for p in pools if p.tvl_usd > 0)
        if total_tvl == 0:
            return 0.0

        weighted_apy = sum(p.apy * p.tvl_usd for p in pools if p.tvl_usd > 0)
        return weighted_apy / total_tvl
