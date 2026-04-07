"""Hyperliquid exchange connector for the AIFred trading system.

Hyperliquid is a non-custodial perpetuals DEX on Arbitrum.
No API keys needed -- just an Ethereum address (read) or private key (write).

Two modes:
  - Read-only: Fetch prices, balances, positions for any address
  - Agent mode: Place/cancel orders using a private key (agent wallet)

The frontend uses MetaMask to sign. The Python backend can use an agent wallet
(delegated signing authority) so the user's main wallet key never touches the server.

API docs: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api
"""

import asyncio
import hashlib
import json
import logging
import struct
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hyperliquid API endpoints
# ---------------------------------------------------------------------------

HL_MAINNET_INFO = "https://api.hyperliquid.xyz/info"
HL_MAINNET_EXCHANGE = "https://api.hyperliquid.xyz/exchange"
HL_TESTNET_INFO = "https://api.hyperliquid-testnet.xyz/info"
HL_TESTNET_EXCHANGE = "https://api.hyperliquid-testnet.xyz/exchange"

# EIP-712 domain for Hyperliquid (mainnet uses chain_id=1337, testnet=13371)
HL_MAINNET_CHAIN_ID = 1337
HL_TESTNET_CHAIN_ID = 13371


# ---------------------------------------------------------------------------
# EIP-712 helpers (standalone, no SDK dependency)
# ---------------------------------------------------------------------------

def _float_to_wire(x: float, decimals: int = 8) -> str:
    """Convert a float to Hyperliquid's wire format string."""
    return f"{x:.{decimals}f}".rstrip("0").rstrip(".")


def _order_type_to_wire(order_type: str, price: Optional[float],
                        tif: str = "Gtc") -> Dict[str, Any]:
    """Build the orderType wire object for Hyperliquid."""
    if order_type == "market":
        return {"limit": {"tif": "Ioc"}}
    return {"limit": {"tif": tif}}


def _action_hash(action: Dict, vault_address: Optional[str],
                 nonce: int) -> bytes:
    """Compute the action hash used for EIP-712 signing on Hyperliquid.

    Hyperliquid uses a custom hashing scheme over the action JSON + nonce,
    not standard EIP-712 struct hashing. This mirrors the SDK's approach.
    """
    # Serialize action deterministically
    action_bytes = json.dumps(action, separators=(",", ":"), sort_keys=True).encode()
    # Build the data to hash: action_bytes + nonce (big-endian u64) + vault
    data = action_bytes + struct.pack(">Q", nonce)
    if vault_address:
        data += bytes.fromhex(vault_address[2:] if vault_address.startswith("0x") else vault_address)
    return hashlib.sha256(data).digest()


# ---------------------------------------------------------------------------
# HyperliquidConnector
# ---------------------------------------------------------------------------

