"""Etherscan API client for on-chain activity analysis.

Provides:
- Whale wallet tracking (large ERC-20 and ETH transfers)
- Exchange inflow/outflow (known exchange hot wallet addresses)
- Gas price trends as a network activity proxy
- Token holder distribution changes

Uses the free Etherscan API tier:
- Without key: 1 req / 5 sec  (conservative default)
- With key:    5 req / sec

API key is optional -- loaded from ETHERSCAN_API_KEY env var.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_BASE_URL = "https://api.etherscan.io/v2/api"

# Rate limits
_RATE_LIMIT_WITH_KEY = 0.2     # 5 req/sec
_RATE_LIMIT_WITHOUT_KEY = 5.0  # 1 req/5sec

_REQUEST_TIMEOUT = 15  # seconds

# Cache TTLs
_TTL_GAS = 120            # 2 min  -- gas changes frequently
_TTL_TRANSFERS = 300      # 5 min
_TTL_TOKEN_HOLDERS = 3600 # 1 hour

# Whale threshold in ETH (transactions above this are "whale" activity)
_WHALE_THRESHOLD_ETH = 100.0

# ---------------------------------------------------------------------------
# Known exchange hot wallet addresses (Ethereum mainnet)
# Source: etherscan labels, public disclosures
# ---------------------------------------------------------------------------
_EXCHANGE_ADDRESSES: Dict[str, str] = {
    # Binance
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance",
    "0x56eddb7aa87536c09ccc2793473599fd21a8b17f": "Binance",
    # Coinbase
    "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase",
    "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43": "Coinbase",
    "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase",
    # Kraken
    "0x2910543af39aba0cd09dbb2d50200b3e800a63d2": "Kraken",
    "0x267be1c1d684f78cb4f6a176c4911b741e4ffdc0": "Kraken",
    # OKX
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX",
    # Bitfinex
    "0x876eabf441b2ee5b5b0554fd502a8e0600950cfa": "Bitfinex",
    "0x742d35cc6634c0532925a3b844bc9e7595f2bd1e": "Bitfinex",
    # Gemini
    "0xd24400ae8bfebb18ca49be86258a3c749cf46853": "Gemini",
    # Bybit
    "0xf89d7b9c864f589bbf53a82105107622b35eaa40": "Bybit",
}

_EXCHANGE_ADDRESS_SET: Set[str] = set(_EXCHANGE_ADDRESSES.keys())


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
class WhaleTransfer:
    """A large on-chain transfer."""
    tx_hash: str
    from_addr: str
    to_addr: str
    value_eth: float
    token_symbol: str
    block_number: int
    timestamp: datetime
    from_label: str = ""  # e.g. "Binance", "Unknown"
    to_label: str = ""
    is_exchange_inflow: bool = False
    is_exchange_outflow: bool = False


@dataclass
class GasSnapshot:
    """Ethereum gas price snapshot."""
    safe_low: float      # Gwei
    standard: float      # Gwei
    fast: float          # Gwei
    base_fee: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ExchangeFlowSummary:
    """Aggregate exchange inflow/outflow over a window."""
    net_flow_eth: float        # positive = net inflow, negative = net outflow
    total_inflow_eth: float
    total_outflow_eth: float
    inflow_count: int
    outflow_count: int
    direction: str             # "net_inflow" | "net_outflow" | "balanced"
    top_exchanges: Dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class EtherscanClient:
    """Async client for the Etherscan API.

    Features:
    - Auto-detects API key from environment for higher rate limits
    - Lazy session creation
    - Response caching with per-endpoint TTL
    - Conservative rate limiting for free tier
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        request_timeout: int = _REQUEST_TIMEOUT,
        whale_threshold_eth: float = _WHALE_THRESHOLD_ETH,
    ):
        self._api_key = api_key or os.environ.get("ETHERSCAN_API_KEY", "")
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        self._whale_threshold = whale_threshold_eth
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, CacheEntry] = {}

        # Rate limit depends on whether we have an API key
        self._min_interval = (
            _RATE_LIMIT_WITH_KEY if self._api_key else _RATE_LIMIT_WITHOUT_KEY
        )
        self._last_request_time = 0.0

        if not self._api_key:
            logger.info(
                "No ETHERSCAN_API_KEY found; using free tier (1 req/5s). "
                "Set the env var for 5 req/s."
            )

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                headers={"Accept": "application/json"},
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Rate limiting & caching
    # ------------------------------------------------------------------

    async def _rate_limit(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.monotonic()

    def _get_cached(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if entry and not entry.is_expired:
            return entry.data
        return None

    def _set_cached(self, key: str, data: Any, ttl: float) -> None:
        self._cache[key] = CacheEntry(data=data, fetched_at=time.monotonic(), ttl=ttl)

    # ------------------------------------------------------------------
    # Low-level API call
    # ------------------------------------------------------------------

    async def _call(self, params: Dict[str, str]) -> Optional[Any]:
        """Make a rate-limited Etherscan API call.

        Automatically appends the API key if available.
        """
        await self._rate_limit()
        session = await self._get_session()

        params["chainid"] = "1"  # Ethereum mainnet
        if self._api_key:
            params["apikey"] = self._api_key

        try:
            async with session.get(_BASE_URL, params=params) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(
                        "Etherscan returned %d: %s", resp.status, body[:200]
                    )
                    return None

                data = await resp.json()

                # Etherscan returns {"status": "1", "result": ...} on success
                if data.get("status") == "0":
                    msg = data.get("message", "")
                    result = data.get("result", "")
                    # "No transactions found" is not an error
                    if "no transactions" in str(result).lower():
                        return []
                    logger.warning("Etherscan error: %s -- %s", msg, result)
                    return None

                return data.get("result")

        except asyncio.TimeoutError:
            logger.warning("Etherscan request timed out")
            return None
        except aiohttp.ClientError as exc:
            logger.warning("Etherscan request failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Gas price
    # ------------------------------------------------------------------

    async def get_gas_price(self) -> Optional[GasSnapshot]:
        """Fetch current gas price oracle data.

        Gas prices serve as a proxy for network activity:
        - High gas = high demand / congestion (active market)
        - Low gas  = low demand (quiet market)
        """
        cache_key = "gas_price"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        result = await self._call({
            "module": "gastracker",
            "action": "gasoracle",
        })

        if result is None or not isinstance(result, dict):
            return None

        try:
            snapshot = GasSnapshot(
                safe_low=float(result.get("SafeGasPrice", 0)),
                standard=float(result.get("ProposeGasPrice", 0)),
                fast=float(result.get("FastGasPrice", 0)),
                base_fee=float(result.get("suggestBaseFee", 0))
                if result.get("suggestBaseFee") else None,
            )
        except (ValueError, TypeError):
            return None

        self._set_cached(cache_key, snapshot, _TTL_GAS)
        logger.debug(
            "Gas: safe=%.1f standard=%.1f fast=%.1f Gwei",
            snapshot.safe_low, snapshot.standard, snapshot.fast,
        )
        return snapshot

    # ------------------------------------------------------------------
    # Whale / large transfer tracking
    # ------------------------------------------------------------------

    async def get_recent_whale_transfers(
        self,
        address: Optional[str] = None,
        block_count: int = 100,
    ) -> List[WhaleTransfer]:
        """Fetch recent large ETH transfers.

        If address is provided, fetches transfers for that address.
        Otherwise, fetches recent normal transactions from the latest blocks.

        Whale = transfer >= _WHALE_THRESHOLD_ETH
        """
        cache_key = f"whale:{address or 'all'}:{block_count}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        if address:
            params = {
                "module": "account",
                "action": "txlist",
                "address": address,
                "startblock": "0",
                "endblock": "99999999",
                "page": "1",
                "offset": str(min(block_count, 100)),
                "sort": "desc",
            }
        else:
            # Get latest block number first, then scan recent blocks
            block_result = await self._call({
                "module": "proxy",
                "action": "eth_blockNumber",
            })
            if block_result is None:
                return []

            try:
                latest_block = int(block_result, 16)
            except (ValueError, TypeError):
                return []

            start_block = max(0, latest_block - block_count)

            # Use internal transactions for large transfers
            params = {
                "module": "account",
                "action": "txlistinternal",
                "startblock": str(start_block),
                "endblock": str(latest_block),
                "page": "1",
                "offset": "100",
                "sort": "desc",
            }

        result = await self._call(params)
        if not result or not isinstance(result, list):
            return []

        transfers: List[WhaleTransfer] = []
        for tx in result:
            try:
                value_wei = int(tx.get("value", "0"))
                value_eth = value_wei / 1e18

                if value_eth < self._whale_threshold:
                    continue

                from_addr = tx.get("from", "").lower()
                to_addr = tx.get("to", "").lower()

                from_label = _EXCHANGE_ADDRESSES.get(from_addr, "")
                to_label = _EXCHANGE_ADDRESSES.get(to_addr, "")

                is_inflow = to_addr in _EXCHANGE_ADDRESS_SET
                is_outflow = from_addr in _EXCHANGE_ADDRESS_SET

                ts = int(tx.get("timeStamp", "0"))

                transfers.append(WhaleTransfer(
                    tx_hash=tx.get("hash", ""),
                    from_addr=from_addr,
                    to_addr=to_addr,
                    value_eth=value_eth,
                    token_symbol="ETH",
                    block_number=int(tx.get("blockNumber", "0")),
                    timestamp=datetime.utcfromtimestamp(ts) if ts else datetime.utcnow(),
                    from_label=from_label,
                    to_label=to_label,
                    is_exchange_inflow=is_inflow,
                    is_exchange_outflow=is_outflow,
                ))
            except (ValueError, TypeError, KeyError):
                continue

        self._set_cached(cache_key, transfers, _TTL_TRANSFERS)
        logger.info(
            "Found %d whale transfers (>= %.0f ETH)",
            len(transfers), self._whale_threshold,
        )
        return transfers

    # ------------------------------------------------------------------
    # Exchange inflow / outflow
    # ------------------------------------------------------------------

    async def get_exchange_flow(
        self,
        lookback_blocks: int = 500,
    ) -> ExchangeFlowSummary:
        """Analyze net exchange inflow/outflow from recent whale transfers.

        - Net inflow (ETH moving TO exchanges) = selling pressure (bearish)
        - Net outflow (ETH moving FROM exchanges) = accumulation (bullish)
        """
        transfers = await self.get_recent_whale_transfers(block_count=lookback_blocks)

        total_inflow = 0.0
        total_outflow = 0.0
        inflow_count = 0
        outflow_count = 0
        exchange_flows: Dict[str, float] = {}

        for t in transfers:
            if t.is_exchange_inflow:
                total_inflow += t.value_eth
                inflow_count += 1
                label = t.to_label or "Unknown Exchange"
                exchange_flows[label] = exchange_flows.get(label, 0) + t.value_eth

            if t.is_exchange_outflow:
                total_outflow += t.value_eth
                outflow_count += 1
                label = t.from_label or "Unknown Exchange"
                exchange_flows[label] = exchange_flows.get(label, 0) - t.value_eth

        net_flow = total_inflow - total_outflow

        # Determine direction with a dead zone
        if net_flow > 50:  # > 50 ETH net inflow
            direction = "net_inflow"
        elif net_flow < -50:
            direction = "net_outflow"
        else:
            direction = "balanced"

        return ExchangeFlowSummary(
            net_flow_eth=net_flow,
            total_inflow_eth=total_inflow,
            total_outflow_eth=total_outflow,
            inflow_count=inflow_count,
            outflow_count=outflow_count,
            direction=direction,
            top_exchanges=dict(
                sorted(exchange_flows.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
            ),
        )

    # ------------------------------------------------------------------
    # Whale activity classification
    # ------------------------------------------------------------------

    async def classify_whale_activity(
        self,
        lookback_blocks: int = 500,
    ) -> Tuple[str, Dict[str, Any]]:
        """Classify overall whale behavior.

        Returns:
            (classification, metadata) where classification is one of:
            "accumulating" -- whales moving off exchanges (buying)
            "distributing" -- whales moving to exchanges (selling)
            "neutral"      -- balanced or low activity
        """
        transfers = await self.get_recent_whale_transfers(block_count=lookback_blocks)

        if not transfers:
            return "neutral", {"reason": "no_whale_transfers", "count": 0}

        exchange_inflows = [t for t in transfers if t.is_exchange_inflow]
        exchange_outflows = [t for t in transfers if t.is_exchange_outflow]

        inflow_volume = sum(t.value_eth for t in exchange_inflows)
        outflow_volume = sum(t.value_eth for t in exchange_outflows)
        total_volume = sum(t.value_eth for t in transfers)

        # Ratio of exchange-bound to total whale movement
        exchange_ratio = (inflow_volume + outflow_volume) / total_volume if total_volume > 0 else 0

        metadata = {
            "total_transfers": len(transfers),
            "exchange_inflows": len(exchange_inflows),
            "exchange_outflows": len(exchange_outflows),
            "inflow_volume_eth": inflow_volume,
            "outflow_volume_eth": outflow_volume,
            "total_volume_eth": total_volume,
            "exchange_ratio": exchange_ratio,
        }

        if outflow_volume > inflow_volume * 1.5:
            return "accumulating", metadata
        elif inflow_volume > outflow_volume * 1.5:
            return "distributing", metadata
        else:
            return "neutral", metadata

    # ------------------------------------------------------------------
    # Gas trend as activity proxy
    # ------------------------------------------------------------------

    async def get_gas_trend(self) -> Tuple[str, Dict[str, Any]]:
        """Interpret gas prices as a network activity proxy.

        High gas = high on-chain activity (often correlated with
        volatility and trading volume).

        Returns:
            (level, metadata) where level is "high" | "moderate" | "low"
        """
        gas = await self.get_gas_price()
        if gas is None:
            return "unknown", {"reason": "gas_fetch_failed"}

        standard = gas.standard

        # Thresholds based on historical Ethereum gas norms
        # These shift over time; using post-merge / EIP-1559 ranges
        if standard > 50:
            level = "high"
        elif standard > 15:
            level = "moderate"
        else:
            level = "low"

        metadata = {
            "safe_low_gwei": gas.safe_low,
            "standard_gwei": gas.standard,
            "fast_gwei": gas.fast,
            "base_fee_gwei": gas.base_fee,
            "level": level,
        }

        return level, metadata

    # ------------------------------------------------------------------
    # Token holder distribution (ERC-20)
    # ------------------------------------------------------------------

    async def get_token_top_holders(
        self,
        contract_address: str,
        page: int = 1,
        offset: int = 20,
    ) -> List[Dict[str, Any]]:
        """Fetch top token holders for an ERC-20 contract.

        Note: This endpoint requires an Etherscan Pro key for some tokens.
        Falls back gracefully if unavailable.
        """
        cache_key = f"holders:{contract_address}:{page}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        result = await self._call({
            "module": "token",
            "action": "tokenholderlist",
            "contractaddress": contract_address,
            "page": str(page),
            "offset": str(offset),
        })

        if not result or not isinstance(result, list):
            return []

        holders = []
        for item in result:
            try:
                addr = item.get("TokenHolderAddress", "").lower()
                qty = float(item.get("TokenHolderQuantity", "0"))
                is_exchange = addr in _EXCHANGE_ADDRESS_SET
                label = _EXCHANGE_ADDRESSES.get(addr, "")

                holders.append({
                    "address": addr,
                    "quantity": qty,
                    "is_exchange": is_exchange,
                    "label": label,
                })
            except (ValueError, TypeError):
                continue

        self._set_cached(cache_key, holders, _TTL_TOKEN_HOLDERS)
        return holders

    async def get_holder_concentration(
        self,
        contract_address: str,
    ) -> Dict[str, Any]:
        """Analyze token holder concentration.

        Returns metrics about how concentrated token holdings are,
        and what fraction sits on exchanges vs. private wallets.
        """
        holders = await self.get_token_top_holders(contract_address, offset=50)
        if not holders:
            return {
                "status": "unavailable",
                "reason": "no_holder_data",
            }

        total = sum(h["quantity"] for h in holders)
        if total == 0:
            return {"status": "unavailable", "reason": "zero_supply"}

        exchange_holdings = sum(h["quantity"] for h in holders if h["is_exchange"])
        top_10_holdings = sum(h["quantity"] for h in holders[:10])

        return {
            "status": "ok",
            "top_holders_count": len(holders),
            "top_10_concentration": top_10_holdings / total if total > 0 else 0,
            "exchange_concentration": exchange_holdings / total if total > 0 else 0,
            "exchange_vs_private": (
                "exchange_heavy" if exchange_holdings > total * 0.4
                else "private_heavy" if exchange_holdings < total * 0.15
                else "balanced"
            ),
        }
