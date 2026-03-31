#!/usr/bin/env python3
"""AIFred Trading System — End-to-End Paper Trading Validation.

Connects to Hyperliquid testnet for real market data, runs the full
signal pipeline (technical -> sentiment -> on-chain -> signal fusion ->
risk check), and executes paper trades.  All positions and P&L are
tracked in-memory with periodic summary reports.

Usage:
    python paper_trading.py
    python paper_trading.py --assets ETH,BTC,SOL --interval 30 --duration 120
    python paper_trading.py --report-interval 5 --portfolio-value 50000
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# Ensure the project root is on sys.path so ``src.*`` imports work.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from src.config import load_config
from src.orchestrator import Orchestrator
from src.execution.hyperliquid_connector import HyperliquidConnector
from src.utils.types import (
    AssetClass,
    Direction,
    OrderType,
    Position,
    Signal,
    TradeProposal,
    TradeResult,
    TradeStatus,
)

logger = logging.getLogger("aifred.paper")


# ---------------------------------------------------------------------------
# Paper trade tracker
# ---------------------------------------------------------------------------

@dataclass
class PaperTrade:
    """Record of a single paper trade."""
    id: str
    asset: str
    side: str           # "LONG" or "SHORT"
    entry_price: float
    size: float
    value_usd: float
    stop_loss: float
    take_profit: float
    entry_time: datetime
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    pnl: float = 0.0
    status: str = "open"  # "open", "closed_tp", "closed_sl", "closed_manual"
    signal_confidence: float = 0.0
    signal_source: str = ""


@dataclass
class PaperPortfolio:
    """In-memory paper portfolio tracker."""
    initial_balance: float = 10_000.0
    cash: float = 10_000.0
    positions: Dict[str, PaperTrade] = field(default_factory=dict)
    closed_trades: List[PaperTrade] = field(default_factory=list)
    trade_counter: int = 0

    # Running stats
    total_pnl: float = 0.0
    peak_equity: float = 10_000.0
    max_drawdown: float = 0.0
    winning_trades: int = 0
    losing_trades: int = 0

    @property
    def equity(self) -> float:
        unrealized = sum(t.pnl for t in self.positions.values())
        return self.cash + unrealized

    @property
    def win_rate(self) -> float:
        total = self.winning_trades + self.losing_trades
        return (self.winning_trades / total * 100) if total > 0 else 0.0

    @property
    def total_trades(self) -> int:
        return self.winning_trades + self.losing_trades

    def open_position(
        self,
        asset: str,
        side: str,
        price: float,
        size: float,
        stop_loss: float,
        take_profit: float,
        confidence: float = 0.0,
        source: str = "",
    ) -> Optional[PaperTrade]:
        """Open a new paper position."""
        if asset in self.positions:
            logger.warning("Already have an open position in %s, skipping", asset)
            return None

        value = size * price
        if value > self.cash:
            logger.warning(
                "Insufficient cash for %s: need $%.2f, have $%.2f",
                asset, value, self.cash,
            )
            return None

        self.trade_counter += 1
        trade = PaperTrade(
            id=f"PT-{self.trade_counter:04d}",
            asset=asset,
            side=side,
            entry_price=price,
            size=size,
            value_usd=value,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_time=datetime.utcnow(),
            signal_confidence=confidence,
            signal_source=source,
        )
        self.positions[asset] = trade
        self.cash -= value
        logger.info(
            "PAPER OPEN: %s %s %.6f @ $%.2f ($%.2f) | SL=$%.2f TP=$%.2f | conf=%.1f%%",
            side, asset, size, price, value, stop_loss, take_profit, confidence,
        )
        return trade

    def close_position(
        self,
        asset: str,
        exit_price: float,
        reason: str = "manual",
    ) -> Optional[PaperTrade]:
        """Close an open paper position."""
        trade = self.positions.pop(asset, None)
        if trade is None:
            return None

        trade.exit_price = exit_price
        trade.exit_time = datetime.utcnow()
        trade.status = f"closed_{reason}"

        if trade.side == "LONG":
            trade.pnl = (exit_price - trade.entry_price) * trade.size
        else:
            trade.pnl = (trade.entry_price - exit_price) * trade.size

        self.cash += trade.value_usd + trade.pnl
        self.total_pnl += trade.pnl

        if trade.pnl >= 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1

        # Update peak / drawdown
        equity = self.equity
        if equity > self.peak_equity:
            self.peak_equity = equity
        dd = (self.peak_equity - equity) / self.peak_equity * 100
        if dd > self.max_drawdown:
            self.max_drawdown = dd

        self.closed_trades.append(trade)
        logger.info(
            "PAPER CLOSE: %s %s @ $%.2f (entry $%.2f) | PnL=$%.2f | reason=%s",
            trade.side, asset, exit_price, trade.entry_price, trade.pnl, reason,
        )
        return trade

    def update_unrealized_pnl(self, prices: Dict[str, float]) -> None:
        """Update unrealized P&L for open positions."""
        for asset, trade in self.positions.items():
            price = prices.get(asset)
            if price is None:
                continue
            if trade.side == "LONG":
                trade.pnl = (price - trade.entry_price) * trade.size
            else:
                trade.pnl = (trade.entry_price - price) * trade.size

    def check_stops(self, prices: Dict[str, float]) -> List[str]:
        """Check stop-loss and take-profit for all open positions.

        Returns list of assets that were closed.
        """
        closed = []
        for asset in list(self.positions.keys()):
            trade = self.positions[asset]
            price = prices.get(asset)
            if price is None:
                continue

            if trade.side == "LONG":
                if price <= trade.stop_loss:
                    self.close_position(asset, trade.stop_loss, reason="sl")
                    closed.append(asset)
                elif price >= trade.take_profit:
                    self.close_position(asset, trade.take_profit, reason="tp")
                    closed.append(asset)
            else:  # SHORT
                if price >= trade.stop_loss:
                    self.close_position(asset, trade.stop_loss, reason="sl")
                    closed.append(asset)
                elif price <= trade.take_profit:
                    self.close_position(asset, trade.take_profit, reason="tp")
                    closed.append(asset)
        return closed


# ---------------------------------------------------------------------------
# Hyperliquid data bridge
# ---------------------------------------------------------------------------

async def fetch_ohlcv_from_hl(
    connector: HyperliquidConnector,
    asset: str,
    interval: str = "1h",
    limit: int = 200,
) -> pd.DataFrame:
    """Fetch OHLCV data from Hyperliquid and return a DataFrame.

    The DataFrame has a DatetimeIndex and columns:
    open, high, low, close, volume.
    """
    coin = asset.split("/")[0].upper()
    candles = await connector.get_ohlcv(coin, interval=interval, limit=limit)
    if not candles:
        return pd.DataFrame()

    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    df = df.astype(float)
    return df


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------

def print_summary(
    portfolio: PaperPortfolio,
    prices: Dict[str, float],
    scan_count: int,
    elapsed_minutes: float,
    final: bool = False,
) -> None:
    """Print a formatted summary report."""
    header = "FINAL PAPER TRADING REPORT" if final else "PAPER TRADING STATUS"
    equity = portfolio.equity
    pnl_pct = (equity - portfolio.initial_balance) / portfolio.initial_balance * 100

    lines = [
        "",
        "=" * 70,
        f"  {header}",
        "=" * 70,
        f"  Runtime:          {elapsed_minutes:.1f} minutes ({scan_count} scans)",
        f"  Initial Balance:  ${portfolio.initial_balance:,.2f}",
        f"  Current Equity:   ${equity:,.2f}  ({pnl_pct:+.2f}%)",
        f"  Cash Available:   ${portfolio.cash:,.2f}",
        f"  Total P&L:        ${portfolio.total_pnl:,.2f}",
        f"  Peak Equity:      ${portfolio.peak_equity:,.2f}",
        f"  Max Drawdown:     {portfolio.max_drawdown:.2f}%",
        f"  Total Trades:     {portfolio.total_trades}",
        f"  Win Rate:         {portfolio.win_rate:.1f}%",
        f"  Winning/Losing:   {portfolio.winning_trades}/{portfolio.losing_trades}",
    ]

    if portfolio.positions:
        lines.append("")
        lines.append("  --- Open Positions ---")
        for asset, trade in portfolio.positions.items():
            price = prices.get(asset, 0.0)
            pnl_str = f"${trade.pnl:+,.2f}" if trade.pnl != 0 else "$0.00"
            lines.append(
                f"  {trade.side:5s} {asset:12s}  "
                f"entry=${trade.entry_price:,.2f}  now=${price:,.2f}  "
                f"PnL={pnl_str}  SL=${trade.stop_loss:,.2f}  TP=${trade.take_profit:,.2f}"
            )

    if final and portfolio.closed_trades:
        lines.append("")
        lines.append("  --- Trade History ---")
        for t in portfolio.closed_trades[-20:]:  # Last 20
            lines.append(
                f"  {t.id} {t.side:5s} {t.asset:12s}  "
                f"entry=${t.entry_price:,.2f}  exit=${t.exit_price:,.2f}  "
                f"PnL=${t.pnl:+,.2f}  status={t.status}  conf={t.signal_confidence:.0f}%"
            )
        if len(portfolio.closed_trades) > 20:
            lines.append(f"  ... and {len(portfolio.closed_trades) - 20} more trades")

    lines.append("=" * 70)
    lines.append("")

    report = "\n".join(lines)
    print(report)
    logger.info(report)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def run_paper_trading(args: argparse.Namespace) -> None:
    """Main paper trading loop."""

    # --- Setup Logging ---
    log_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(log_fmt)
    root_logger.addHandler(console_handler)

    file_handler = logging.FileHandler("paper_trading.log", mode="a")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_fmt)
    root_logger.addHandler(file_handler)

    # Suppress noisy third-party loggers
    for noisy in ("urllib3", "httpx", "xgboost", "aiohttp"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # --- Parse asset list ---
    assets = [a.strip().upper() for a in args.assets.split(",") if a.strip()]
    # Normalize to /USDT pairs for the orchestrator
    asset_pairs = []
    for a in assets:
        if "/" not in a:
            asset_pairs.append(f"{a}/USDT")
        else:
            asset_pairs.append(a)

    # --- Load config ---
    try:
        config = load_config()
    except Exception:
        config = {}

    # Override config for paper mode
    config.setdefault("execution", {})["mode"] = "paper"
    config.setdefault("orchestrator", {})["scan_interval_seconds"] = args.interval
    config["assets"] = {"crypto": asset_pairs, "stocks": [], "forex": []}

    # --- Print banner ---
    banner = f"""
