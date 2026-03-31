"""Interactive Telegram bot for monitoring and controlling the trading system.

Extends TelegramAlerts with:
- Interactive commands (/status, /positions, /pnl, /pause, /resume, /kill, /help)
- Periodic health reports (every 4 hours)
- Daily P&L summary (at midnight UTC)
- Heartbeat pings (every 30 minutes)
- Startup/shutdown notifications
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def _escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _pnl_emoji(value: float) -> str:
    """Return emoji indicator for positive/negative P&L."""
    if value > 0:
        return "+"
    elif value < 0:
        return ""
    return " "


def _status_icon(status: str) -> str:
    """Map health status strings to icons."""
    mapping = {
        "ok": "[OK]",
        "warning": "[WARN]",
        "critical": "[CRIT]",
        "unknown": "[???]",
    }
    return mapping.get(status.lower(), "[???]")


class TradingTelegramBot:
    """Full-featured Telegram bot for trading system control.

    This wraps and extends the existing TelegramAlerts class.
    It handles interactive commands from authorized users and
    sends periodic automated reports (heartbeat, daily P&L, health).
    """

    def __init__(self, bot_token: str, chat_id: str, config: dict = None):
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._config = config or {}
        self._enabled = bool(bot_token and chat_id)
        self._application = None  # telegram.ext.Application
        self._running = False
        self._start_time: Optional[datetime] = None

        # Callbacks to get system state (set by orchestrator / main.py)
        self._get_status: Optional[Callable[[], Dict[str, Any]]] = None
        self._get_positions: Optional[Callable[[], List[Dict[str, Any]]]] = None
        self._get_pnl: Optional[Callable[[], Dict[str, Any]]] = None
        self._get_health: Optional[Callable[[], Dict[str, Any]]] = None
        self._pause_trading: Optional[Callable[[], None]] = None
        self._resume_trading: Optional[Callable[[], None]] = None
        self._kill_switch: Optional[Callable[[str], None]] = None

        # Heartbeat tracking
        telegram_cfg = self._config.get("monitoring", {}).get("telegram", {})
        self._heartbeat_interval: int = telegram_cfg.get("heartbeat_interval", 1800)
        self._daily_report_hour: int = telegram_cfg.get("daily_report_hour", 0)
        self._commands_enabled: bool = telegram_cfg.get("commands_enabled", True)
        self._health_report_interval: int = telegram_cfg.get(
            "health_report_interval", 14400
        )  # 4 hours

        # Alert type toggles
        alert_cfg = telegram_cfg.get("alerts", {})
        self._alert_config = {
            "trade_executed": alert_cfg.get("trade_executed", True),
            "position_closed": alert_cfg.get("position_closed", True),
            "stop_loss_hit": alert_cfg.get("stop_loss_hit", True),
            "safety_triggered": alert_cfg.get("safety_triggered", True),
            "system_error": alert_cfg.get("system_error", True),
            "drawdown_warning": alert_cfg.get("drawdown_warning", True),
        }

    # ------------------------------------------------------------------
    # Callback wiring
    # ------------------------------------------------------------------

    def set_callbacks(
        self,
        get_status: Optional[Callable] = None,
        get_positions: Optional[Callable] = None,
        get_pnl: Optional[Callable] = None,
        get_health: Optional[Callable] = None,
        pause_trading: Optional[Callable] = None,
        resume_trading: Optional[Callable] = None,
        kill_switch: Optional[Callable] = None,
    ) -> None:
        """Wire up callbacks to the orchestrator / main application."""
        if get_status is not None:
            self._get_status = get_status
        if get_positions is not None:
            self._get_positions = get_positions
        if get_pnl is not None:
            self._get_pnl = get_pnl
        if get_health is not None:
            self._get_health = get_health
        if pause_trading is not None:
            self._pause_trading = pause_trading
        if resume_trading is not None:
            self._resume_trading = resume_trading
        if kill_switch is not None:
            self._kill_switch = kill_switch

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the Telegram bot (runs in background).

        Registers command handlers, starts polling for updates,
        sends a startup notification, and launches background tasks.
        """
        if not self._enabled:
            logger.info("Telegram bot disabled (no bot_token or chat_id)")
            return

        try:
            from telegram.ext import Application, CommandHandler
        except ImportError:
            logger.warning(
                "python-telegram-bot not installed — Telegram bot disabled. "
                "Install with: pip install python-telegram-bot>=20"
            )
            self._enabled = False
            return

        try:
            self._application = (
                Application.builder().token(self._bot_token).build()
            )
        except Exception as exc:
            logger.error("Failed to build Telegram Application: %s", exc)
            self._enabled = False
            return

        # Register command handlers
        if self._commands_enabled:
            handlers = [
                ("start", self._cmd_start),
                ("help", self._cmd_help),
                ("status", self._cmd_status),
                ("positions", self._cmd_positions),
                ("pnl", self._cmd_pnl),
                ("pause", self._cmd_pause),
                ("resume", self._cmd_resume),
                ("kill", self._cmd_kill),
                ("health", self._cmd_health),
            ]
            for name, callback in handlers:
                self._application.add_handler(CommandHandler(name, callback))

        # Start polling for commands
        await self._application.initialize()
        await self._application.start()
        await self._application.updater.start_polling(drop_pending_updates=True)

        self._running = True
        self._start_time = datetime.utcnow()

        # Determine mode label
        exec_cfg = self._config.get("execution", {})
        mode = exec_cfg.get("mode", "paper").upper()

        # Startup notification
        await self._send(
            "<b>AIFred Trading Bot Started</b>\n"
            f"Mode: {_escape_html(mode)}\n"
            f"Time: {self._start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
            "Send /help for available commands"
        )

        # Launch background tasks
        asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self._daily_report_loop())
        asyncio.create_task(self._health_report_loop())

        logger.info("Telegram bot started successfully")

    async def stop(self) -> None:
        """Stop the bot gracefully with a shutdown notification."""
        if not self._running or self._application is None:
            return

        uptime = self._format_uptime()
        try:
            await self._send(
                "<b>AIFred Trading Bot Stopping</b>\n"
                f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
                f"Uptime: {uptime}"
            )
        except Exception:
            pass  # best-effort shutdown message

        self._running = False

        try:
            await self._application.updater.stop()
            await self._application.stop()
            await self._application.shutdown()
        except Exception as exc:
            logger.error("Error during Telegram bot shutdown: %s", exc)

        logger.info("Telegram bot stopped")

    # ------------------------------------------------------------------
    # Message sending
    # ------------------------------------------------------------------

    async def _send(self, message: str) -> bool:
        """Send an HTML-formatted message to the configured chat.

        Returns True on success, False on failure.
        """
        if not self._enabled or self._application is None:
            return False
        try:
            await self._application.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode="HTML",
            )
            return True
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Command Handlers
    # ------------------------------------------------------------------

    async def _cmd_start(self, update, context) -> None:
        """Handle /start command."""
        await update.message.reply_html(
            "<b>Welcome to AIFred Trading Bot!</b>\n\n"
            "This bot monitors and controls the AIFred multi-agent "
            "trading system.\n\n"
            "Send /help for a list of available commands."
        )

    async def _cmd_help(self, update, context) -> None:
        """Handle /help — list all available commands."""
        help_text = (
            "<b>AIFred Trading Bot Commands</b>\n\n"
            "/status  --  System status (mode, uptime, circuit breakers)\n"
            "/positions  --  Open positions with unrealized P&amp;L\n"
            "/pnl  --  Daily and weekly P&amp;L summary\n"
            "/health  --  System health (data freshness, exchanges, agents)\n"
            "/pause  --  Pause trading (no new entries)\n"
            "/resume  --  Resume trading\n"
            "/kill CONFIRM  --  EMERGENCY: close all positions, halt trading\n"
            "/help  --  Show this message\n\n"
            "<i>Automated reports: heartbeat every "
            f"{self._heartbeat_interval // 60} min, "
            f"daily P&amp;L at {self._daily_report_hour:02d}:00 UTC, "
            f"health every {self._health_report_interval // 3600}h</i>"
        )
        await update.message.reply_html(help_text)

    async def _cmd_status(self, update, context) -> None:
        """Handle /status — show system status."""
        if not self._get_status:
            await update.message.reply_text(
                "Status callback not configured. "
                "The orchestrator has not wired up status reporting."
            )
            return

        try:
            status = self._get_status()
        except Exception as exc:
            await update.message.reply_text(f"Error fetching status: {exc}")
            return

        running = status.get("running", False)
        mode = _escape_html(status.get("mode", "unknown"))
        scan_count = status.get("scan_count", 0)
        last_scan = status.get("last_scan_time")
        paused = status.get("paused", False)

        # Circuit breaker
        cb = status.get("circuit_breaker", {})
        cb_tripped = cb.get("tripped", False)
        cb_reason = _escape_html(cb.get("reason", ""))
        cb_daily_trades = cb.get("daily_trades", 0)
        cb_max_trades = cb.get("max_daily_trades", "?")

        # Safety
        safety = status.get("safety", {})
        killed = safety.get("killed", False)
        daily_pnl = safety.get("daily_pnl", 0.0)
        weekly_pnl = safety.get("weekly_pnl", 0.0)

        # Uptime
        uptime = self._format_uptime()

        # Last scan
        if last_scan:
            if isinstance(last_scan, str):
                last_scan_str = last_scan
            else:
                last_scan_str = last_scan.strftime("%H:%M:%S UTC")
        else:
            last_scan_str = "never"

        # Build message
        state_icon = "[PAUSED]" if paused else ("[KILLED]" if killed else ("[RUNNING]" if running else "[STOPPED]"))

        lines = [
            f"<b>System Status</b> {state_icon}",
            "",
            f"Mode: {mode}",
            f"Uptime: {uptime}",
            f"Scans: {scan_count}",
            f"Last scan: {last_scan_str}",
            "",
            "<b>Circuit Breaker</b>",
            f"  State: {'TRIPPED' if cb_tripped else 'OK'}",
        ]
        if cb_tripped:
            lines.append(f"  Reason: {cb_reason}")
        lines.append(f"  Daily trades: {cb_daily_trades}/{cb_max_trades}")

        lines.extend([
            "",
            "<b>Account Safety</b>",
            f"  Kill switch: {'ACTIVE' if killed else 'off'}",
            f"  Daily P&amp;L: {_pnl_emoji(daily_pnl)}${daily_pnl:,.2f}",
            f"  Weekly P&amp;L: {_pnl_emoji(weekly_pnl)}${weekly_pnl:,.2f}",
        ])

        # Error counts
        errors = status.get("error_counts", {})
        if errors:
            lines.append("")
            lines.append("<b>Recent Errors</b>")
            for subsystem, count in sorted(errors.items()):
                lines.append(f"  {_escape_html(subsystem)}: {count}")

        await update.message.reply_html("\n".join(lines))

    async def _cmd_positions(self, update, context) -> None:
        """Handle /positions — show open positions."""
        if not self._get_positions:
            await update.message.reply_text(
                "Positions callback not configured."
            )
            return

        try:
            positions = self._get_positions()
        except Exception as exc:
            await update.message.reply_text(f"Error fetching positions: {exc}")
            return

        if not positions:
            await update.message.reply_text("No open positions.")
            return

        lines = [f"<b>Open Positions ({len(positions)})</b>", ""]

        total_pnl = 0.0
        for pos in positions:
            asset = _escape_html(pos.get("asset", "???"))
            side = pos.get("side", "???").upper()
            entry = pos.get("entry_price", 0.0)
            current = pos.get("current_price", 0.0)
            size = pos.get("size", 0.0)
            stop = pos.get("stop_loss", None)
            target = pos.get("take_profit", None)

            # Calculate unrealized P&L
            if side == "LONG":
                pnl = (current - entry) * size
            elif side == "SHORT":
                pnl = (entry - current) * size
            else:
                pnl = 0.0

            total_pnl += pnl
            pnl_pct = ((current - entry) / entry * 100) if entry > 0 else 0.0
            if side == "SHORT":
                pnl_pct = -pnl_pct

            lines.append(
                f"<b>{asset}</b> {side}\n"
                f"  Entry: ${entry:,.4f}  |  Now: ${current:,.4f}\n"
                f"  Size: {size:.6f}  |  P&amp;L: {_pnl_emoji(pnl)}${pnl:,.2f} "
                f"({_pnl_emoji(pnl_pct)}{pnl_pct:.2f}%)"
            )

            extras = []
            if stop is not None:
                extras.append(f"SL: ${stop:,.4f}")
            if target is not None:
                extras.append(f"TP: ${target:,.4f}")
            if extras:
                lines.append(f"  {' | '.join(extras)}")

            lines.append("")

        lines.append(
            f"<b>Total Unrealized P&amp;L:</b> "
            f"{_pnl_emoji(total_pnl)}${total_pnl:,.2f}"
        )

        await update.message.reply_html("\n".join(lines))

    async def _cmd_pnl(self, update, context) -> None:
        """Handle /pnl — show P&L summary."""
        if not self._get_pnl:
            await update.message.reply_text("P&L callback not configured.")
            return

        try:
            pnl_data = self._get_pnl()
        except Exception as exc:
            await update.message.reply_text(f"Error fetching P&L: {exc}")
            return

        daily_pnl = pnl_data.get("daily_pnl", 0.0)
        weekly_pnl = pnl_data.get("weekly_pnl", 0.0)
        daily_trades = pnl_data.get("daily_trades", 0)
        weekly_trades = pnl_data.get("weekly_trades", 0)
        win_rate = pnl_data.get("win_rate", 0.0)
        total_pnl = pnl_data.get("total_pnl", 0.0)
        best_trade = pnl_data.get("best_trade", 0.0)
        worst_trade = pnl_data.get("worst_trade", 0.0)
        max_drawdown = pnl_data.get("max_drawdown_pct", 0.0)
        unrealized = pnl_data.get("unrealized_pnl", 0.0)

        lines = [
            "<b>P&amp;L Summary</b>",
            "",
            "<b>Today</b>",
            f"  Realized P&amp;L: {_pnl_emoji(daily_pnl)}${daily_pnl:,.2f}",
            f"  Trades: {daily_trades}",
            "",
            "<b>This Week</b>",
            f"  Realized P&amp;L: {_pnl_emoji(weekly_pnl)}${weekly_pnl:,.2f}",
            f"  Trades: {weekly_trades}",
            f"  Win rate: {win_rate:.1f}%",
            "",
            "<b>Session Total</b>",
            f"  Realized: {_pnl_emoji(total_pnl)}${total_pnl:,.2f}",
            f"  Unrealized: {_pnl_emoji(unrealized)}${unrealized:,.2f}",
            f"  Best trade: {_pnl_emoji(best_trade)}${best_trade:,.2f}",
            f"  Worst trade: {_pnl_emoji(worst_trade)}${worst_trade:,.2f}",
            f"  Max drawdown: {max_drawdown:.2f}%",
        ]

        await update.message.reply_html("\n".join(lines))

    async def _cmd_pause(self, update, context) -> None:
        """Handle /pause — pause trading (no new entries)."""
        if not self._pause_trading:
            await update.message.reply_text(
                "Pause callback not configured."
            )
            return

        try:
            self._pause_trading()
            await update.message.reply_html(
                "<b>Trading Paused</b>\n\n"
                "No new positions will be opened.\n"
                "Existing positions and stop-losses remain active.\n\n"
                "Send /resume to continue trading."
            )
            logger.info("Trading paused via Telegram command")
        except Exception as exc:
            await update.message.reply_text(f"Failed to pause: {exc}")

    async def _cmd_resume(self, update, context) -> None:
        """Handle /resume — resume trading."""
        if not self._resume_trading:
            await update.message.reply_text(
                "Resume callback not configured."
            )
            return

        try:
            self._resume_trading()
            await update.message.reply_html(
                "<b>Trading Resumed</b>\n\n"
                "The system will open new positions again."
            )
            logger.info("Trading resumed via Telegram command")
        except Exception as exc:
            await update.message.reply_text(f"Failed to resume: {exc}")

    async def _cmd_kill(self, update, context) -> None:
        """Handle /kill — emergency kill switch.

        Requires explicit confirmation: /kill CONFIRM
        """
        args = context.args
        if not args or args[0] != "CONFIRM":
            await update.message.reply_html(
                "<b>EMERGENCY KILL SWITCH</b>\n\n"
                "This will:\n"
                "  1. Close ALL open positions at market\n"
                "  2. Halt all trading immediately\n"
                "  3. Require manual restart to resume\n\n"
                "To confirm, send:\n"
                "<code>/kill CONFIRM</code>"
            )
            return

        if not self._kill_switch:
            await update.message.reply_text(
                "Kill switch callback not configured."
            )
            return

        try:
            user = update.effective_user
            username = user.username or user.first_name if user else "unknown"
            reason = f"telegram_kill_command by @{username}"
            self._kill_switch(reason)

            await update.message.reply_html(
                "<b>KILL SWITCH ACTIVATED</b>\n\n"
                "All positions are being closed.\n"
                "Trading is halted.\n\n"
                f"Triggered by: @{_escape_html(username)}\n"
                f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )
            logger.critical("Kill switch activated via Telegram by %s", username)
        except Exception as exc:
            await update.message.reply_text(
                f"Kill switch activation failed: {exc}"
            )

    async def _cmd_health(self, update, context) -> None:
        """Handle /health — show system health."""
        lines = ["<b>System Health Report</b>", ""]

        # If a health callback is configured, use it
        if self._get_health:
            try:
                health = self._get_health()
            except Exception as exc:
                await update.message.reply_text(
                    f"Error fetching health: {exc}"
                )
                return

            overall = health.get("overall", "unknown")
            lines.append(
                f"Overall: {_status_icon(overall)} {overall.upper()}"
            )
            lines.append("")

            subsystems = health.get("subsystems", {})
            if subsystems:
                lines.append("<b>Subsystems</b>")
                for name, info in sorted(subsystems.items()):
                    status = info.get("status", "unknown")
                    latency = info.get("latency_ms", 0)
                    errors = info.get("error_count", 0)
                    msg = info.get("message", "")

                    line = f"  {_status_icon(status)} {_escape_html(name)}"
                    if latency > 0:
                        line += f" ({latency:.0f}ms)"
                    if errors > 0:
                        line += f" [errs: {errors}]"
                    if msg:
                        line += f"\n    {_escape_html(msg)}"
                    lines.append(line)
                lines.append("")

            checked_at = health.get("checked_at", "")
            if checked_at:
                lines.append(f"<i>Checked at {_escape_html(checked_at)}</i>")
        else:
            lines.append("Health callback not configured.")
            lines.append("Basic diagnostics:")

        # Always show bot-level diagnostics
        lines.extend([
            "",
            "<b>Bot Diagnostics</b>",
            f"  Bot uptime: {self._format_uptime()}",
            f"  Heartbeat interval: {self._heartbeat_interval}s",
            f"  Commands enabled: {self._commands_enabled}",
        ])

        # Memory usage (best-effort)
        try:
            import resource
            mem_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
            # On macOS, ru_maxrss is in bytes; on Linux, in KB
            import sys
            if sys.platform == "darwin":
                mem_mb = mem_mb / 1024
            lines.append(f"  Peak memory: {mem_mb:.1f} MB")
        except Exception:
            pass

        await update.message.reply_html("\n".join(lines))

    # ------------------------------------------------------------------
    # Background Tasks
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat to confirm the bot is alive."""
        while self._running:
            await asyncio.sleep(self._heartbeat_interval)
            if not self._running:
                break

            status = {}
            if self._get_status:
                try:
                    status = self._get_status()
                except Exception:
                    pass

            scan_count = status.get("scan_count", 0)
            mode = status.get("mode", "?")
            paused = status.get("paused", False)

            # Position count
            positions = []
            if self._get_positions:
                try:
                    positions = self._get_positions() or []
                except Exception:
                    pass

            # Safety
            safety = status.get("safety", {})
            daily_pnl = safety.get("daily_pnl", 0.0)

            state_tag = "PAUSED" if paused else "RUNNING"
            uptime = self._format_uptime()

            await self._send(
                f"<b>Heartbeat</b> [{state_tag}]\n"
                f"Uptime: {uptime} | Scans: {scan_count}\n"
                f"Positions: {len(positions)} | "
                f"Daily P&amp;L: {_pnl_emoji(daily_pnl)}${daily_pnl:,.2f}"
            )

    async def _daily_report_loop(self) -> None:
        """Send daily P&L report at the configured hour (UTC)."""
        while self._running:
            # Calculate seconds until next report time
            now = datetime.utcnow()
            target = now.replace(
                hour=self._daily_report_hour,
                minute=0,
                second=0,
                microsecond=0,
            )
            if target <= now:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()

            await asyncio.sleep(wait_seconds)
            if not self._running:
                break

            await self._send_daily_report()

    async def _health_report_loop(self) -> None:
        """Send periodic health reports."""
        while self._running:
            await asyncio.sleep(self._health_report_interval)
            if not self._running:
                break

            if not self._get_health:
                continue

            try:
                health = self._get_health()
            except Exception as exc:
                logger.error("Failed to get health for report: %s", exc)
                continue

            overall = health.get("overall", "unknown")
            subsystems = health.get("subsystems", {})

            # Only send detailed report if something is not OK
            problem_count = sum(
                1
                for info in subsystems.values()
                if info.get("status") in ("warning", "critical")
            )

            if problem_count == 0:
                await self._send(
                    f"<b>Health Check</b> [OK]\n"
                    f"All {len(subsystems)} subsystems healthy."
                )
            else:
                lines = [
                    f"<b>Health Check</b> "
                    f"[{_status_icon(overall)} {overall.upper()}]",
                    f"{problem_count} issue(s) detected:",
                    "",
                ]
                for name, info in sorted(subsystems.items()):
                    status = info.get("status", "unknown")
                    if status in ("warning", "critical"):
                        msg = info.get("message", "no details")
                        lines.append(
                            f"  {_status_icon(status)} "
                            f"{_escape_html(name)}: "
                            f"{_escape_html(msg)}"
                        )
                await self._send("\n".join(lines))

    async def _send_daily_report(self) -> None:
        """Generate and send the daily P&L report."""
        lines = [
            "<b>Daily Report</b>",
            f"Date: {datetime.utcnow().strftime('%Y-%m-%d')}",
            "",
        ]

        # P&L data
        if self._get_pnl:
            try:
                pnl_data = self._get_pnl()
                daily_pnl = pnl_data.get("daily_pnl", 0.0)
                daily_trades = pnl_data.get("daily_trades", 0)
                win_rate = pnl_data.get("win_rate", 0.0)
                best_trade = pnl_data.get("best_trade", 0.0)
                worst_trade = pnl_data.get("worst_trade", 0.0)

                lines.extend([
                    "<b>P&amp;L</b>",
                    f"  Daily: {_pnl_emoji(daily_pnl)}${daily_pnl:,.2f}",
                    f"  Trades: {daily_trades}",
                    f"  Win rate: {win_rate:.1f}%",
                    f"  Best: {_pnl_emoji(best_trade)}${best_trade:,.2f}",
                    f"  Worst: {_pnl_emoji(worst_trade)}${worst_trade:,.2f}",
                    "",
                ])
            except Exception as exc:
                lines.append(f"P&amp;L data unavailable: {_escape_html(str(exc))}")
                lines.append("")

        # Status data
        if self._get_status:
            try:
                status = self._get_status()
                scan_count = status.get("scan_count", 0)
                safety = status.get("safety", {})
                daily_loss_limit = safety.get("daily_loss_limit_pct", "?")

                lines.extend([
                    "<b>System</b>",
                    f"  Scans completed: {scan_count}",
                    f"  Daily loss limit: {daily_loss_limit}%",
                    f"  Uptime: {self._format_uptime()}",
                    "",
                ])
            except Exception:
                pass

        # Positions summary
        if self._get_positions:
            try:
                positions = self._get_positions() or []
                if positions:
                    total_unrealized = 0.0
                    for pos in positions:
                        entry = pos.get("entry_price", 0.0)
                        current = pos.get("current_price", 0.0)
                        size = pos.get("size", 0.0)
                        side = pos.get("side", "").upper()
                        if side == "LONG":
                            total_unrealized += (current - entry) * size
                        elif side == "SHORT":
                            total_unrealized += (entry - current) * size

                    lines.extend([
                        f"<b>Open Positions: {len(positions)}</b>",
                        f"  Unrealized P&amp;L: "
                        f"{_pnl_emoji(total_unrealized)}"
                        f"${total_unrealized:,.2f}",
                        "",
                    ])
                else:
                    lines.append("No open positions.")
                    lines.append("")
            except Exception:
                pass

        await self._send("\n".join(lines))

    # ------------------------------------------------------------------
    # Alert Methods (extend TelegramAlerts functionality)
    # ------------------------------------------------------------------

    async def alert_trade(
        self,
        asset: str,
        side: str,
        size: float,
        price: float,
        exchange: str,
        confidence: float = 0.0,
        strategy: str = "",
    ) -> bool:
        """Enhanced trade alert with confidence and strategy context."""
        if not self._alert_config.get("trade_executed", True):
            return False

        lines = [
            "<b>Trade Executed</b>",
            "",
            f"Asset: {_escape_html(asset)}",
            f"Side: {_escape_html(side.upper())}",
            f"Size: {size:.6f}",
            f"Price: ${price:,.4f}",
            f"Exchange: {_escape_html(exchange)}",
        ]
        if confidence > 0:
            lines.append(f"Confidence: {confidence:.1f}%")
        if strategy:
            lines.append(f"Strategy: {_escape_html(strategy)}")
        lines.append(
            f"\nTime: {datetime.utcnow().strftime('%H:%M:%S')} UTC"
        )

        return await self._send("\n".join(lines))

    async def alert_position_closed(
        self,
        asset: str,
        side: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        reason: str = "manual",
    ) -> bool:
        """Alert when a position is closed (stop, TP, or manual)."""
        if not self._alert_config.get("position_closed", True):
            return False

        pnl_pct = (
            ((exit_price - entry_price) / entry_price * 100)
            if entry_price > 0
            else 0.0
        )
        if side.upper() == "SHORT":
            pnl_pct = -pnl_pct

        result_tag = "WIN" if pnl >= 0 else "LOSS"

        lines = [
            f"<b>Position Closed [{result_tag}]</b>",
            "",
            f"Asset: {_escape_html(asset)}",
            f"Side: {_escape_html(side.upper())}",
            f"Entry: ${entry_price:,.4f}",
            f"Exit: ${exit_price:,.4f}",
            f"P&amp;L: {_pnl_emoji(pnl)}${pnl:,.2f} "
            f"({_pnl_emoji(pnl_pct)}{pnl_pct:.2f}%)",
            f"Reason: {_escape_html(reason)}",
            f"\nTime: {datetime.utcnow().strftime('%H:%M:%S')} UTC",
        ]

        return await self._send("\n".join(lines))

    async def alert_safety_triggered(
        self,
        limit_type: str,
        current_value: float,
        limit_value: float,
    ) -> bool:
        """Alert when a safety limit is hit."""
        if not self._alert_config.get("safety_triggered", True):
            return False

        lines = [
            "<b>SAFETY LIMIT TRIGGERED</b>",
            "",
            f"Limit: {_escape_html(limit_type)}",
            f"Current: {current_value:.2f}",
            f"Threshold: {limit_value:.2f}",
            "",
            "Trading may be restricted until the limit resets.",
            f"\nTime: {datetime.utcnow().strftime('%H:%M:%S')} UTC",
        ]

        return await self._send("\n".join(lines))

    async def alert_system_error(
        self,
        subsystem: str,
        error: str,
    ) -> bool:
        """Alert on system errors."""
        if not self._alert_config.get("system_error", True):
            return False

        lines = [
            "<b>System Error</b>",
            "",
            f"Subsystem: {_escape_html(subsystem)}",
            f"Error: {_escape_html(error)}",
            f"\nTime: {datetime.utcnow().strftime('%H:%M:%S')} UTC",
        ]

        return await self._send("\n".join(lines))

    async def alert_drawdown_warning(
        self,
        current_drawdown: float,
        limit: float,
    ) -> bool:
        """Alert on drawdown approaching limit."""
        if not self._alert_config.get("drawdown_warning", True):
            return False

        pct_of_limit = (
            (current_drawdown / limit * 100) if limit > 0 else 0.0
        )

        lines = [
            "<b>Drawdown Warning</b>",
            "",
            f"Current drawdown: {current_drawdown:.2f}%",
            f"Limit: {limit:.2f}%",
            f"Usage: {pct_of_limit:.0f}% of limit",
            "",
            "Consider reducing exposure.",
            f"\nTime: {datetime.utcnow().strftime('%H:%M:%S')} UTC",
        ]

        return await self._send("\n".join(lines))

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _format_uptime(self) -> str:
        """Return a human-readable uptime string."""
        if self._start_time is None:
            return "N/A"
        delta = datetime.utcnow() - self._start_time
        total_seconds = int(delta.total_seconds())
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0 or days > 0:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        return " ".join(parts)

    @property
    def is_running(self) -> bool:
        """Whether the bot is currently running."""
        return self._running

    @property
    def is_enabled(self) -> bool:
        """Whether the bot is enabled (has credentials)."""
        return self._enabled
