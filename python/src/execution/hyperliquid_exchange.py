"""Hyperliquid implementation of AbstractExchange.

Wraps HyperliquidConnector to provide the standardized AbstractExchange
interface used by the AIFred execution layer. This allows Hyperliquid to be
used interchangeably with CCXT-based exchanges, paper trading, and backtesting.

Usage:
    exchange = HyperliquidExchange(
        user_address="0x...",
        private_key="0x...",   # optional, for order placement
        testnet=False,
    )
    await exchange.connect()
    balance = await exchange.get_balance()
    ticker = await exchange.get_ticker("BTC/USDT")
"""

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from src.execution.abstract_exchange import (
    AbstractExchange,
    BalanceInfo,
    OrderRequest,
    OrderResponse,
    TickerInfo,
)
from src.execution.hyperliquid_connector import HyperliquidConnector

logger = logging.getLogger(__name__)


class HyperliquidExchange(AbstractExchange):
    """Hyperliquid DEX via the AbstractExchange interface.

    Read-only mode (no private key):
        Can fetch prices, balances, positions, order book, candles.
        Calling place_order / cancel_order will raise RuntimeError.

    Agent mode (with private key):
        Full trading capability via EIP-712 signed transactions.
        The private key should be an agent/delegate wallet, not the main wallet.
    """

    def __init__(
        self,
        user_address: str = "",
        private_key: str = "",
        testnet: bool = False,
    ) -> None:
        self._connector = HyperliquidConnector(
            user_address=user_address,
            private_key=private_key,
            testnet=testnet,
        )
        self._testnet = testnet

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "hyperliquid"

    @property
    def is_live(self) -> bool:
        """True when a private key is configured (can trade real money)."""
        return self._connector.can_trade

    @property
    def connector(self) -> HyperliquidConnector:
        """Direct access to the underlying connector for advanced operations."""
        return self._connector

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect to Hyperliquid and fetch asset metadata."""
        await self._connector.connect()
        logger.info("HyperliquidExchange connected (live=%s, testnet=%s)",
                     self.is_live, self._testnet)

    async def disconnect(self) -> None:
        """Disconnect from Hyperliquid."""
        await self._connector.disconnect()
        logger.info("HyperliquidExchange disconnected")

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place an order on Hyperliquid.

        Args:
            request: Standardized order request.

        Returns:
            Standardized order response.

        Raises:
            RuntimeError: If no private key is configured.
        """
        result = await self._connector.place_order(
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            amount=request.amount,
            price=request.price,
            params=request.params,
        )

        return OrderResponse(
            id=result.get("id", str(uuid.uuid4())),
            symbol=result.get("symbol", request.symbol),
            side=result.get("side", request.side),
            order_type=result.get("type", request.order_type),
            amount=result.get("amount", request.amount),
            filled=result.get("amount", request.amount) if result.get("status") == "filled" else 0.0,
            remaining=0.0 if result.get("status") == "filled" else result.get("amount", request.amount),
            average_price=result.get("price", request.price or 0.0),
            status=result.get("status", "open"),
            fee=0.0,  # Fees are deducted from margin, not returned in order response
            fee_currency="USDC",
            timestamp=int(time.time() * 1000),
            exchange="hyperliquid",
            raw=result.get("raw", result),
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an open order.

        Args:
            order_id: Hyperliquid order ID.
            symbol: Trading pair.

        Returns:
            True if cancellation was successful.
        """
        try:
            result = await self._connector.cancel_order(order_id, symbol)
            return result.get("status") == "cancelled"
        except Exception as e:
            logger.error("Failed to cancel order %s: %s", order_id, e)
            return False

    async def get_order(self, order_id: str, symbol: str) -> OrderResponse:
        """Get current state of an order.

        Hyperliquid does not have a direct "get order by ID" endpoint, so we
        check open orders and recent fills to reconstruct the order state.

        Args:
            order_id: Hyperliquid order ID.
            symbol: Trading pair.

        Returns:
            Current order state.
        """
        # Check open orders first
        open_orders = await self._connector.get_open_orders()
        for o in open_orders:
            if str(o["id"]) == str(order_id):
                return OrderResponse(
                    id=str(o["id"]),
                    symbol=f"{o['symbol']}/USDT" if "/" not in o["symbol"] else o["symbol"],
                    side=o["side"],
                    order_type=o.get("order_type", "limit"),
                    amount=o["size"],
                    filled=0.0,
                    remaining=o["size"],
                    average_price=o["price"],
                    status="open",
                    timestamp=o.get("timestamp", 0),
                    exchange="hyperliquid",
                )

        # Not in open orders -- check recent fills
        fills = await self._connector.get_user_fills(limit=50)
        for f in fills:
            if str(f.get("id")) == str(order_id):
                return OrderResponse(
                    id=str(f["id"]),
                    symbol=f"{f['symbol']}/USDT" if "/" not in f["symbol"] else f["symbol"],
                    side=f["side"],
                    order_type="limit",
                    amount=f["size"],
                    filled=f["size"],
                    remaining=0.0,
                    average_price=f["price"],
                    status="closed",
                    fee=f.get("fee", 0.0),
                    fee_currency="USDC",
                    timestamp=f.get("timestamp", 0),
                    exchange="hyperliquid",
                )

        # Order not found in either -- assume cancelled or expired
        return OrderResponse(
            id=order_id,
            symbol=symbol,
            side="",
            order_type="",
            amount=0.0,
            filled=0.0,
            remaining=0.0,
            average_price=0.0,
            status="unknown",
            exchange="hyperliquid",
        )

    async def get_open_orders(
        self, symbol: Optional[str] = None,
    ) -> List[OrderResponse]:
        """Get all open orders, optionally filtered by symbol.

        Args:
            symbol: If provided, only return orders for this pair.

        Returns:
            List of open orders as OrderResponse.
        """
        raw_orders = await self._connector.get_open_orders()

        if symbol:
            coin = symbol.split("/")[0].split("-")[0].upper()
            raw_orders = [o for o in raw_orders if o["symbol"] == coin]

        return [
            OrderResponse(
                id=str(o["id"]),
                symbol=f"{o['symbol']}/USDT" if "/" not in o["symbol"] else o["symbol"],
                side=o["side"],
                order_type=o.get("order_type", "limit"),
                amount=o["size"],
                filled=0.0,
                remaining=o["size"],
                average_price=o["price"],
                status="open",
                timestamp=o.get("timestamp", 0),
                exchange="hyperliquid",
            )
            for o in raw_orders
        ]

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def get_balance(self) -> BalanceInfo:
        """Get account balance as standardized BalanceInfo.

        Returns:
            BalanceInfo with USD-denominated totals.
        """
        raw = await self._connector.get_balance()
        return BalanceInfo(
            total_usd=raw.get("total", 0.0),
            free_usd=raw.get("free", 0.0),
            used_usd=raw.get("used", 0.0),
            assets={
                "USDC": {
                    "total": raw.get("total", 0.0),
                    "free": raw.get("free", 0.0),
                    "used": raw.get("used", 0.0),
                }
            },
        )

    async def get_ticker(self, symbol: str) -> TickerInfo:
        """Get current ticker for a symbol.

        Args:
            symbol: Trading pair (e.g. "BTC/USDT" or "BTC").

        Returns:
            Standardized ticker data.
        """
        raw = await self._connector.get_ticker(symbol)
        return TickerInfo(
            symbol=raw.get("symbol", symbol),
            last=raw.get("last", 0.0),
            bid=raw.get("bid", 0.0),
            ask=raw.get("ask", 0.0),
            volume=raw.get("volume", 0.0),
            timestamp=raw.get("timestamp", int(time.time() * 1000)),
        )

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get open positions.

        Returns:
            List of position dicts with symbol, side, size, entry_price, etc.
        """
        return await self._connector.get_positions()

    async def ping(self) -> float:
        """Check connectivity and return latency in milliseconds.

        Returns:
            Latency in ms, or -1.0 on failure.
        """
        return await self._connector.ping()