================================================================================
  AIFred Paper Trading Validator
================================================================================
  Mode:             PAPER (Hyperliquid testnet market data)
  Assets:           {', '.join(assets)}
  Scan Interval:    {args.interval}s
  Duration:         {"infinite (24/7)" if args.duration == 0 else f"{args.duration} minutes"}
  Report Interval:  {args.report_interval} minutes
  Portfolio Value:  ${args.portfolio_value:,.2f}
  Started:          {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
  Log File:         paper_trading.log
================================================================================
"""
    print(banner)
    logger.info(banner)

    # --- Connect to Hyperliquid testnet for market data ---
    hl = HyperliquidConnector(testnet=True)
    try:
        await hl.connect()
        logger.info("Connected to Hyperliquid testnet for market data")
    except Exception as e:
        logger.error("Failed to connect to Hyperliquid testnet: %s", e)
        print(f"ERROR: Cannot connect to Hyperliquid testnet: {e}")
        return

    # --- Initialize orchestrator ---
    orchestrator = Orchestrator(config)
    init_status = orchestrator.initialize_agents()
    logger.info("Agent initialization status: %s", init_status)

    print("\n  Agent Status:")
    for agent_name, ok in init_status.items():
        tag = "\033[92mOK\033[0m" if ok else "\033[91mFAIL\033[0m"
        print(f"    {agent_name:25s} [{tag}]")
    print()

    # --- Set up data provider using Hyperliquid ---
    async def hl_data_provider(asset: str, timeframe: str = "1h") -> pd.DataFrame:
        """Fetch market data from Hyperliquid testnet."""
        try:
            df = await fetch_ohlcv_from_hl(hl, asset, interval=timeframe, limit=200)
            return df
        except Exception as e:
            logger.error("Failed to fetch data for %s: %s", asset, e)
            return pd.DataFrame()

    # The orchestrator expects a sync callable; we wrap async calls.
    # In practice the orchestrator calls _get_technical_signal which uses
    # the data provider synchronously.  We provide a bridge that works
    # inside the running event loop.
    _data_cache: Dict[str, pd.DataFrame] = {}

    def sync_data_provider(asset: str, timeframe: str = "1h") -> pd.DataFrame:
        """Return cached data fetched during the prefetch step."""
        return _data_cache.get(asset, pd.DataFrame())

    orchestrator.set_data_provider(sync_data_provider)
    orchestrator.set_portfolio_value(args.portfolio_value, args.portfolio_value)

    # --- Paper portfolio ---
    portfolio = PaperPortfolio(
        initial_balance=args.portfolio_value,
        cash=args.portfolio_value,
    )

    # --- Graceful shutdown ---
    shutdown_event = asyncio.Event()

    def _signal_handler(*_: Any) -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            signal.signal(sig, _signal_handler)

    # --- Main scan loop ---
    start_time = time.monotonic()
    run_forever = args.duration == 0
    end_time = start_time + (args.duration * 60) if not run_forever else float("inf")
    last_report_time = start_time
    scan_count = 0
    coin_names = [a.split("/")[0] for a in asset_pairs]

    logger.info(
        "Starting paper trading scan loop (%s)...",
        "infinite" if run_forever else f"{args.duration} min",
    )

    try:
        while not shutdown_event.is_set() and time.monotonic() < end_time:
            scan_start = time.monotonic()
            scan_count += 1

            logger.info("=== Paper Scan #%d ===", scan_count)

            # --- Fetch current prices ---
            try:
                all_mids = await hl.get_all_mids()
            except Exception as e:
                logger.error("Failed to fetch prices: %s", e)
                await asyncio.sleep(args.interval)
                continue

            current_prices: Dict[str, float] = {}
            for coin in coin_names:
                price = all_mids.get(coin, 0.0)
                if price > 0:
                    current_prices[coin] = price

            if not current_prices:
                logger.warning("No valid prices received, skipping scan")
                await asyncio.sleep(args.interval)
                continue

            logger.info(
                "Prices: %s",
                ", ".join(f"{k}=${v:,.2f}" for k, v in current_prices.items()),
            )

            # --- Prefetch OHLCV data for all assets ---
            for pair in asset_pairs:
                try:
                    df = await fetch_ohlcv_from_hl(hl, pair, interval="1h", limit=200)
                    if not df.empty:
                        _data_cache[pair] = df
                except Exception as e:
                    logger.warning("Could not fetch OHLCV for %s: %s", pair, e)

            # --- Update unrealized P&L and check stops ---
            portfolio.update_unrealized_pnl(current_prices)
            closed_assets = portfolio.check_stops(current_prices)
            for ca in closed_assets:
                logger.info("Stop triggered for %s", ca)

            # --- Run orchestrator scan cycle ---
            try:
                # Run a single scan cycle through the orchestrator
                for pair in asset_pairs:
                    coin = pair.split("/")[0]
                    asset_class = AssetClass.CRYPTO

                    try:
                        result = await orchestrator._process_asset(pair, asset_class)

                        if result.get("signal_generated"):
                            logger.info(
                                "Signal generated for %s: %s",
                                pair, result.get("reason", ""),
                            )

                        if result.get("trade_executed"):
                            # The orchestrator's execution engine handles the
                            # trade internally via PaperTrader.  We mirror the
                            # decision in our portfolio tracker for reporting.
                            price = current_prices.get(coin, 0.0)
                            if price > 0 and coin not in portfolio.positions:
                                # Extract signal info from the orchestrator's
                                # decision log if available.
                                direction = result.get("direction", "LONG")
                                confidence = result.get("confidence", 0.0)

                                # Calculate position size (2% risk per trade)
                                risk_pct = 0.02
                                position_value = portfolio.cash * risk_pct * 10  # ~20% max
                                position_value = min(position_value, portfolio.cash * 0.25)
                                size = position_value / price if price > 0 else 0

                                # Default stop/take-profit (2% SL, 4% TP)
                                if direction in ("LONG", "BUY", "STRONG_BUY"):
                                    sl = price * 0.98
                                    tp = price * 1.04
                                    side = "LONG"
                                else:
                                    sl = price * 1.02
                                    tp = price * 0.96
                                    side = "SHORT"

                                portfolio.open_position(
                                    asset=coin,
                                    side=side,
                                    price=price,
                                    size=size,
                                    stop_loss=sl,
                                    take_profit=tp,
                                    confidence=confidence,
                                    source="orchestrator",
                                )

                    except Exception as e:
                        logger.error("Error processing %s: %s", pair, e)

            except Exception as e:
                logger.error("Scan cycle error: %s", e)

            # --- Update portfolio tracking ---
            portfolio.update_unrealized_pnl(current_prices)
            equity = portfolio.equity
            if equity > portfolio.peak_equity:
                portfolio.peak_equity = equity

            # --- Periodic report ---
            now = time.monotonic()
            elapsed_min = (now - start_time) / 60
            if (now - last_report_time) >= (args.report_interval * 60):
                print_summary(portfolio, current_prices, scan_count, elapsed_min)
                last_report_time = now

            # --- Sleep until next scan ---
            scan_elapsed = time.monotonic() - scan_start
            sleep_time = max(0, args.interval - scan_elapsed)
            if sleep_time > 0 and not shutdown_event.is_set():
                try:
                    await asyncio.wait_for(
                        shutdown_event.wait(), timeout=sleep_time
                    )
                except asyncio.TimeoutError:
                    pass  # Normal: timeout means the sleep period elapsed

    except asyncio.CancelledError:
        logger.info("Paper trading loop cancelled")

    # --- Final cleanup ---
    elapsed_min = (time.monotonic() - start_time) / 60

    # Close all open positions at current prices
    try:
        all_mids = await hl.get_all_mids()
        for coin in list(portfolio.positions.keys()):
            price = all_mids.get(coin, 0.0)
            if price > 0:
                portfolio.close_position(coin, price, reason="session_end")
    except Exception as e:
        logger.warning("Could not fetch final prices for position close: %s", e)

    # Fetch final prices for report
    final_prices: Dict[str, float] = {}
    try:
        all_mids = await hl.get_all_mids()
        for coin in coin_names:
            final_prices[coin] = all_mids.get(coin, 0.0)
    except Exception:
        pass

    # Print final report
    print_summary(portfolio, final_prices, scan_count, elapsed_min, final=True)

    # Disconnect
    await hl.disconnect()
    logger.info("Hyperliquid testnet disconnected. Paper trading session complete.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="AIFred Paper Trading Validator — end-to-end system validation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python paper_trading.py
  python paper_trading.py --assets ETH,BTC --interval 60 --duration 60
  python paper_trading.py --assets SOL,ETH,BTC --report-interval 5 --duration 30
  python paper_trading.py --portfolio-value 50000 --duration 120
        """,
    )
    parser.add_argument(
        "--assets",
        type=str,
        default="ETH,BTC",
        help="Comma-separated asset symbols (default: ETH,BTC)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Scan interval in seconds (default: 60)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="How long to run in minutes (default: 60)",
    )
    parser.add_argument(
        "--report-interval",
        type=int,
        default=15,
        help="Summary report interval in minutes (default: 15)",
    )
    parser.add_argument(
        "--portfolio-value",
        type=float,
        default=10_000.0,
        help="Initial paper portfolio value in USD (default: 10000)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(run_paper_trading(args))
        return 0
    except KeyboardInterrupt:
        print("\nPaper trading interrupted.")
        return 0
    except Exception as e:
        print(f"\nFATAL ERROR: {e}", file=sys.stderr)
        logger.exception("Fatal error in paper trading")
        return 1


if __name__ == "__main__":
    sys.exit(main())
