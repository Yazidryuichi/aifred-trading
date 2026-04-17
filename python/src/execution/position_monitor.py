"""Background position monitor that checks open positions against market prices.

Runs every check_interval seconds and:
1. Updates current prices for all open positions
2. Checks if stop-loss has been hit (price <= stop for LONG, price >= stop for SHORT)
3. Checks if take-profit has been hit
4. Checks for trailing stop updates
5. Emits close signals for positions that need to be closed
"""

import asyncio
import logging
import traceback
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from src.utils.types import Position, TradeResult, TradeStatus

if TYPE_CHECKING:
    from src.execution.execution_engine import ExecutionAgent

logger = logging.getLogger(__name__)


class PositionMonitor:
    """Background monitor that checks open positions against market prices.

    Designed to run as an asyncio background task alongside the orchestrator's
    scan loop. Works identically in paper and live mode -- the execution agent
    handles the mode difference internally.
    """

    def __init__(
        self,
        execution_agent: "ExecutionAgent",
        price_provider: Callable,
        config: Dict[str, Any],
        check_interval: float = 30.0,
    ):
        """
        Args:
            execution_agent: The execution agent used to close positions.
            price_provider: Callable(asset: str) -> Optional[float] that returns
                the current price for a given asset. Should return None if price
                is unavailable.
            config: Full application config dict.
            check_interval: Seconds between each check cycle.
        """
        self._execution_agent = execution_agent
        self._price_provider = price_provider
        self._config = config
        self._check_interval = check_interval

        # Trailing stop configuration
        monitor_cfg = config.get("position_monitor", {})
        self._trailing_stop_enabled = monitor_cfg.get("trailing_stop_enabled", False)
        self._trailing_stop_pct = monitor_cfg.get("trailing_stop_pct", 2.0) / 100.0

        # Signal-staleness exit (close when the signal that opened this position is too old)
        self._staleness_enabled = monitor_cfg.get("signal_staleness_enabled", True)
        self._staleness_max_age_minutes = float(
            monitor_cfg.get("signal_staleness_max_age_minutes", 240)
        )

        # Control
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._running = False

        # Stats
        self._check_count = 0
        self._close_count = 0
        self._errors: Dict[str, int] = {}

    async def start(self) -> None:
        """Start the background monitoring loop."""
        if self._running:
            logger.warning("PositionMonitor is already running")
            return

        self._stop_event.clear()
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "PositionMonitor started (interval=%.1fs, trailing_stop=%s)",
            self._check_interval,
            self._trailing_stop_enabled,
        )

    async def stop(self) -> None:
        """Stop the monitor gracefully."""
        if not self._running:
            return

        logger.info("PositionMonitor stopping...")
        self._running = False
        self._stop_event.set()

        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("PositionMonitor did not stop within timeout, cancelling")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None

        logger.info(
            "PositionMonitor stopped (checks=%d, closes=%d)",
            self._check_count, self._close_count,
        )

    async def _run_loop(self) -> None:
        """Main monitoring loop."""
        while self._running and not self._stop_event.is_set():
            try:
                await self._check_cycle()
            except Exception as e:
                logger.error(
                    "PositionMonitor check cycle error: %s\n%s",
                    e, traceback.format_exc(),
                )

            # Wait for next cycle or stop signal
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._check_interval,
                )
                # If we get here, stop was requested
                break
            except asyncio.TimeoutError:
                # Normal timeout -- loop continues
                pass

    async def _check_cycle(self) -> None:
        """Single check cycle -- iterate all open positions and check exits."""
        self._check_count += 1
        positions = self._execution_agent.get_open_positions()

        if not positions:
            logger.debug(
                "PositionMonitor cycle #%d: no open positions", self._check_count
            )
            return

        logger.debug(
            "PositionMonitor cycle #%d: checking %d positions",
            self._check_count, len(positions),
        )

        for position in positions:
            try:
                close_reason = await self._check_position(position)
                if close_reason is not None:
                    await self._close_position(position, close_reason)
            except Exception as e:
                asset = position.asset
                self._errors[asset] = self._errors.get(asset, 0) + 1
                logger.error(
                    "PositionMonitor error checking %s: %s\n%s",
                    asset, e, traceback.format_exc(),
                )

    async def _check_position(self, position: Position) -> Optional[str]:
        """Check a single position against current market price.

        Updates position.current_price and position.unrealized_pnl.

        Returns:
            Close reason string if exit is triggered, or None to keep open.
        """
        current_price = self._get_price(position.asset)
        if current_price is None:
            logger.debug(
                "PositionMonitor: price unavailable for %s, skipping",
                position.asset,
            )
            return None

        # Update position price and PnL
        position.current_price = current_price
        if position.side == "LONG":
            position.unrealized_pnl = (current_price - position.entry_price) * position.size
        else:
            position.unrealized_pnl = (position.entry_price - current_price) * position.size

        # Also update in the execution agent's internal tracking
        self._execution_agent.update_position_price(position.asset, current_price)

        # Check stop-loss
        if position.stop_loss > 0:
            if position.side == "LONG" and current_price <= position.stop_loss:
                logger.info(
                    "STOP-LOSS HIT: %s LONG price=%.4f <= stop=%.4f",
                    position.asset, current_price, position.stop_loss,
                )
                return "stop_loss_hit"
            if position.side == "SHORT" and current_price >= position.stop_loss:
                logger.info(
                    "STOP-LOSS HIT: %s SHORT price=%.4f >= stop=%.4f",
                    position.asset, current_price, position.stop_loss,
                )
                return "stop_loss_hit"

        # Check take-profit
        if position.take_profit > 0:
            if position.side == "LONG" and current_price >= position.take_profit:
                logger.info(
                    "TAKE-PROFIT HIT: %s LONG price=%.4f >= tp=%.4f",
                    position.asset, current_price, position.take_profit,
                )
                return "take_profit_hit"
            if position.side == "SHORT" and current_price <= position.take_profit:
                logger.info(
                    "TAKE-PROFIT HIT: %s SHORT price=%.4f <= tp=%.4f",
                    position.asset, current_price, position.take_profit,
                )
                return "take_profit_hit"

        # Signal-staleness exit: catalyst may have evaporated
        if self._staleness_enabled and position.signal_timestamp is not None:
            sig_ts = position.signal_timestamp
            # Normalize to aware UTC to avoid naive/aware subtraction errors
            if sig_ts.tzinfo is None:
                sig_ts = sig_ts.replace(tzinfo=timezone.utc)
            age_minutes = (datetime.now(timezone.utc) - sig_ts).total_seconds() / 60.0
            if age_minutes > self._staleness_max_age_minutes:
                logger.info(
                    "SIGNAL STALENESS EXIT: %s %s signal age=%.1fm > max=%.1fm",
                    position.asset, position.side, age_minutes, self._staleness_max_age_minutes,
                )
                return "stale_signal"

        # Peak profit trailing stop
        current_pnl_pct = ((current_price - position.entry_price) / position.entry_price * 100
                           if position.side == "LONG"
                           else (position.entry_price - current_price) / position.entry_price * 100)

        # Track peak
        if not hasattr(position, '_peak_pnl_pct') or position._peak_pnl_pct is None:
            position._peak_pnl_pct = current_pnl_pct
        elif current_pnl_pct > position._peak_pnl_pct:
            position._peak_pnl_pct = current_pnl_pct

        PEAK_PROFIT_THRESHOLD = 5.0    # only activate after 5% unrealized profit
        PEAK_DRAWDOWN_TRIGGER = 0.40   # close if profit drops 40% from peak

        if (position._peak_pnl_pct >= PEAK_PROFIT_THRESHOLD
                and current_pnl_pct < position._peak_pnl_pct * (1 - PEAK_DRAWDOWN_TRIGGER)):
            logger.warning(
                "PEAK PROFIT STOP: %s peak=%.1f%% current=%.1f%% (%.1f%% drawdown from peak)",
                position.asset, position._peak_pnl_pct, current_pnl_pct,
                (1 - current_pnl_pct / position._peak_pnl_pct) * 100
            )
            return "peak_profit_stop"

        # Update trailing stop if applicable
        if self._trailing_stop_enabled:
            self._update_trailing_stop(position, current_price)

        return None

    def _update_trailing_stop(self, position: Position, current_price: float) -> None:
        """Move the stop-loss up (for LONG) or down (for SHORT) to lock in profits.

        Only moves the stop in the favorable direction -- never away from it.
        """
        if position.stop_loss <= 0:
            return

        if position.side == "LONG":
            # For longs, trail below the highest price seen
            new_stop = current_price * (1.0 - self._trailing_stop_pct)
            if new_stop > position.stop_loss:
                old_stop = position.stop_loss
                position.stop_loss = new_stop
                self._execution_agent.modify_stop(position, new_stop)
                logger.info(
                    "Trailing stop updated: %s LONG stop %.4f -> %.4f (price=%.4f)",
                    position.asset, old_stop, new_stop, current_price,
                )
        else:
            # For shorts, trail above the lowest price seen
            new_stop = current_price * (1.0 + self._trailing_stop_pct)
            if new_stop < position.stop_loss:
                old_stop = position.stop_loss
                position.stop_loss = new_stop
                self._execution_agent.modify_stop(position, new_stop)
                logger.info(
                    "Trailing stop updated: %s SHORT stop %.4f -> %.4f (price=%.4f)",
                    position.asset, old_stop, new_stop, current_price,
                )

    async def _close_position(self, position: Position, reason: str) -> None:
        """Close a position via the execution agent."""
        logger.info(
            "Closing position: %s %s size=%.6f reason=%s price=%.4f",
            position.side, position.asset, position.size, reason,
            position.current_price,
        )

        try:
            result: TradeResult = self._execution_agent.close_position(
                position, reason=reason,
            )
            self._close_count += 1

            if result.status == TradeStatus.FILLED:
                pnl = position.unrealized_pnl
                logger.info(
                    "Position closed: %s %s @ %.4f, reason=%s, PnL=%.2f",
                    position.side, position.asset, result.fill_price,
                    reason, pnl,
                )
            else:
                logger.warning(
                    "Position close returned status %s for %s: %s",
                    result.status.value, position.asset, result.error,
                )
        except Exception as e:
            logger.error(
                "Failed to close position %s (%s): %s",
                position.asset, reason, e,
            )

    def _get_price(self, asset: str) -> Optional[float]:
        """Get current price from the price provider callback."""
        try:
            price = self._price_provider(asset)
            if price is not None and price > 0:
                return float(price)
        except Exception as e:
            logger.debug("Price provider error for %s: %s", asset, e)
        return None

    # -- Status --

    @property
    def is_running(self) -> bool:
        return self._running

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "check_interval": self._check_interval,
            "check_count": self._check_count,
            "close_count": self._close_count,
            "trailing_stop_enabled": self._trailing_stop_enabled,
            "trailing_stop_pct": self._trailing_stop_pct * 100,
            "errors": dict(self._errors),
        }
