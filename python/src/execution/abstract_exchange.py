"""Abstract exchange interface -- unified API for live, paper, and backtest modes.

Inspired by OctoBot's pattern where backtesting inherits from the main exchange,
guaranteeing that backtest and live trading use identical code paths.

All exchange interactions go through this interface. The ExecutionAgent should
use this instead of directly calling ExchangeConnector or PaperTrader.
"""

import abc
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Standardized data classes
# ---------------------------------------------------------------------------

@dataclass
class OrderRequest:
    """Standardized order request submitted to any exchange implementation."""

    symbol: str                          # e.g. "BTC/USDT"
    side: str                            # "buy" or "sell"
    order_type: str                      # "market", "limit", "stop", "trailing_stop"
    amount: float                        # quantity in base currency
    price: Optional[float] = None        # required for limit orders
    stop_price: Optional[float] = None   # for stop / trailing_stop orders
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderResponse:
    """Standardized order response returned by every exchange implementation."""

    id: str
    symbol: str
    side: str
    order_type: str
    amount: float
    filled: float
    remaining: float
    average_price: float
    status: str            # "open", "closed", "cancelled", "expired", "rejected"
    fee: float = 0.0
    fee_currency: str = "USDT"
    timestamp: int = 0
    exchange: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BalanceInfo:
    """Standardized balance information across all exchange modes."""

    total_usd: float
    free_usd: float
    used_usd: float
    assets: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # assets example: {"BTC": {"total": 0.5, "free": 0.3, "used": 0.2}}


@dataclass
class TickerInfo:
    """Standardized ticker data."""

    symbol: str
    last: float
    bid: float
    ask: float
    volume: float
    timestamp: int


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class AbstractExchange(abc.ABC):
    """Abstract base class for all exchange implementations.

    Concrete implementations:
    - LiveExchange:     wraps CCXT via ExchangeConnector for real exchanges
    - PaperExchange:    wraps PaperTrader for simulated fills
    - BacktestExchange: replays historical data with internal accounting
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Exchange identifier (e.g. 'binance', 'paper', 'backtest')."""
        ...

    @property
    @abc.abstractmethod
    def is_live(self) -> bool:
        """Whether this exchange trades with real money."""
        ...

    @abc.abstractmethod
    async def connect(self) -> None:
        """Establish connection to the exchange."""
        ...

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Close connection gracefully."""
        ...

    @abc.abstractmethod
    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place an order on the exchange.

        Args:
            request: Standardized order request.

        Returns:
            Standardized order response with fill information.
        """
        ...

    @abc.abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an open order.

        Args:
            order_id: Exchange-assigned order identifier.
            symbol: Trading pair the order belongs to.

        Returns:
            True if the order was successfully cancelled.
        """
        ...

    @abc.abstractmethod
    async def get_order(self, order_id: str, symbol: str) -> OrderResponse:
        """Get the current state of an order.

        Args:
            order_id: Exchange-assigned order identifier.
            symbol: Trading pair the order belongs to.

        Returns:
            Current order state as an OrderResponse.
        """
        ...

    @abc.abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResponse]:
        """Get all open orders, optionally filtered by symbol.

        Args:
            symbol: If provided, only return orders for this pair.

        Returns:
            List of open orders.
        """
        ...

    @abc.abstractmethod
    async def get_balance(self) -> BalanceInfo:
        """Get current account balance.

        Returns:
            Standardized balance information.
        """
        ...

    @abc.abstractmethod
    async def get_ticker(self, symbol: str) -> TickerInfo:
        """Get current ticker for a symbol.

        Args:
            symbol: Trading pair (e.g. "BTC/USDT").

        Returns:
            Standardized ticker data.
        """
        ...

    @abc.abstractmethod
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get open positions (relevant for futures/margin).

        Returns:
            List of position dictionaries.
        """
        ...

    async def ping(self) -> float:
        """Check connectivity and return latency in milliseconds.

        Returns:
            Latency in ms, or -1.0 on failure.
        """
        return -1.0


# ---------------------------------------------------------------------------
# LiveExchange -- adapter over ExchangeConnector
# ---------------------------------------------------------------------------