class HyperliquidConnector:
    """Hyperliquid exchange connector.

    Usage (read-only):
        hl = HyperliquidConnector(user_address="0x...")
        await hl.connect()
        balance = await hl.get_balance()
        positions = await hl.get_positions()
        price = await hl.get_ticker("BTC")

    Usage (agent mode with private key):
        hl = HyperliquidConnector(user_address="0x...", private_key="0x...")
        await hl.connect()
        result = await hl.place_order("BTC", "buy", "limit", 0.01, price=65000)
    """

    def __init__(
        self,
        user_address: str = "",
        private_key: str = "",
        testnet: bool = False,
    ) -> None:
        self.name = "hyperliquid"
        self.user_address = user_address.lower() if user_address else ""
        self._private_key = private_key
        self._testnet = testnet

        # Endpoint URLs
        self._info_url = HL_TESTNET_INFO if testnet else HL_MAINNET_INFO
        self._exchange_url = HL_TESTNET_EXCHANGE if testnet else HL_MAINNET_EXCHANGE
        self._chain_id = HL_TESTNET_CHAIN_ID if testnet else HL_MAINNET_CHAIN_ID

        # Session and metadata
        self._session: Optional[aiohttp.ClientSession] = None
        self._meta: Optional[Dict] = None
        self._asset_to_index: Dict[str, int] = {}   # "BTC" -> 0, "ETH" -> 1, ...
        self._asset_sz_decimals: Dict[str, int] = {}  # size decimal places per asset
        self._connected = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Initialize HTTP session and fetch exchange metadata."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
        )
        try:
            self._meta = await self._post_info({"type": "meta"})
            if self._meta and "universe" in self._meta:
                for i, asset in enumerate(self._meta["universe"]):
                    name = asset["name"]
                    self._asset_to_index[name] = i
                    self._asset_sz_decimals[name] = asset.get("szDecimals", 8)
            self._connected = True
            logger.info(
                "Hyperliquid connected (%s): %d assets, address=%s",
                "testnet" if self._testnet else "mainnet",
                len(self._asset_to_index),
                f"{self.user_address[:6]}...{self.user_address[-4:]}"
                if self.user_address else "none",
            )
        except Exception as e:
            logger.error("Failed to connect to Hyperliquid: %s", e)
            raise

    async def disconnect(self) -> None:
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def can_trade(self) -> bool:
        """Whether this connector can place orders (has private key)."""
        return bool(self._private_key)

    # ------------------------------------------------------------------
    # Low-level HTTP
    # ------------------------------------------------------------------

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def _post_info(self, payload: Dict) -> Any:
        """POST to the info endpoint (public, no auth)."""
        session = await self._ensure_session()
        async with session.post(
            self._info_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(
                    f"Hyperliquid info API error {resp.status}: {body}"
                )
            return await resp.json()

    async def _post_exchange(self, payload: Dict) -> Any:
        """POST to the exchange endpoint (requires signature)."""
        session = await self._ensure_session()
        async with session.post(
            self._exchange_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(
                    f"Hyperliquid exchange API error {resp.status}: {body}"
                )
            return await resp.json()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _normalize_coin(self, symbol: str) -> str:
        """Strip /USDT, /USD, -PERP suffixes to get the HL coin name."""
        coin = symbol.split("/")[0].split("-")[0].upper()
        return coin

    def _get_asset_index(self, coin: str) -> int:
        """Get the Hyperliquid asset index for a coin name."""
        idx = self._asset_to_index.get(coin)
        if idx is None:
            raise ValueError(
                f"Unknown Hyperliquid asset: {coin}. "
                f"Known: {list(self._asset_to_index.keys())[:20]}..."
            )
        return idx

    def _round_size(self, coin: str, size: float) -> float:
        """Round order size to the asset's allowed decimal places."""
        decimals = self._asset_sz_decimals.get(coin, 8)
        factor = 10 ** decimals
        return int(size * factor) / factor

    def _round_price(self, price: float) -> float:
        """Round price to Hyperliquid's 5 significant figures."""
        if price == 0:
            return 0.0
        # Hyperliquid requires prices with at most 5 significant figures
        from math import log10, floor
        sig_figs = 5
        magnitude = floor(log10(abs(price)))
        factor = 10 ** (sig_figs - 1 - magnitude)
        return round(price * factor) / factor

    # ------------------------------------------------------------------
    # Info API -- read-only, no auth required
    # ------------------------------------------------------------------

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get current mid price for a symbol (e.g. 'BTC', 'ETH', 'BTC/USDT').

        Returns a dict with keys: symbol, last, bid, ask, volume, timestamp.
        """
        coin = self._normalize_coin(symbol)
        data = await self._post_info({"type": "allMids"})

        if data and coin in data:
            mid = float(data[coin])
            return {
                "symbol": symbol,
                "last": mid,
                "bid": mid,  # HL only provides mids publicly
                "ask": mid,
                "volume": 0.0,
                "timestamp": int(time.time() * 1000),
            }
        return {
            "symbol": symbol,
            "last": 0.0,
            "bid": 0.0,
            "ask": 0.0,
            "volume": 0.0,
            "timestamp": int(time.time() * 1000),
        }

    async def get_all_mids(self) -> Dict[str, float]:
        """Get mid prices for all assets.

        Returns:
            Dict mapping coin name to mid price, e.g. {"BTC": 65000.0, "ETH": 3400.0}
        """
        data = await self._post_info({"type": "allMids"})
        return {k: float(v) for k, v in (data or {}).items()}

    async def get_l2_book(self, coin: str, depth: int = 20) -> Dict[str, Any]:
        """Get L2 order book for a coin.

        Returns:
            Dict with 'bids' and 'asks', each a list of [price, size] pairs.
        """
        coin = self._normalize_coin(coin)
        data = await self._post_info({
            "type": "l2Book",
            "coin": coin,
        })
        if not data or "levels" not in data:
            return {"bids": [], "asks": []}

        levels = data["levels"]
        bids = [[float(b["px"]), float(b["sz"])] for b in levels[0][:depth]]
        asks = [[float(a["px"]), float(a["sz"])] for a in levels[1][:depth]]
        return {"bids": bids, "asks": asks}

    async def get_balance(self) -> Dict[str, Any]:
        """Get account balance and margin info for self.user_address.

        Checks both perps and spot clearinghouse states to support
        Hyperliquid's unified account mode where spot balance is
        available for perp trading.

        Returns dict with keys: total, free, used, equity, margin_used, raw.
        """
        if not self.user_address:
            return {"total": 0.0, "free": 0.0, "used": 0.0}

        # Fetch both perps and spot in parallel
        perps_data, spot_data = await asyncio.gather(
            self._post_info({
                "type": "clearinghouseState",
                "user": self.user_address,
            }),
            self._post_info({
                "type": "spotClearinghouseState",
                "user": self.user_address,
            }),
            return_exceptions=True,
        )

        # Parse perps balance
        perps_value = 0.0
        margin_used = 0.0
        withdrawable = 0.0
        if isinstance(perps_data, dict):
            margin = perps_data.get("marginSummary", {})
            perps_value = float(margin.get("accountValue", 0))
            margin_used = float(margin.get("totalMarginUsed", 0))
            withdrawable = float(perps_data.get("withdrawable", 0))

        # Parse spot USDC balance (unified account makes this available for perps)
        spot_usdc = 0.0
        if isinstance(spot_data, dict):
            for bal in spot_data.get("balances", []):
                if bal.get("coin") == "USDC":
                    spot_usdc = float(bal.get("total", 0))
                    break

        # Total available = perps equity + spot USDC (unified account)
        total = perps_value + spot_usdc
        free = withdrawable + spot_usdc

        return {
            "total": total,
            "free": free,
            "used": margin_used,
            "equity": total,
            "margin_used": margin_used,
            "spot_usdc": spot_usdc,
            "perps_value": perps_value,
            "raw": perps_data if isinstance(perps_data, dict) else {},
        }

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions for self.user_address.

        Returns a list of position dicts with keys:
        symbol, side, size, entry_price, mark_price, unrealized_pnl,
        leverage, liquidation_price.
        """
        if not self.user_address:
            return []

        data = await self._post_info({
            "type": "clearinghouseState",
            "user": self.user_address,
        })

        if not data:
            return []

        positions = []
        for ap in data.get("assetPositions", []):
            pos = ap.get("position", {})
            size = float(pos.get("szi", 0))
            if size == 0:
                continue

            entry_px = float(pos.get("entryPx", 0))
            position_value = float(pos.get("positionValue", 0))
            mark_price = position_value / abs(size) if size != 0 else 0.0

            # leverage can be a dict {"type": "cross", "value": 5} or similar
            lev_raw = pos.get("leverage", {})
            if isinstance(lev_raw, dict):
                leverage = float(lev_raw.get("value", 1))
            else:
                leverage = float(lev_raw or 1)

            liq_px_raw = pos.get("liquidationPx")
            liq_px = float(liq_px_raw) if liq_px_raw and liq_px_raw != "null" else 0.0

            positions.append({
                "symbol": pos.get("coin", ""),
                "side": "LONG" if size > 0 else "SHORT",
                "size": abs(size),
                "entry_price": entry_px,
                "mark_price": mark_price,
                "unrealized_pnl": float(pos.get("unrealizedPnl", 0)),
                "leverage": leverage,
                "liquidation_price": liq_px,
                "return_on_equity": float(pos.get("returnOnEquity", 0)),
            })

        return positions

    async def get_open_orders(self) -> List[Dict[str, Any]]:
        """Get all open orders for self.user_address.

        Returns a list of order dicts with keys:
        id, symbol, side, price, size, order_type, timestamp.
        """
        if not self.user_address:
            return []

        data = await self._post_info({
            "type": "openOrders",
            "user": self.user_address,
        })

        return [
            {
                "id": str(o.get("oid", "")),
                "symbol": o.get("coin", ""),
                "side": o.get("side", "").lower(),
                "price": float(o.get("limitPx", 0)),
                "size": float(o.get("sz", 0)),
                "order_type": "limit",
                "timestamp": o.get("timestamp", 0),
            }
            for o in (data or [])
        ]

    async def get_user_fills(
        self, start_time: Optional[int] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent fills/trades for self.user_address.

        Args:
            start_time: Unix timestamp in ms. If None, fetches most recent.
            limit: Max number of fills to return.

        Returns:
            List of fill dicts.
        """
        if not self.user_address:
            return []

        payload: Dict[str, Any] = {
            "type": "userFills",
            "user": self.user_address,
        }
        if start_time is not None:
            payload["startTime"] = start_time

        data = await self._post_info(payload)
        fills = []
        for f in (data or [])[:limit]:
            fills.append({
                "id": str(f.get("tid", "")),
                "symbol": f.get("coin", ""),
                "side": f.get("side", "").lower(),
                "price": float(f.get("px", 0)),
                "size": float(f.get("sz", 0)),
                "fee": float(f.get("fee", 0)),
                "timestamp": f.get("time", 0),
                "closed_pnl": float(f.get("closedPnl", 0)),
            })
        return fills

    async def get_funding_history(self, coin: str, start_time: int,
                                   end_time: Optional[int] = None) -> List[Dict]:
        """Get historical funding rates for a coin."""
        payload: Dict[str, Any] = {
            "type": "fundingHistory",
            "coin": self._normalize_coin(coin),
            "startTime": start_time,
        }
        if end_time is not None:
            payload["endTime"] = end_time

        data = await self._post_info(payload)
        return [
            {
                "coin": f.get("coin", ""),
                "funding_rate": float(f.get("fundingRate", 0)),
                "premium": float(f.get("premium", 0)),
                "timestamp": f.get("time", 0),
            }
            for f in (data or [])
        ]

    async def get_ohlcv(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
    ) -> List[List]:
        """Get OHLCV candle data.

        Args:
            symbol: Coin name or pair (e.g. "BTC", "ETH/USDT").
            interval: Candle interval. One of: 1m, 5m, 15m, 30m, 1h, 4h, 1d.
            limit: Number of candles to return.

        Returns:
            List of [timestamp, open, high, low, close, volume] lists.
        """
        coin = self._normalize_coin(symbol)

        interval_map = {
            "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "1h", "2h": "2h", "4h": "4h", "8h": "8h",
            "12h": "12h", "1d": "1d", "3d": "3d", "1w": "1w",
        }
        hl_interval = interval_map.get(interval)
        if hl_interval is None:
            raise ValueError(
                f"Unsupported interval: {interval}. "
                f"Supported: {list(interval_map.keys())}"
            )

        interval_ms = {
            "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
            "30m": 1_800_000, "1h": 3_600_000, "2h": 7_200_000,
            "4h": 14_400_000, "8h": 28_800_000, "12h": 43_200_000,
            "1d": 86_400_000, "3d": 259_200_000, "1w": 604_800_000,
        }.get(hl_interval, 3_600_000)

        now_ms = int(time.time() * 1000)
        start_ms = now_ms - (interval_ms * limit)

        data = await self._post_info({
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": hl_interval,
                "startTime": start_ms,
                "endTime": now_ms,
            },
        })

        # Convert to CCXT-compatible format: [timestamp, open, high, low, close, volume]
        candles = []
        for c in (data or []):
            candles.append([
                c.get("t", 0),
                float(c.get("o", 0)),
                float(c.get("h", 0)),
                float(c.get("l", 0)),
                float(c.get("c", 0)),
                float(c.get("v", 0)),
            ])

        return candles[-limit:]

    async def ping(self) -> float:
        """Check connectivity and return latency in milliseconds.

        Returns:
            Latency in ms, or -1.0 on failure.
        """
        start = time.time()
        try:
            await self._post_info({"type": "meta"})
            return (time.time() - start) * 1000
        except Exception:
            return -1.0

    # ------------------------------------------------------------------
    # Exchange API -- requires EIP-712 signing with private key
    # ------------------------------------------------------------------

    def _sign_action(
        self, action: Dict, nonce: int, vault_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sign an action using EIP-712 via eth_account.

        Args:
            action: The action dict (e.g. order placement).
            nonce: Timestamp nonce in ms.
            vault_address: Optional vault address.

        Returns:
            Dict with 'r', 's', 'v' signature components.

        Raises:
            RuntimeError: If eth_account is not installed.
        """
        try:
            from eth_account import Account
        except ImportError:
            raise RuntimeError(
                "eth_account required for signing. Install: pip install eth-account"
            )

        # Hyperliquid uses a phantom EIP-712 typed data structure
        # The actual message to sign is the connection action hash
        action_hash = _action_hash(action, vault_address, nonce)

        # Build the EIP-712 typed data that Hyperliquid expects
        domain = {
            "name": "Exchange",
            "version": "1",
            "chainId": self._chain_id,
            "verifyingContract": "0x0000000000000000000000000000000000000000",
        }

        # Hyperliquid's EIP-712 type for agent actions
        types = {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "Agent": [
                {"name": "source", "type": "string"},
                {"name": "connectionId", "type": "bytes32"},
            ],
        }

        message = {
            "source": "a" if not self._testnet else "b",
            "connectionId": action_hash,
        }

        # Sign with eth_account
        from eth_account.messages import encode_typed_data
        signable = encode_typed_data(
            domain_data=domain,
            message_types={"Agent": types["Agent"]},
            message_data=message,
        )
        signed = Account.sign_message(signable, private_key=self._private_key)

        return {
            "r": hex(signed.r),
            "s": hex(signed.s),
            "v": signed.v,
        }

    def _build_signed_payload(
        self,
        action: Dict,
        nonce: Optional[int] = None,
        vault_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a complete signed payload for the exchange endpoint.

        Args:
            action: The action dict.
            nonce: Timestamp nonce. Auto-generated if None.
            vault_address: Optional vault address for delegated signing.

        Returns:
            Complete payload ready to POST to the exchange endpoint.
        """
        if nonce is None:
            nonce = int(time.time() * 1000)

        sig = self._sign_action(action, nonce, vault_address)

        payload: Dict[str, Any] = {
            "action": action,
            "nonce": nonce,
            "signature": sig,
        }
        if vault_address:
            payload["vaultAddress"] = vault_address

        return payload

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: Optional[float] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Place an order on Hyperliquid.

        Args:
            symbol: Coin name or pair (e.g. "BTC", "ETH/USDT").
            side: "buy" or "sell".
            order_type: "market" or "limit".
            amount: Size in base currency.
            price: Required for limit orders. For market orders, a slippage
                   price is computed automatically.
            params: Optional extra params. Supported keys:
                - tif: Time in force ("Gtc", "Ioc", "Alo"). Default "Gtc" for limit.
                - reduce_only: bool. Default False.
                - vault_address: str. For vault/sub-account trading.
                - slippage_pct: float. Slippage for market orders (default 1%).

        Returns:
            Dict with order result including 'id', 'symbol', 'side', 'status'.

        Raises:
            RuntimeError: If no private key is set.
            ValueError: If the asset is unknown.
        """
        if not self._private_key:
            raise RuntimeError(
                "Cannot place orders without private key. "
                "Set HYPERLIQUID_PRIVATE_KEY or use an agent wallet."
            )

        params = params or {}
        coin = self._normalize_coin(symbol)
        asset_index = self._get_asset_index(coin)
        is_buy = side.lower() == "buy"

        # Round size to allowed decimals
        rounded_size = self._round_size(coin, amount)
        if rounded_size <= 0:
            raise ValueError(f"Order size too small after rounding: {amount}")

        # Determine price
        if order_type == "market":
            # For market orders, use a far-away limit price with IOC
            slippage_pct = params.get("slippage_pct", 1.0)
            if price is None:
                # Fetch current mid price
                mids = await self.get_all_mids()
                mid = mids.get(coin, 0)
                if mid <= 0:
                    raise ValueError(f"Cannot determine market price for {coin}")
                price = mid
            # Apply slippage
            if is_buy:
                limit_px = self._round_price(price * (1 + slippage_pct / 100))
            else:
                limit_px = self._round_price(price * (1 - slippage_pct / 100))
        else:
            if price is None:
                raise ValueError("Price is required for limit orders")
            limit_px = self._round_price(price)

        tif = params.get("tif", "Ioc" if order_type == "market" else "Gtc")
        reduce_only = params.get("reduce_only", False)

        # Build the order action
        order_wire = {
            "a": asset_index,
            "b": is_buy,
            "p": _float_to_wire(limit_px),
            "s": _float_to_wire(rounded_size, self._asset_sz_decimals.get(coin, 8)),
            "r": reduce_only,
            "t": _order_type_to_wire(order_type, limit_px, tif),
        }

        action = {
            "type": "order",
            "orders": [order_wire],
            "grouping": "na",
        }

        vault_address = params.get("vault_address")
        payload = self._build_signed_payload(action, vault_address=vault_address)

        result = await self._post_exchange(payload)

        # Parse the response
        status_data = result.get("response", {}).get("data", {})
        statuses = status_data.get("statuses", [])
        order_status = statuses[0] if statuses else {}

        # Check for errors
        if "error" in order_status:
            raise RuntimeError(f"Order rejected: {order_status['error']}")

        order_id = ""
        filled_info = order_status.get("filled", order_status.get("resting", {}))
        if isinstance(filled_info, dict):
            order_id = str(filled_info.get("oid", ""))

        return {
            "id": order_id,
            "symbol": f"{coin}/USDT",
            "side": side.lower(),
            "type": order_type,
            "amount": rounded_size,
            "price": limit_px,
            "status": "filled" if "filled" in order_status else "open",
            "exchange": "hyperliquid",
            "raw": result,
        }

    async def cancel_order(
        self,
        order_id: str,
        symbol: str,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Cancel an open order on Hyperliquid.

        Args:
            order_id: The Hyperliquid order ID (oid).
            symbol: Coin name or pair.
            params: Optional. Supported keys:
                - vault_address: str.

        Returns:
            Dict with cancellation result.

        Raises:
            RuntimeError: If no private key is set.
        """
        if not self._private_key:
            raise RuntimeError("Cannot cancel orders without private key")

        params = params or {}
        coin = self._normalize_coin(symbol)
        asset_index = self._get_asset_index(coin)

        action = {
            "type": "cancel",
            "cancels": [
                {"a": asset_index, "o": int(order_id)},
            ],
        }

        vault_address = params.get("vault_address")
        payload = self._build_signed_payload(action, vault_address=vault_address)

        result = await self._post_exchange(payload)
        logger.info("Cancelled order %s for %s: %s", order_id, coin, result)

        return {
            "id": order_id,
            "symbol": f"{coin}/USDT",
            "status": "cancelled",
            "exchange": "hyperliquid",
            "raw": result,
        }

    async def cancel_all_orders(
        self, symbol: Optional[str] = None, params: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """Cancel all open orders, optionally filtered by symbol.

        Args:
            symbol: If provided, only cancel orders for this coin.
            params: Optional extra params.

        Returns:
            List of cancellation results.
        """
        open_orders = await self.get_open_orders()
        if symbol:
            coin = self._normalize_coin(symbol)
            open_orders = [o for o in open_orders if o["symbol"] == coin]

        results = []
        for order in open_orders:
            try:
                result = await self.cancel_order(
                    order["id"], order["symbol"], params=params,
                )
                results.append(result)
            except Exception as e:
                logger.error("Failed to cancel order %s: %s", order["id"], e)
                results.append({
                    "id": order["id"],
                    "status": "error",
                    "error": str(e),
                })
        return results

    async def set_leverage(
        self, symbol: str, leverage: int, is_cross: bool = True,
    ) -> Dict[str, Any]:
        """Set leverage for a symbol.

        Args:
            symbol: Coin name or pair.
            leverage: Leverage multiplier (1-100).
            is_cross: True for cross margin, False for isolated.

        Returns:
            API response dict.
        """
        if not self._private_key:
            raise RuntimeError("Cannot set leverage without private key")

        coin = self._normalize_coin(symbol)
        asset_index = self._get_asset_index(coin)

        action = {
            "type": "updateLeverage",
            "asset": asset_index,
            "isCross": is_cross,
            "leverage": leverage,
        }

        payload = self._build_signed_payload(action)
        result = await self._post_exchange(payload)
        logger.info("Set leverage for %s to %dx (%s): %s",
                     coin, leverage, "cross" if is_cross else "isolated", result)
        return result

    # ------------------------------------------------------------------
    # Convenience: close position
    # ------------------------------------------------------------------

    async def close_position(
        self, symbol: str, params: Optional[Dict] = None,
    ) -> Optional[Dict[str, Any]]:
        """Close an entire position for a symbol using a market order.

        Args:
            symbol: Coin name or pair.
            params: Optional extra params for the order.

        Returns:
            Order result dict, or None if no position exists.
        """
        positions = await self.get_positions()
        coin = self._normalize_coin(symbol)

        target = None
        for pos in positions:
            if pos["symbol"] == coin:
                target = pos
                break

        if target is None:
            logger.info("No open position for %s, nothing to close", coin)
            return None

        close_side = "sell" if target["side"] == "LONG" else "buy"
        close_params = {**(params or {}), "reduce_only": True}

        return await self.place_order(
            symbol=coin,
            side=close_side,
            order_type="market",
            amount=target["size"],
            params=close_params,
        )

    # ------------------------------------------------------------------
    # Sync wrappers for compatibility with sync ExecutionAgent/OrderManager
    # ------------------------------------------------------------------

    @staticmethod
    def _run_sync(coro):
        """Run an async coroutine synchronously."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # Already in an async context — create a new thread to avoid deadlock
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result(timeout=30)
        return asyncio.run(coro)

    def connect_sync(self) -> None:
        """Sync version of connect()."""
        self._run_sync(self.connect())

    def place_order_sync(
        self, symbol: str, side: str, order_type: str,
        amount: float, price: Optional[float] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Sync version of place_order() — used by OrderManager."""
        return self._run_sync(
            self.place_order(symbol, side, order_type, amount, price, params)
        )

    def get_balance_sync(self) -> Dict[str, Any]:
        """Sync version of get_balance() — uses requests for simplicity.

        Checks both perps and spot clearinghouse states to support
        unified account mode.
        """
        import requests

        total = 0.0
        try:
            # Check perps
            r = requests.post(
                self._info_url,
                json={"type": "clearinghouseState", "user": self.user_address},
                timeout=5,
            )
            if r.ok:
                data = r.json()
                total += float(data.get("marginSummary", {}).get("accountValue", 0))

            # Check spot (unified account mode)
            r = requests.post(
                self._info_url,
                json={"type": "spotClearinghouseState", "user": self.user_address},
                timeout=5,
            )
            if r.ok:
                data = r.json()
                for bal in data.get("balances", []):
                    if bal.get("coin") == "USDC":
                        total += float(bal.get("total", 0))
                        break
        except Exception as e:
            logger.warning("get_balance_sync failed: %s", e)

        return {
            "total": {"USDC": total},
            "free": {"USDC": total},
            "used": {"USDC": 0},
        }
