"""Paper trading: simulated execution engine for testing without real money."""

import logging
import random
import sqlite3
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.utils.types import AssetClass, OrderType, Position, TradeResult, TradeStatus

logger = logging.getLogger(__name__)


def estimate_slippage_bps(
    symbol: str,
    trade_value: float = 0.0,
    current_atr: float = 0.0,
    historical_avg_atr: float = 0.0,
    avg_daily_volume: float = 0.0,
) -> float:
    """Estimate realistic slippage in basis points using a volatility-scaled model.

    Base slippage (bps) = base_rate * volatility_multiplier * size_multiplier
      * volatility_multiplier = current_atr / historical_avg_atr (clamped 0.5–3.0)
      * size_multiplier      = trade_value / avg_daily_volume * 10 (floor 1.0)
      * noise                = uniform jitter +/-20%

    Args:
        symbol: Trading pair, e.g. "BTC/USDT".
        trade_value: Notional value of the order in quote currency.
        current_atr: Current ATR (or realized volatility measure).
        historical_avg_atr: Long-run average ATR for the same asset.
        avg_daily_volume: Average daily *notional* volume (quote currency).

    Returns:
        Estimated slippage in basis points (bps).
    """
    sym_upper = symbol.upper()

    # Asset-class base rates (bps) reflecting typical spread/depth
    if "BTC" in sym_upper:
        base_rate = 3.0
    elif "ETH" in sym_upper:
        base_rate = 4.0
    elif any(t in sym_upper for t in ("SOL", "BNB", "XRP", "ADA", "AVAX", "DOT", "DOGE", "MATIC")):
        base_rate = 5.0
    else:
        base_rate = 2.0  # Forex / large-cap equity default

    # Volatility multiplier
    if current_atr > 0 and historical_avg_atr > 0:
        vol_mult = max(0.5, min(3.0, current_atr / historical_avg_atr))
    else:
        vol_mult = 1.0

    # Size-impact multiplier
    if avg_daily_volume > 0 and trade_value > 0:
        size_mult = max(1.0, trade_value / avg_daily_volume * 10.0)
    else:
        size_mult = 1.0

    # Random noise (+/- 20%)
    noise = 1.0 + (random.random() - 0.5) * 0.4

    return base_rate * vol_mult * size_mult * noise