class LiveExchange(AbstractExchange):
    """Live exchange implementation wrapping ExchangeConnector (CCXT).

    Adapts the existing ExchangeConnector to the AbstractExchange interface.
    Adds retry logic with exponential backoff for transient failures.
    """

    _MAX_RETRIES = 3
    _BASE_DELAY = 0.5  # seconds

    def __init__(self, connector: Any) -> None:
        """Initialize with an existing ExchangeConnector instance.

        Args:
            connector: An ExchangeConnector (from exchange_connector.py).
        """
        self._connector = connector
        self._name: str = connector.name

    # -- properties ----------------------------------------------------------

    @property
    def name(self) -> str:
        """Exchange identifier derived from the underlying connector."""
        return self._name

    @property
    def is_live(self) -> bool:
        """LiveExchange always trades with real money (unless sandbox)."""
        return True

    # -- lifecycle -----------------------------------------------------------

    async def connect(self) -> None:
        """Establish an async CCXT connection."""
        await self._connector.connect_async()
        logger.info("LiveExchange connected to %s", self._name)

    async def disconnect(self) -> None:
        """Close the async CCXT connection."""
        await self._connector.close_async()
        logger.info("LiveExchange disconnected from %s", self._name)

    # -- retry helper --------------------------------------------------------

    async def _retry(self, coro_factory, description: str = "operation"):
        """Execute an async operation with exponential-backoff retries.

        Args:
            coro_factory: A zero-arg callable that returns an awaitable.
            description: Human-readable label for logging.

        Returns:
            The result of the awaitable.

        Raises:
            The last exception if all retries are exhausted.
        """
        last_error: Optional[Exception] = None
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                return await coro_factory()
            except Exception as exc:
                last_error = exc
                if attempt < self._MAX_RETRIES:
                    delay = self._BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "LiveExchange %s attempt %d/%d failed: %s  -- retrying in %.1fs",
                        description, attempt, self._MAX_RETRIES, exc, delay,
                    )
                    await asyncio.sleep(delay)
        raise last_error  # type: ignore[misc]

    # -- order helpers -------------------------------------------------------

    @staticmethod
    def _ccxt_order_to_response(raw: Dict[str, Any], exchange: str) -> OrderResponse:
        """Convert a CCXT order dict to a standardized OrderResponse.

        Args:
            raw: Raw CCXT order dictionary.
            exchange: Exchange name for tagging.

        Returns:
            An OrderResponse dataclass.
        """
        fee_info = raw.get("fee") or {}
        return OrderResponse(
            id=str(raw.get("id", "")),
            symbol=raw.get("symbol", ""),
            side=raw.get("side", ""),
            order_type=raw.get("type", ""),
            amount=float(raw.get("amount", 0)),
            filled=float(raw.get("filled", 0)),
            remaining=float(raw.get("remaining", 0)),
            average_price=float(raw.get("average", 0) or raw.get("price", 0) or 0),
            status=raw.get("status", "unknown"),
            fee=float(fee_info.get("cost", 0) or 0),
            fee_currency=str(fee_info.get("currency", "USDT") or "USDT"),
            timestamp=int(raw.get("timestamp", 0) or 0),
            exchange=exchange,
            raw=raw,
        )

    @staticmethod
    def _ccxt_balance_to_info(raw: Dict[str, Any]) -> BalanceInfo:
        """Convert a CCXT balance dict to a standardized BalanceInfo.

        Args:
            raw: Raw CCXT balance dictionary.

        Returns:
            A BalanceInfo dataclass.
        """
        total_section = raw.get("total", {})
        free_section = raw.get("free", {})
        used_section = raw.get("used", {})

        # Aggregate USD-like totals
        usd_keys = ("USD", "USDT", "USDC", "BUSD")
        total_usd = sum(float(total_section.get(k, 0) or 0) for k in usd_keys)
        free_usd = sum(float(free_section.get(k, 0) or 0) for k in usd_keys)
        used_usd = sum(float(used_section.get(k, 0) or 0) for k in usd_keys)

        assets: Dict[str, Dict[str, float]] = {}
        for currency in total_section:
            t = float(total_section.get(currency, 0) or 0)
            if t > 0:
                assets[currency] = {
                    "total": t,
                    "free": float(free_section.get(currency, 0) or 0),
                    "used": float(used_section.get(currency, 0) or 0),
                }

        return BalanceInfo(
            total_usd=total_usd,
            free_usd=free_usd,
            used_usd=used_usd,
            assets=assets,
        )

    # -- AbstractExchange implementation -------------------------------------

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place an order on the live exchange with retry logic.

        Args:
            request: Standardized order request.

        Returns:
            Standardized order response.
        """
        async def _do():
            return await self._connector.place_order_async(
                symbol=request.symbol,
                side=request.side,
                order_type=request.order_type,
                amount=request.amount,
                price=request.price,
                params=request.params,
            )

        raw = await self._retry(_do, f"place_order({request.symbol})")
        return self._ccxt_order_to_response(raw, self._name)

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an order on the live exchange.

        Args:
            order_id: Exchange-assigned order identifier.
            symbol: Trading pair.

        Returns:
            True if cancellation succeeded.
        """
        try:
            await self._retry(
                lambda: self._connector.cancel_order_async(order_id, symbol),
                f"cancel_order({order_id})",
            )
            return True
        except Exception as exc:
            logger.error("LiveExchange cancel_order failed: %s", exc)
            return False

    async def get_order(self, order_id: str, symbol: str) -> OrderResponse:
        """Fetch current state of an order from the live exchange.

        Args:
            order_id: Exchange-assigned order identifier.
            symbol: Trading pair.

        Returns:
            Current order state.
        """
        raw = await self._retry(
            lambda: self._connector.get_order_status_async(order_id, symbol),
            f"get_order({order_id})",
        )
        return self._ccxt_order_to_response(raw, self._name)

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResponse]:
        """Fetch open orders from the live exchange.

        Args:
            symbol: Optional filter by trading pair.

        Returns:
            List of open orders.
        """
        # ExchangeConnector.get_open_orders is sync-only; run in thread.
        raw_list = await asyncio.to_thread(self._connector.get_open_orders, symbol)
        return [self._ccxt_order_to_response(o, self._name) for o in raw_list]

    async def get_balance(self) -> BalanceInfo:
        """Fetch account balance from the live exchange.

        Returns:
            Standardized balance information.
        """
        raw = await self._retry(
            lambda: self._connector.get_balance_async(),
            "get_balance",
        )
        return self._ccxt_balance_to_info(raw)

    async def get_ticker(self, symbol: str) -> TickerInfo:
        """Fetch current ticker from the live exchange.

        Args:
            symbol: Trading pair.

        Returns:
            Standardized ticker data.
        """
        raw = await self._retry(
            lambda: self._connector.get_ticker_async(symbol),
            f"get_ticker({symbol})",
        )
        return TickerInfo(
            symbol=raw.get("symbol", symbol),
            last=float(raw.get("last", 0) or 0),
            bid=float(raw.get("bid", 0) or 0),
            ask=float(raw.get("ask", 0) or 0),
            volume=float(raw.get("baseVolume", 0) or 0),
            timestamp=int(raw.get("timestamp", 0) or 0),
        )

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get open positions (futures/margin) from the live exchange.

        Returns:
            List of position dicts. Empty list for spot exchanges.
        """
        # Most spot exchanges don't have a positions endpoint.
        return []

    async def ping(self) -> float:
        """Check connectivity to the live exchange.

        Returns:
            Latency in ms, or -1.0 on failure.
        """
        try:
            latency = await asyncio.to_thread(self._connector.ping)
            return latency
        except Exception:
            return -1.0


# ---------------------------------------------------------------------------
# PaperExchange -- adapter over PaperTrader
# ---------------------------------------------------------------------------

class PaperExchange(AbstractExchange):
    """Paper trading exchange -- simulates fills with configurable realism.

    Adapts the existing PaperTrader to the AbstractExchange interface.
    All synchronous PaperTrader calls are run via asyncio.to_thread so that
    the caller always gets a consistent async API.
    """

    def __init__(self, paper_trader: Any) -> None:
        """Initialize with an existing PaperTrader instance.

        Args:
            paper_trader: A PaperTrader (from paper_trader.py).
        """
        self._trader = paper_trader

    # -- properties ----------------------------------------------------------

    @property
    def name(self) -> str:
        """Identifier for the paper exchange."""
        return "paper"

    @property
    def is_live(self) -> bool:
        """Paper exchange never trades real money."""
        return False

    # -- lifecycle -----------------------------------------------------------

    async def connect(self) -> None:
        """No-op for paper trading -- always ready."""
        logger.info("PaperExchange connected (simulated)")

    async def disconnect(self) -> None:
        """Persist balances on disconnect."""
        await asyncio.to_thread(self._trader.save_balances)
        logger.info("PaperExchange disconnected -- balances saved")

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _raw_order_to_response(raw: Dict[str, Any]) -> OrderResponse:
        """Convert a PaperTrader order dict to a standardized OrderResponse.

        Args:
            raw: Order dictionary from PaperTrader.

        Returns:
            An OrderResponse dataclass.
        """
        fee_info = raw.get("fee", {})
        if isinstance(fee_info, dict):
            fee_cost = float(fee_info.get("cost", 0) or 0)
            fee_currency = str(fee_info.get("currency", "USDT") or "USDT")
        else:
            fee_cost = 0.0
            fee_currency = "USDT"

        return OrderResponse(
            id=str(raw.get("id", "")),
            symbol=raw.get("symbol", ""),
            side=raw.get("side", ""),
            order_type=raw.get("type", ""),
            amount=float(raw.get("amount", 0)),
            filled=float(raw.get("filled", 0)),
            remaining=float(raw.get("amount", 0)) - float(raw.get("filled", 0)),
            average_price=float(raw.get("average", 0) or 0),
            status=raw.get("status", "unknown"),
            fee=fee_cost,
            fee_currency=fee_currency,
            timestamp=int(raw.get("timestamp", 0) or 0),
            exchange="paper",
            raw=raw,
        )

    # -- AbstractExchange implementation -------------------------------------

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place a simulated order via PaperTrader.

        Args:
            request: Standardized order request.

        Returns:
            Standardized order response with simulated fill.
        """
        raw = await asyncio.to_thread(
            self._trader.place_order,
            request.symbol,
            request.side,
            request.order_type,
            request.amount,
            request.price,
            request.params,
        )
        return self._raw_order_to_response(raw)

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel a simulated order.

        Args:
            order_id: Order identifier.
            symbol: Trading pair.

        Returns:
            Always True for paper trading (instant cancellation).
        """
        await asyncio.to_thread(self._trader.cancel_order, order_id, symbol)
        return True

    async def get_order(self, order_id: str, symbol: str) -> OrderResponse:
        """Fetch a simulated order's state.

        Args:
            order_id: Order identifier.
            symbol: Trading pair.

        Returns:
            Current order state.
        """
        raw = await asyncio.to_thread(self._trader.get_order_status, order_id, symbol)
        return self._raw_order_to_response(raw)

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResponse]:
        """Fetch open orders from PaperTrader.

        Paper trades fill instantly, so this always returns an empty list.

        Args:
            symbol: Ignored -- included for interface conformance.

        Returns:
            Empty list (paper orders fill immediately).
        """
        raw_list = await asyncio.to_thread(self._trader.get_open_orders, symbol)
        return [self._raw_order_to_response(o) for o in raw_list]

    async def get_balance(self) -> BalanceInfo:
        """Fetch simulated account balance.

        Returns:
            Standardized balance information.
        """
        raw = await asyncio.to_thread(self._trader.get_balance)
        total = raw.get("total", {})
        free = raw.get("free", {})
        used = raw.get("used", {})

        usd_keys = ("USD", "USDT", "USDC", "BUSD")
        total_usd = sum(float(total.get(k, 0) or 0) for k in usd_keys)
        free_usd = sum(float(free.get(k, 0) or 0) for k in usd_keys)
        used_usd = sum(float(used.get(k, 0) or 0) for k in usd_keys)

        assets: Dict[str, Dict[str, float]] = {}
        for currency in total:
            t = float(total.get(currency, 0) or 0)
            if t > 0:
                assets[currency] = {
                    "total": t,
                    "free": float(free.get(currency, 0) or 0),
                    "used": float(used.get(currency, 0) or 0),
                }

        return BalanceInfo(
            total_usd=total_usd,
            free_usd=free_usd,
            used_usd=used_usd,
            assets=assets,
        )

    async def get_ticker(self, symbol: str) -> TickerInfo:
        """Fetch simulated ticker from PaperTrader.

        Args:
            symbol: Trading pair.

        Returns:
            Standardized ticker data.
        """
        raw = await asyncio.to_thread(self._trader.get_ticker, symbol)
        return TickerInfo(
            symbol=raw.get("symbol", symbol),
            last=float(raw.get("last", 0) or 0),
            bid=float(raw.get("bid", 0) or 0),
            ask=float(raw.get("ask", 0) or 0),
            volume=0.0,  # PaperTrader doesn't simulate volume
            timestamp=int(raw.get("timestamp", 0) or 0),
        )

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Fetch open positions tracked by PaperTrader.

        Returns:
            List of position dicts with asset, side, size, entry, and P&L.
        """
        positions = await asyncio.to_thread(self._trader.get_positions)
        result: List[Dict[str, Any]] = []
        for pos in positions:
            result.append({
                "asset": pos.asset,
                "side": pos.side,
                "size": pos.size,
                "entry_price": pos.entry_price,
                "current_price": pos.current_price,
                "unrealized_pnl": pos.unrealized_pnl,
                "stop_loss": pos.stop_loss,
                "take_profit": pos.take_profit,
            })
        return result

    async def ping(self) -> float:
        """Simulated latency check.

        Returns:
            Near-zero latency (paper exchange is in-process).
        """
        return 0.1


