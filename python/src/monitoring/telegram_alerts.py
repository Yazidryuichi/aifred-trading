"""Telegram bot integration for trading alerts and notifications."""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class AlertType(Enum):
    TRADE_EXECUTED = "trade_executed"
    STOP_LOSS_HIT = "stop_loss_hit"
    DAILY_SUMMARY = "daily_summary"
    MODEL_DEGRADATION = "model_degradation"
    SYSTEM_ERROR = "system_error"
    DRAWDOWN_WARNING = "drawdown_warning"
    SCAN_ANALYSIS = "scan_analysis"
    CYCLE_SUMMARY = "cycle_summary"
    PEAK_PROFIT_STOP = "peak_profit_stop"


class TelegramAlerts:
    """Sends trading alerts via Telegram bot.

    Gracefully degrades if bot token is not configured.
    Implements rate limiting to avoid spam.
    """

    # Rate limiting: max messages per window
    RATE_LIMIT_WINDOW = 60  # seconds
    RATE_LIMIT_MAX = 30  # max messages per window (raised to allow per-asset analysis)

    def __init__(self, bot_token: str = "", chat_id: str = "",
                 alert_config: Optional[Dict[str, bool]] = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._enabled = bool(bot_token and chat_id)
        self._bot = None
        self._message_times: list[float] = []

        # Which alert types are enabled
        defaults = {
            "trade_executed": True,
            "stop_loss_hit": True,
            "daily_summary": True,
            "model_degradation": True,
            "drawdown_warning": True,
            "scan_analysis": True,
            "cycle_summary": True,
            "peak_profit_stop": True,
        }
        self._alert_config = {**defaults, **(alert_config or {})}

        if not self._enabled:
            logger.info("Telegram alerts DISABLED (no bot token/chat ID configured)")
        else:
            self._init_bot()

    def _init_bot(self) -> None:
        """Initialize the Telegram bot."""
        try:
            from telegram import Bot
            self._bot = Bot(token=self.bot_token)
            logger.info("Telegram bot initialized")
        except ImportError:
            logger.warning("python-telegram-bot not installed, Telegram alerts disabled")
            self._enabled = False
        except Exception as e:
            logger.error("Failed to initialize Telegram bot: %s", e)
            self._enabled = False

    def _is_rate_limited(self) -> bool:
        now = time.time()
        # Remove old timestamps
        self._message_times = [t for t in self._message_times
                               if now - t < self.RATE_LIMIT_WINDOW]
        return len(self._message_times) >= self.RATE_LIMIT_MAX

    def _record_message(self) -> None:
        self._message_times.append(time.time())

    def send_alert(self, message: str, alert_type: AlertType = AlertType.SYSTEM_ERROR) -> bool:
        """Send an alert message via Telegram.

        Returns True if sent successfully, False otherwise.
        """
        if not self._enabled:
            logger.debug("Telegram alert skipped (disabled): %s", alert_type.value)
            return False

        # Check if this alert type is enabled
        if not self._alert_config.get(alert_type.value, True):
            return False

        if self._is_rate_limited():
            logger.warning("Telegram rate limit reached, dropping alert")
            return False

        try:
            self._send_sync(message)
            self._record_message()
            return True
        except Exception as e:
            logger.error("Failed to send Telegram alert: %s", e)
            return False

    async def send_alert_async(self, message: str,
                               alert_type: AlertType = AlertType.SYSTEM_ERROR) -> bool:
        """Async version of send_alert."""
        if not self._enabled or not self._alert_config.get(alert_type.value, True):
            return False
        if self._is_rate_limited():
            return False
        try:
            await self._send_async(message)
            self._record_message()
            return True
        except Exception as e:
            logger.error("Failed to send async Telegram alert: %s", e)
            return False

    def _send_sync(self, message: str) -> None:
        """Send message — works whether called from sync or async context."""
        if self._bot is None:
            return
        # Detect if we're inside a running event loop
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is not None:
            # Async context: schedule and keep a reference so it isn't garbage collected
            task = running_loop.create_task(self._send_async(message))
            if not hasattr(self, '_pending_tasks'):
                self._pending_tasks = set()
            self._pending_tasks.add(task)
            task.add_done_callback(self._pending_tasks.discard)
        else:
            # Sync context: spin up a temporary loop
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(self._bot.send_message(
                    chat_id=self.chat_id, text=message, parse_mode="HTML",
                ))
            finally:
                loop.close()

    async def _send_async(self, message: str) -> None:
        if self._bot is None:
            return
        await self._bot.send_message(
            chat_id=self.chat_id, text=message, parse_mode="HTML",
        )

    # --- Convenience methods for specific alert types ---

    def alert_trade_executed(self, asset: str, side: str, size: float,
                             price: float, exchange: str) -> bool:
        msg = (
            f"<b>Trade Executed</b>\n"
            f"Asset: {asset}\n"
            f"Side: {side.upper()}\n"
            f"Size: {size:.6f}\n"
            f"Price: ${price:,.4f}\n"
            f"Exchange: {exchange}"
        )
        return self.send_alert(msg, AlertType.TRADE_EXECUTED)

    def alert_stop_loss_hit(self, asset: str, entry_price: float,
                            stop_price: float, pnl: float) -> bool:
        emoji = "+" if pnl >= 0 else ""
        msg = (
            f"<b>Stop-Loss Hit</b>\n"
            f"Asset: {asset}\n"
            f"Entry: ${entry_price:,.4f}\n"
            f"Stop: ${stop_price:,.4f}\n"
            f"P&L: {emoji}${pnl:,.2f}"
        )
        return self.send_alert(msg, AlertType.STOP_LOSS_HIT)

    def alert_daily_summary(self, summary_text: str) -> bool:
        msg = f"<b>Daily P&L Summary</b>\n\n{summary_text}"
        return self.send_alert(msg, AlertType.DAILY_SUMMARY)

    def alert_model_degradation(self, model_name: str,
                                current_accuracy: float,
                                baseline_accuracy: float) -> bool:
        drop = baseline_accuracy - current_accuracy
        msg = (
            f"<b>Model Degradation Warning</b>\n"
            f"Model: {model_name}\n"
            f"Current accuracy: {current_accuracy:.1f}%\n"
            f"Baseline: {baseline_accuracy:.1f}%\n"
            f"Drop: {drop:.1f}%"
        )
        return self.send_alert(msg, AlertType.MODEL_DEGRADATION)

    def alert_system_error(self, subsystem: str, error: str) -> bool:
        msg = (
            f"<b>System Error</b>\n"
            f"Subsystem: {subsystem}\n"
            f"Error: {error}"
        )
        return self.send_alert(msg, AlertType.SYSTEM_ERROR)

    def alert_scan_analysis(
        self,
        asset: str,
        scan_num: int,
        ml_predictions: Optional[Dict[str, str]] = None,
        ensemble_direction: str = "HOLD",
        ensemble_confidence: float = 0.0,
        confluences: int = 0,
        sentiment_status: str = "n/a",
        onchain_status: str = "n/a",
        fused_direction: str = "HOLD",
        fused_confidence: float = 0.0,
        meta_reasoning: Optional[str] = None,
        meta_adjusted_conf: Optional[float] = None,
        decision: str = "HOLD",
        reason: str = "",
        expectation: str = "",
        threshold: float = 80.0,
    ) -> bool:
        """Send a detailed per-asset scan analysis with full reasoning chain."""
        ml_block = ""
        if ml_predictions:
            for model, pred in ml_predictions.items():
                ml_block += f"  • {model}: {pred}\n"

        meta_block = ""
        if meta_reasoning:
            adj_str = f" → adjusted: {meta_adjusted_conf:.1f}%" if meta_adjusted_conf is not None else ""
            meta_block = (
                f"\n<b>🧠 Meta-Reasoning (Claude){adj_str}</b>\n"
                f"<i>{meta_reasoning[:400]}</i>\n"
            )

        emoji = {
            "EXECUTED": "✅",
            "REJECTED": "❌",
            "HOLD": "⏸",
            "SKIPPED": "⏭",
        }.get(decision.upper(), "📊")

        msg = (
            f"<b>{emoji} Scan #{scan_num} — {asset}</b>\n"
            f"\n"
            f"<b>ML Models</b>\n"
            f"{ml_block}"
            f"\n"
            f"<b>Ensemble:</b> {ensemble_direction} {ensemble_confidence:.1f}% ({confluences} confluences)\n"
            f"<b>Sentiment:</b> {sentiment_status}\n"
            f"<b>On-chain:</b> {onchain_status}\n"
            f"\n"
            f"<b>📊 Fused Signal:</b> {fused_direction} @ {fused_confidence:.1f}%"
            f"{meta_block}"
            f"\n"
            f"<b>Decision:</b> {decision}\n"
            f"<b>Why:</b> {reason}\n"
        )
        if expectation:
            msg += f"<b>Expectation:</b> {expectation}\n"
        msg += f"<i>Threshold: {threshold:.0f}% required for live execution</i>"

        return self.send_alert(msg, AlertType.SCAN_ANALYSIS)

    def alert_cycle_summary(
        self,
        scan_num: int,
        elapsed_sec: float,
        signals_generated: int,
        trades_executed: int,
        exits_processed: int,
        portfolio_value: float,
        open_positions: int,
        next_scan_in: int = 60,
        macro_verdict: str = "n/a",
    ) -> bool:
        """Send a per-scan-cycle summary."""
        msg = (
            f"<b>🔄 Scan #{scan_num} Complete</b>\n"
            f"\n"
            f"⏱ Duration: {elapsed_sec:.1f}s\n"
            f"📊 Signals: {signals_generated}\n"
            f"💸 Trades: {trades_executed}\n"
            f"🚪 Exits: {exits_processed}\n"
            f"💰 Portfolio: ${portfolio_value:.2f}\n"
            f"📍 Open positions: {open_positions}\n"
            f"🌐 Macro: {macro_verdict}\n"
            f"\n"
            f"<i>Next scan in ~{next_scan_in}s</i>"
        )
        return self.send_alert(msg, AlertType.CYCLE_SUMMARY)

    def alert_peak_profit_stop(self, asset: str, peak_pnl: float,
                              current_pnl: float, locked_profit: float) -> bool:
        """Send alert when peak profit trailing stop triggers."""
        msg = (
            f"<b>Peak Profit Stop</b>\n"
            f"Asset: {asset}\n"
            f"Peak P&L: {peak_pnl:+.1f}%\n"
            f"Current P&L: {current_pnl:+.1f}%\n"
            f"Drawdown from peak: {peak_pnl - current_pnl:.1f}%\n"
            f"Locked profit: {locked_profit:+.1f}%"
        )
        return self.send_alert(msg, AlertType.PEAK_PROFIT_STOP)

    def alert_drawdown_warning(self, current_drawdown: float,
                               limit: float) -> bool:
        msg = (
            f"<b>Drawdown Warning</b>\n"
            f"Current drawdown: {current_drawdown:.2f}%\n"
            f"Limit: {limit:.2f}%\n"
            f"Action: Consider reducing exposure"
        )
        return self.send_alert(msg, AlertType.DRAWDOWN_WARNING)
