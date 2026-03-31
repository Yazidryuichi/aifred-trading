"""Telegram bot command handler for /kill, /resume, /status."""

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class TelegramCommandHandler:
    """Handles incoming Telegram commands for trading control.

    Requires polling or webhook setup to receive updates.
    """

    def __init__(self, bot_token: str, chat_id: str,
                 safety_ref: Any, orchestrator_ref: Any):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._safety = safety_ref
        self._orchestrator = orchestrator_ref
        self._enabled = bool(bot_token and chat_id)
        self._commands: Dict[str, Callable] = {
            "/kill": self._handle_kill,
            "/resume": self._handle_resume,
            "/status": self._handle_status,
        }

    async def poll_updates(self, send_fn: Callable) -> None:
        """Poll for new messages and handle commands.

        Called periodically from the orchestrator loop.
        send_fn: async callable(message: str) to send replies.
        """
        if not self._enabled:
            return

        try:
            from telegram import Bot
            bot = Bot(token=self.bot_token)
            updates = await bot.get_updates(
                timeout=1,
                allowed_updates=["message"],
            )
            for update in updates:
                if not update.message or not update.message.text:
                    continue
                if str(update.message.chat_id) != str(self.chat_id):
                    continue
                text = update.message.text.strip().lower()
                if text in self._commands:
                    response = self._commands[text]()
                    await send_fn(response)
                # Acknowledge the update
                await bot.get_updates(offset=update.update_id + 1, timeout=1)
        except ImportError:
            logger.debug("python-telegram-bot not installed, commands disabled")
        except Exception as e:
            logger.debug("Telegram command poll error: %s", e)

    def _handle_kill(self) -> str:
        self._safety.activate_kill_switch("telegram /kill command")
        return (
            "<b>KILL SWITCH ACTIVATED</b>\n"
            "All trading halted immediately.\n"
            "Use /resume to restart trading."
        )

    def _handle_resume(self) -> str:
        self._safety.deactivate_kill_switch()
        return (
            "<b>TRADING RESUMED</b>\n"
            "Kill switch deactivated. Normal trading will resume on next scan."
        )

    def _handle_status(self) -> str:
        status = self._safety.status
        mode = "LIVE" if not getattr(self._orchestrator, '_paper_mode', True) else "PAPER"
        positions = len(getattr(self._orchestrator, '_positions', {}))
        killed = status.get("killed", False)
        daily_pnl = status.get("daily_realized_pnl", 0.0)
        weekly_pnl = status.get("weekly_realized_pnl", 0.0)

        return (
            f"<b>AIFred Status</b>\n"
            f"Mode: {mode}\n"
            f"Kill Switch: {'ACTIVE' if killed else 'OFF'}\n"
            f"Open Positions: {positions}\n"
            f"Daily P&L: ${daily_pnl:+.2f}\n"
            f"Weekly P&L: ${weekly_pnl:+.2f}\n"
            f"Daily Trades: {status.get('daily_trade_count', 0)}"
        )