# ---------------------------------------------------------------------------
# BacktestExchange -- new implementation with full internal accounting
# ---------------------------------------------------------------------------

class BacktestExchange(AbstractExchange):
    """Backtest exchange -- replays historical data with time progression.

    Uses the SAME OrderResponse / BalanceInfo / TickerInfo interface as live
    and paper modes, guaranteeing that strategy code works identically across
    all three execution contexts.

    Financial calculations (fees, slippage, P&L) use Decimal internally for
    precision, then convert to float at the interface boundary.
    """

    def __init__(
        self,
        initial_balance: float = 100_000.0,
        fee_pct: float = 0.1,
        slippage_pct: float = 0.05,
        quote_currency: str = "USDT",
    ) -> None:
        """Initialize the backtest exchange.

        Args:
            initial_balance: Starting cash in quote currency.
            fee_pct: Trading fee as a percentage (e.g. 0.1 = 0.1%).
            slippage_pct: Maximum slippage as a percentage (e.g. 0.05 = 0.05%).
            quote_currency: Quote currency for balances (default USDT).
        """
        self._initial_balance = Decimal(str(initial_balance))
        self._fee_pct = Decimal(str(fee_pct)) / Decimal("100")
        self._slippage_pct = Decimal(str(slippage_pct)) / Decimal("100")
        self._quote_currency = quote_currency

        # Internal state
        self._cash: Decimal = self._initial_balance
        self._holdings: Dict[str, Decimal] = {}   # base currency -> quantity
        self._orders: Dict[str, OrderResponse] = {}  # order_id -> response
        self._open_orders: Dict[str, OrderRequest] = {}  # pending limit/stop orders
        self._current_prices: Dict[str, float] = {}
        self._current_time: datetime = datetime.utcnow()
        self._order_counter: int = 0
        self._connected: bool = False

        # P&L tracking
        self._realized_pnl: Decimal = Decimal("0")
        self._peak_equity: Decimal = self._initial_balance
        self._max_drawdown: Decimal = Decimal("0")
        self._trade_count: int = 0
        self._winning_trades: int = 0
        self._total_fees: Decimal = Decimal("0")

    # -- properties ----------------------------------------------------------

    @property
    def name(self) -> str:
        """Identifier for the backtest exchange."""
        return "backtest"

    @property
    def is_live(self) -> bool:
        """Backtest exchange never trades real money."""
        return False

    # -- backtest control methods --------------------------------------------

    def set_prices(self, prices: Dict[str, float]) -> None:
        """Set current market prices for this backtest step.

        Also triggers evaluation of pending limit/stop orders.

        Args:
            prices: Mapping of symbol to current price.
        """
        self._current_prices = prices
        self._try_fill_pending_orders()

    def set_time(self, time: datetime) -> None:
        """Advance the backtest clock.

        Args:
            time: The new current time.
        """
        self._current_time = time

    def get_equity(self) -> float:
        """Calculate total equity (cash + marked-to-market holdings).

        Returns:
            Total portfolio value in quote currency.
        """
        equity = self._cash
        for symbol, qty in self._holdings.items():
            price = self._current_prices.get(symbol, 0.0)
            equity += qty * Decimal(str(price))
        return float(equity.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def get_stats(self) -> Dict[str, Any]:
        """Return backtest performance statistics.

        Returns:
            Dict with realized_pnl, total_return_pct, max_drawdown_pct,
            trade_count, win_rate, and total_fees.
        """
        equity = Decimal(str(self.get_equity()))
        total_return = (equity - self._initial_balance) / self._initial_balance * 100
        win_rate = (
            float(self._winning_trades) / self._trade_count * 100
            if self._trade_count > 0
            else 0.0
        )
        return {
            "initial_balance": float(self._initial_balance),
            "final_equity": float(equity),
            "realized_pnl": float(self._realized_pnl),
            "total_return_pct": float(total_return.quantize(Decimal("0.01"))),
            "max_drawdown_pct": float(self._max_drawdown.quantize(Decimal("0.01"))),
            "trade_count": self._trade_count,
            "win_rate": round(win_rate, 2),
            "total_fees": float(self._total_fees.quantize(Decimal("0.01"))),
        }

    # -- internal helpers ----------------------------------------------------

    def _next_order_id(self) -> str:
        """Generate a sequential backtest order ID.

        Returns:
            A unique order identifier string.
        """
        self._order_counter += 1
        return f"bt-{self._order_counter:06d}"

    def _apply_slippage(self, price: float, side: str) -> Decimal:
        """Apply worst-case slippage to a price.

        Buys slip up; sells slip down.

        Args:
            price: The base price.
            side: "buy" or "sell".

        Returns:
            Price after slippage as Decimal.
        """
        p = Decimal(str(price))
        if side == "buy":
            return p * (Decimal("1") + self._slippage_pct)
        else:
            return p * (Decimal("1") - self._slippage_pct)

    def _compute_fee(self, notional: Decimal) -> Decimal:
        """Compute the fee for a given notional value.

        Args:
            notional: Trade notional in quote currency.

        Returns:
            Fee amount as Decimal.
        """
        return (notional * self._fee_pct).quantize(
            Decimal("0.00000001"), rounding=ROUND_HALF_UP
        )

    def _base_currency(self, symbol: str) -> str:
        """Extract the base currency from a trading pair.

        Args:
            symbol: e.g. "BTC/USDT".

        Returns:
            Base currency string (e.g. "BTC").
        """
        return symbol.split("/")[0] if "/" in symbol else symbol

    def _execute_fill(self, request: OrderRequest, fill_price: Decimal) -> OrderResponse:
        """Execute an order fill at the given price, updating internal state.

        Args:
            request: The order request to fill.
            fill_price: The price at which to fill (after slippage).

        Returns:
            OrderResponse reflecting the fill.
        """
        order_id = self._next_order_id()
        amount = Decimal(str(request.amount))
        notional = amount * fill_price
        fee = self._compute_fee(notional)
        self._total_fees += fee
        base = self._base_currency(request.symbol)

        if request.side == "buy":
            total_cost = notional + fee
            if self._cash < total_cost:
                logger.warning(
                    "BacktestExchange: insufficient cash for %s %s "
                    "(need %s, have %s)",
                    request.side, request.symbol, total_cost, self._cash,
                )
                return OrderResponse(
                    id=order_id,
                    symbol=request.symbol,
                    side=request.side,
                    order_type=request.order_type,
                    amount=float(amount),
                    filled=0.0,
                    remaining=float(amount),
                    average_price=0.0,
                    status="rejected",
                    fee=0.0,
                    fee_currency=self._quote_currency,
                    timestamp=int(self._current_time.timestamp() * 1000),
                    exchange="backtest",
                )
            self._cash -= total_cost
            self._holdings[base] = self._holdings.get(base, Decimal("0")) + amount

        else:  # sell
            current_holding = self._holdings.get(base, Decimal("0"))
            if current_holding < amount:
                logger.warning(
                    "BacktestExchange: insufficient %s to sell "
                    "(need %s, have %s)",
                    base, amount, current_holding,
                )
                return OrderResponse(
                    id=order_id,
                    symbol=request.symbol,
                    side=request.side,
                    order_type=request.order_type,
                    amount=float(amount),
                    filled=0.0,
                    remaining=float(amount),
                    average_price=0.0,
                    status="rejected",
                    fee=0.0,
                    fee_currency=self._quote_currency,
                    timestamp=int(self._current_time.timestamp() * 1000),
                    exchange="backtest",
                )
            self._holdings[base] = current_holding - amount
            if self._holdings[base] == Decimal("0"):
                del self._holdings[base]
            self._cash += notional - fee

        # Track P&L and drawdown
        self._trade_count += 1
        equity = Decimal(str(self.get_equity()))
        if equity > self._peak_equity:
            self._peak_equity = equity
        drawdown = (
            (self._peak_equity - equity) / self._peak_equity * 100
            if self._peak_equity > 0
            else Decimal("0")
        )
        if drawdown > self._max_drawdown:
            self._max_drawdown = drawdown

        # Simplified win detection: sell proceeds > initial cost implies win
        if request.side == "sell":
            pnl = notional - fee  # gross sell proceeds minus fee
            # We count as winning if equity is above initial
            if equity >= self._initial_balance:
                self._winning_trades += 1

        response = OrderResponse(
            id=order_id,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            amount=float(amount),
            filled=float(amount),
            remaining=0.0,
            average_price=float(fill_price.quantize(Decimal("0.00000001"))),
            status="closed",
            fee=float(fee),
            fee_currency=self._quote_currency,
            timestamp=int(self._current_time.timestamp() * 1000),
            exchange="backtest",
        )
        self._orders[order_id] = response
        return response

    def _try_fill_pending_orders(self) -> None:
        """Evaluate and fill any pending limit/stop orders against current prices."""
        filled_ids: List[str] = []
        for oid, request in list(self._open_orders.items()):
            price = self._current_prices.get(request.symbol)
            if price is None:
                continue

            should_fill = False

            if request.order_type == "limit" and request.price is not None:
                if request.side == "buy" and price <= request.price:
                    should_fill = True
                elif request.side == "sell" and price >= request.price:
                    should_fill = True

            elif request.order_type == "stop" and request.stop_price is not None:
                if request.side == "buy" and price >= request.stop_price:
                    should_fill = True
                elif request.side == "sell" and price <= request.stop_price:
                    should_fill = True

            if should_fill:
                fill_price = self._apply_slippage(price, request.side)
                response = self._execute_fill(request, fill_price)
                # Overwrite the existing open order record
                self._orders[oid] = response
                filled_ids.append(oid)

        for oid in filled_ids:
            del self._open_orders[oid]

    # -- lifecycle -----------------------------------------------------------

    async def connect(self) -> None:
        """Mark the backtest exchange as connected."""
        self._connected = True
        logger.info("BacktestExchange connected (initial balance: %s)", self._initial_balance)

    async def disconnect(self) -> None:
        """Mark the backtest exchange as disconnected and log final stats."""
        self._connected = False
        stats = self.get_stats()
        logger.info("BacktestExchange disconnected -- stats: %s", stats)

    # -- AbstractExchange implementation -------------------------------------

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place an order in the backtest.

        Market orders fill immediately at the current price (with slippage).
        Limit and stop orders are queued and evaluated on each set_prices call.

        Args:
            request: Standardized order request.

        Returns:
            Standardized order response.
        """
        # Market orders fill immediately
        if request.order_type == "market":
            price = self._current_prices.get(request.symbol)
            if price is None:
                return OrderResponse(
                    id=self._next_order_id(),
                    symbol=request.symbol,
                    side=request.side,
                    order_type=request.order_type,
                    amount=request.amount,
                    filled=0.0,
                    remaining=request.amount,
                    average_price=0.0,
                    status="rejected",
                    exchange="backtest",
                    timestamp=int(self._current_time.timestamp() * 1000),
                    raw={"error": f"No price available for {request.symbol}"},
                )
            fill_price = self._apply_slippage(price, request.side)
            return self._execute_fill(request, fill_price)

        # Limit / stop / trailing_stop orders are queued
        order_id = self._next_order_id()
        self._open_orders[order_id] = request

        response = OrderResponse(
            id=order_id,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            amount=request.amount,
            filled=0.0,
            remaining=request.amount,
            average_price=0.0,
            status="open",
            exchange="backtest",
            timestamp=int(self._current_time.timestamp() * 1000),
        )
        self._orders[order_id] = response
        return response

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel a pending backtest order.

        Args:
            order_id: Order identifier.
            symbol: Trading pair (unused, included for interface conformance).

        Returns:
            True if the order was found and cancelled.
        """
        if order_id in self._open_orders:
            del self._open_orders[order_id]
            if order_id in self._orders:
                old = self._orders[order_id]
                self._orders[order_id] = OrderResponse(
                    id=old.id,
                    symbol=old.symbol,
                    side=old.side,
                    order_type=old.order_type,
                    amount=old.amount,
                    filled=old.filled,
                    remaining=old.remaining,
                    average_price=old.average_price,
                    status="cancelled",
                    fee=old.fee,
                    fee_currency=old.fee_currency,
                    timestamp=old.timestamp,
                    exchange="backtest",
                )
            return True
        return False

    async def get_order(self, order_id: str, symbol: str) -> OrderResponse:
        """Get the state of a backtest order.

        Args:
            order_id: Order identifier.
            symbol: Trading pair (unused, included for interface conformance).

        Returns:
            Order state, or a synthetic 'unknown' response if not found.
        """
        if order_id in self._orders:
            return self._orders[order_id]
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
            exchange="backtest",
        )

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResponse]:
        """Get all pending (unfilled) backtest orders.

        Args:
            symbol: Optional filter by trading pair.

        Returns:
            List of open orders.
        """
        results: List[OrderResponse] = []
        for oid in self._open_orders:
            resp = self._orders.get(oid)
            if resp and (symbol is None or resp.symbol == symbol):
                results.append(resp)
        return results

    async def get_balance(self) -> BalanceInfo:
        """Get the backtest account balance.

        Returns:
            Standardized balance with cash and holdings valued at current prices.
        """
        cash_float = float(self._cash.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        assets: Dict[str, Dict[str, float]] = {}
        # Quote currency
        if self._cash > 0:
            assets[self._quote_currency] = {
                "total": cash_float,
                "free": cash_float,
                "used": 0.0,
            }
        # Base currencies
        for base, qty in self._holdings.items():
            q = float(qty.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP))
            if q > 0:
                assets[base] = {"total": q, "free": q, "used": 0.0}

        return BalanceInfo(
            total_usd=self.get_equity(),
            free_usd=cash_float,
            used_usd=self.get_equity() - cash_float,
            assets=assets,
        )

    async def get_ticker(self, symbol: str) -> TickerInfo:
        """Get the current ticker for a symbol in the backtest.

        Args:
            symbol: Trading pair.

        Returns:
            Ticker built from the current backtest price.

        Raises:
            ValueError: If no price has been set for the symbol.
        """
        price = self._current_prices.get(symbol)
        if price is None:
            raise ValueError(
                f"No backtest price set for {symbol}. Call set_prices() first."
            )
        spread = Decimal(str(price)) * Decimal("0.0005")
        return TickerInfo(
            symbol=symbol,
            last=price,
            bid=float(Decimal(str(price)) - spread / 2),
            ask=float(Decimal(str(price)) + spread / 2),
            volume=0.0,
            timestamp=int(self._current_time.timestamp() * 1000),
        )

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get open positions in the backtest.

        Returns:
            List of position dicts with base currency, quantity, and value.
        """
        results: List[Dict[str, Any]] = []
        for base, qty in self._holdings.items():
            price = self._current_prices.get(f"{base}/{self._quote_currency}", 0.0)
            q = float(qty)
            results.append({
                "asset": base,
                "side": "long",
                "size": q,
                "entry_price": 0.0,  # not tracked per-trade in simple model
                "current_price": price,
                "unrealized_pnl": 0.0,  # would need entry tracking
                "value": q * price,
            })
        return results

    async def ping(self) -> float:
        """Backtest ping -- always instant.

        Returns:
            0.0 ms (no network latency in backtest).
        """
        return 0.0


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def create_exchange(mode: str, config: Dict[str, Any]) -> AbstractExchange:
    """Factory function to create the appropriate exchange implementation.

    Args:
        mode: One of "live", "paper", or "backtest".
        config: Full system configuration dictionary. Expected keys vary by mode:
            - live:     "exchange_name", "api_key", "secret", "sandbox" (bool),
                        "extra_params" (dict, optional)
            - paper:    "initial_balance" (float), "slippage_pct" (float),
                        "fee_pct" (float), "db_path" (str, optional)
            - backtest: "initial_balance" (float), "fee_pct" (float),
                        "slippage_pct" (float), "quote_currency" (str, optional)

    Returns:
        An AbstractExchange instance ready to use.

    Raises:
        ValueError: If mode is not recognized.
    """
    if mode == "live":
        from src.execution.exchange_connector import ExchangeConnector

        connector = ExchangeConnector(
            name=config.get("exchange_name", "binance"),
            api_key=config.get("api_key", ""),
            secret=config.get("secret", ""),
            sandbox=config.get("sandbox", True),
            extra_params=config.get("extra_params"),
        )
        return LiveExchange(connector)

    elif mode == "paper":
        from src.execution.paper_trader import PaperTrader

        trader = PaperTrader(
            initial_balance=config.get("initial_balance", 100_000.0),
            slippage_pct=config.get("slippage_pct", 0.05),
            fee_pct=config.get("fee_pct", 0.1),
            db_path=config.get("db_path", "data/paper_trades.db"),
        )
        return PaperExchange(trader)

    elif mode == "backtest":
        return BacktestExchange(
            initial_balance=config.get("initial_balance", 100_000.0),
            fee_pct=config.get("fee_pct", 0.1),
            slippage_pct=config.get("slippage_pct", 0.05),
            quote_currency=config.get("quote_currency", "USDT"),
        )

    elif mode == "hyperliquid":
        import os
        from src.execution.hyperliquid_exchange import HyperliquidExchange

        hl_config = config.get("hyperliquid", {})
        address = hl_config.get("user_address", os.environ.get("HYPERLIQUID_ADDRESS", ""))
        private_key = hl_config.get("private_key", os.environ.get("HYPERLIQUID_PRIVATE_KEY", ""))
        testnet = hl_config.get("testnet", False)
        return HyperliquidExchange(address, private_key, testnet)

    else:
        raise ValueError(
            f"Unknown exchange mode: '{mode}'. "
            f"Expected 'live', 'paper', 'backtest', or 'hyperliquid'."
        )