class PaperTrader:
    """Simulated exchange connector for paper trading.

    Implements the same interface as ExchangeConnector so it can be
    swapped in transparently. Tracks virtual balances, positions, and P&L.
    """

    def __init__(self, initial_balance: float = 100_000.0,
                 slippage_pct: float = 0.05,
                 fee_pct: float = 0.1,
                 db_path: str = "data/paper_trades.db"):
        self.name = "paper"
        self.slippage_pct = slippage_pct / 100.0
        self.fee_pct = fee_pct / 100.0
        self._balances: Dict[str, float] = {"USD": initial_balance, "USDT": initial_balance}
        self._positions: Dict[str, Position] = {}
        self._orders: List[Dict[str, Any]] = []
        self._prices: Dict[str, float] = {}  # symbol -> simulated current price
        self._trade_history: List[Dict[str, Any]] = []
        self.db_path = db_path

        # Volatility / liquidity context for realistic slippage estimation.
        # Callers should populate these via ``set_market_context()`` when data
        # is available; otherwise the slippage model falls back to asset-class
        # base rates with vol_mult=1 and size_mult=1.
        self._atr_current: Dict[str, float] = {}
        self._atr_historical: Dict[str, float] = {}
        self._avg_daily_volume: Dict[str, float] = {}

        self._init_db()

    def _init_db(self) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    requested_price REAL,
                    fill_price REAL NOT NULL,
                    slippage REAL NOT NULL,
                    fees REAL NOT NULL,
                    status TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_balances (
                    currency TEXT PRIMARY KEY,
                    amount REAL NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Could not initialize paper trade DB: %s", e)

    def set_price(self, symbol: str, price: float) -> None:
        """Set the simulated current price for a symbol."""
        self._prices[symbol] = price

    def set_market_context(
        self,
        symbol: str,
        current_atr: float = 0.0,
        historical_avg_atr: float = 0.0,
        avg_daily_volume: float = 0.0,
    ) -> None:
        """Provide volatility / liquidity context for slippage estimation.

        Args:
            symbol: Trading pair, e.g. "BTC/USDT".
            current_atr: Most recent ATR value.
            historical_avg_atr: Long-run average ATR.
            avg_daily_volume: Average daily notional volume (quote currency).
        """
        if current_atr > 0:
            self._atr_current[symbol] = current_atr
        if historical_avg_atr > 0:
            self._atr_historical[symbol] = historical_avg_atr
        if avg_daily_volume > 0:
            self._avg_daily_volume[symbol] = avg_daily_volume

    def _get_price(self, symbol: str) -> float:
        price = self._prices.get(symbol)
        if price is None:
            raise ValueError(f"No simulated price set for {symbol}. Call set_price() first.")
        return price

    def _simulate_fill_price(self, symbol: str, side: str,
                             order_type: str,
                             amount: float = 0.0) -> float:
        """Calculate a realistic fill price with volatility-scaled slippage.

        Uses ``estimate_slippage_bps`` for market orders, which accounts for
        asset type, volatility (ATR), and position size vs liquidity.
        Limit orders still fill at the requested price (no slippage).
        """
        base_price = self._get_price(symbol)
        if order_type == "market":
            trade_value = amount * base_price if amount > 0 else 0.0
            slip_bps = estimate_slippage_bps(
                symbol=symbol,
                trade_value=trade_value,
                current_atr=self._atr_current.get(symbol, 0.0),
                historical_avg_atr=self._atr_historical.get(symbol, 0.0),
                avg_daily_volume=self._avg_daily_volume.get(symbol, 0.0),
            )
            slip_frac = slip_bps / 10_000.0
            if side == "buy":
                return base_price * (1 + slip_frac)
            else:
                return base_price * (1 - slip_frac)
        # Limit orders fill at the requested price (no slippage)
        return base_price

    def _calculate_fees(self, amount: float, price: float) -> float:
        return amount * price * self.fee_pct

    def get_balance(self) -> Dict[str, Any]:
        return {
            "total": self._balances.copy(),
            "free": self._balances.copy(),
            "used": {k: 0.0 for k in self._balances},
        }

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        price = self._get_price(symbol)
        spread = price * 0.0005  # 0.05% simulated spread
        return {
            "symbol": symbol,
            "bid": price - spread / 2,
            "ask": price + spread / 2,
            "last": price,
            "timestamp": int(time.time() * 1000),
        }

    def place_order(self, symbol: str, side: str, order_type: str,
                    amount: float, price: Optional[float] = None,
                    params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Simulate placing an order with realistic fills."""
        order_id = str(uuid.uuid4())[:12]

        fill_price = self._simulate_fill_price(symbol, side, order_type, amount=amount)
        fees = self._calculate_fees(amount, fill_price)
        slippage = 0.0
        if price and price > 0:
            slippage = abs(fill_price - price) / price * 100

        # Update virtual balances
        quote = symbol.split("/")[1] if "/" in symbol else "USD"
        cost = amount * fill_price + fees

        if side == "buy":
            if self._balances.get(quote, 0) < cost:
                logger.warning("Paper trade: insufficient balance for %s %s (need %.2f, have %.2f)",
                               side, symbol, cost, self._balances.get(quote, 0))
                return {
                    "id": order_id, "status": "rejected",
                    "info": "Insufficient paper balance",
                }
            self._balances[quote] = self._balances.get(quote, 0) - cost
            base = symbol.split("/")[0] if "/" in symbol else symbol
            self._balances[base] = self._balances.get(base, 0) + amount
        else:
            base = symbol.split("/")[0] if "/" in symbol else symbol
            if self._balances.get(base, 0) < amount:
                logger.warning("Paper trade: insufficient %s balance", base)
                return {
                    "id": order_id, "status": "rejected",
                    "info": "Insufficient paper balance",
                }
            self._balances[base] = self._balances.get(base, 0) - amount
            self._balances[quote] = self._balances.get(quote, 0) + (amount * fill_price - fees)

        order_record = {
            "id": order_id,
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "amount": amount,
            "price": price,
            "filled": amount,
            "average": fill_price,
            "status": "closed",
            "fee": {"cost": fees, "currency": quote},
            "timestamp": int(time.time() * 1000),
            "datetime": datetime.utcnow().isoformat(),
        }
        self._orders.append(order_record)

        trade_record = {
            "id": order_id,
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "amount": amount,
            "requested_price": price or fill_price,
            "fill_price": fill_price,
            "slippage": slippage,
            "fees": fees,
            "status": "filled",
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._trade_history.append(trade_record)
        self._save_trade(trade_record)

        logger.info("Paper trade executed: %s %s %.6f @ %.4f (slip=%.4f%%, fee=%.4f)",
                     side, symbol, amount, fill_price, slippage, fees)
        return order_record

    def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        return {"id": order_id, "status": "cancelled"}

    def get_order_status(self, order_id: str, symbol: str) -> Dict[str, Any]:
        for order in self._orders:
            if order["id"] == order_id:
                return order
        return {"id": order_id, "status": "unknown"}

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        # Paper trades fill instantly, so there are no open orders
        return []

    def ping(self) -> float:
        return 0.1  # Simulated latency

    # --- Position tracking ---

    def open_position(self, asset: str, asset_class: AssetClass,
                      side: str, entry_price: float, size: float,
                      stop_loss: float, take_profit: float,
                      order_id: str = "", strategy: str = "") -> Position:
        pos = Position(
            asset=asset, asset_class=asset_class, side=side,
            entry_price=entry_price, current_price=entry_price,
            size=size, stop_loss=stop_loss, take_profit=take_profit,
            order_id=order_id, strategy=strategy,
        )
        self._positions[asset] = pos
        return pos

    def close_position(self, asset: str, exit_price: float) -> Optional[float]:
        """Close a position and return realized P&L."""
        pos = self._positions.pop(asset, None)
        if pos is None:
            return None
        if pos.side == "LONG":
            pnl = (exit_price - pos.entry_price) * pos.size
        else:
            pnl = (pos.entry_price - exit_price) * pos.size
        return pnl

    def get_positions(self) -> List[Position]:
        return list(self._positions.values())

    def get_total_value(self) -> float:
        """Calculate total portfolio value (cash + positions)."""
        cash = self._balances.get("USD", 0) + self._balances.get("USDT", 0)
        positions_value = sum(
            p.current_price * p.size for p in self._positions.values()
        )
        return cash + positions_value

    def get_trade_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self._trade_history[-limit:]

    # --- Persistence ---

    def _save_trade(self, trade: Dict[str, Any]) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """INSERT OR REPLACE INTO paper_trades
                   (id, symbol, side, order_type, amount, requested_price,
                    fill_price, slippage, fees, status, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (trade["id"], trade["symbol"], trade["side"], trade["order_type"],
                 trade["amount"], trade["requested_price"], trade["fill_price"],
                 trade["slippage"], trade["fees"], trade["status"], trade["timestamp"]),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Could not save paper trade: %s", e)

    def save_balances(self) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            now = datetime.utcnow().isoformat()
            for currency, amount in self._balances.items():
                conn.execute(
                    """INSERT OR REPLACE INTO paper_balances (currency, amount, updated_at)
                       VALUES (?, ?, ?)""",
                    (currency, amount, now),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Could not save paper balances: %s", e)
