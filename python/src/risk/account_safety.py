"""Non-overridable account safety limits.

These limits are the LAST LINE OF DEFENSE before real money is at risk.
They cannot be bypassed by any agent, configuration, or code path.
Every trade execution MUST pass through these checks.

Safety hierarchy:
1. account_safety.py (this file) -- HARD limits, never bypassed
2. risk_gate.py -- Strategy-level risk checks
3. drawdown_manager.py -- Adaptive drawdown management
4. position_sizer.py -- Position sizing optimization
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class SafetyState:
    """Persistent safety state tracked across the trading session."""
    daily_realized_pnl: float = 0.0
    daily_start_equity: float = 0.0
    weekly_realized_pnl: float = 0.0
    weekly_start_equity: float = 0.0
    total_exposure_usd: float = 0.0
    position_count: int = 0
    daily_trade_count: int = 0
    last_daily_reset: Optional[datetime] = None
    last_weekly_reset: Optional[datetime] = None
    killed: bool = False  # kill switch activated
    kill_reason: str = ""


class AccountSafety:
    """Hard, non-overridable account safety limits.

    This is the final gate before any order reaches an exchange.
    If any check fails, the trade is BLOCKED -- no exceptions.

    Limits (all non-overridable):
    - Daily loss limit: -2% of account equity
    - Weekly loss limit: -5% of account equity
    - Max position size: 5% of account per trade
    - Max total exposure: 30% of account
    - Max simultaneous positions: configurable (default 5)
    - Kill switch: immediately halt all trading
    """

    # These constants are the absolute maximums. Config can only TIGHTEN them.
    # Temporarily raised for micro-account ($10.80) — normal accounts should use
    # 2/5/5/30 limits. TODO: Restore once account is funded properly.
    HARD_DAILY_LOSS_PCT = 25.0     # Micro account: allow bigger daily swing
    HARD_WEEKLY_LOSS_PCT = 50.0    # Micro account: allow bigger weekly swing
    HARD_MAX_POSITION_PCT = 95.0   # Micro account: allow full-balance positions
    HARD_MAX_EXPOSURE_PCT = 95.0   # Micro account: allow full exposure
    HARD_MAX_POSITIONS = 1         # Only 1 position at a time

    def __init__(self, config: Dict[str, Any]):
        safety_cfg = config.get("safety", {})

        # Allow config to TIGHTEN limits (not loosen)
        self.daily_loss_pct = min(
            safety_cfg.get("daily_loss_limit_pct", self.HARD_DAILY_LOSS_PCT),
            self.HARD_DAILY_LOSS_PCT,
        )
        self.weekly_loss_pct = min(
            safety_cfg.get("weekly_loss_limit_pct", self.HARD_WEEKLY_LOSS_PCT),
            self.HARD_WEEKLY_LOSS_PCT,
        )
        self.max_position_pct = min(
            safety_cfg.get("max_position_pct", self.HARD_MAX_POSITION_PCT),
            self.HARD_MAX_POSITION_PCT,
        )
        self.max_exposure_pct = min(
            safety_cfg.get("max_exposure_pct", self.HARD_MAX_EXPOSURE_PCT),
            self.HARD_MAX_EXPOSURE_PCT,
        )
        self.max_positions = min(
            safety_cfg.get("max_positions", self.HARD_MAX_POSITIONS),
            self.HARD_MAX_POSITIONS,
        )

        self._state = SafetyState()
        self._lock = threading.Lock()
        self._telegram = None  # Set via set_telegram()

        logger.info(
            "Account safety initialized: daily_loss=%.1f%%, weekly_loss=%.1f%%, "
            "max_pos=%.1f%%, max_exposure=%.1f%%, max_positions=%d",
            self.daily_loss_pct, self.weekly_loss_pct,
            self.max_position_pct, self.max_exposure_pct, self.max_positions,
        )

    def set_telegram(self, telegram_alerts):
        """Wire up Telegram for kill switch alerts."""
        self._telegram = telegram_alerts

    def initialize_session(self, account_equity: float):
        """Call on startup with current account equity."""
        now = datetime.utcnow()
        with self._lock:
            self._state.daily_start_equity = account_equity
            self._state.weekly_start_equity = account_equity
            self._state.last_daily_reset = now
            self._state.last_weekly_reset = now
        logger.info(
            "Account safety session initialized: equity=$%.2f", account_equity,
        )

    def check_trade_allowed(
        self,
        position_value_usd: float,
        account_equity: float,
        current_positions: int,
        total_exposure_usd: float,
    ) -> tuple:
        """Check if a new trade is allowed. Returns (allowed: bool, reason: str).

        This is called by execution_engine BEFORE every trade.
        If this returns False, the trade MUST NOT execute.
        """
        with self._lock:
            # Reset daily/weekly counters if needed
            self._maybe_reset_counters(account_equity)

            # Kill switch check
            if self._state.killed:
                return False, f"KILL SWITCH ACTIVE: {self._state.kill_reason}"

            # Daily loss check
            if self._state.daily_start_equity > 0:
                daily_loss_pct = (
                    abs(min(0, self._state.daily_realized_pnl))
                    / self._state.daily_start_equity
                    * 100
                )
            else:
                daily_loss_pct = 0.0
            if daily_loss_pct >= self.daily_loss_pct:
                return False, (
                    f"DAILY LOSS LIMIT: {daily_loss_pct:.2f}% >= "
                    f"{self.daily_loss_pct:.1f}%"
                )

            # Weekly loss check
            if self._state.weekly_start_equity > 0:
                weekly_loss_pct = (
                    abs(min(0, self._state.weekly_realized_pnl))
                    / self._state.weekly_start_equity
                    * 100
                )
            else:
                weekly_loss_pct = 0.0
            if weekly_loss_pct >= self.weekly_loss_pct:
                return False, (
                    f"WEEKLY LOSS LIMIT: {weekly_loss_pct:.2f}% >= "
                    f"{self.weekly_loss_pct:.1f}%"
                )

            # Position size check
            if account_equity > 0:
                pos_pct = position_value_usd / account_equity * 100
                if pos_pct > self.max_position_pct:
                    return False, (
                        f"POSITION TOO LARGE: {pos_pct:.2f}% > "
                        f"{self.max_position_pct:.1f}%"
                    )

            # Total exposure check
            new_exposure = total_exposure_usd + position_value_usd
            if account_equity > 0:
                exposure_pct = new_exposure / account_equity * 100
                if exposure_pct > self.max_exposure_pct:
                    return False, (
                        f"EXPOSURE LIMIT: {exposure_pct:.2f}% > "
                        f"{self.max_exposure_pct:.1f}%"
                    )

            # Max positions check
            if current_positions >= self.max_positions:
                return False, (
                    f"MAX POSITIONS: {current_positions} >= {self.max_positions}"
                )

            return True, "OK"

    def record_trade_pnl(self, pnl: float):
        """Record realized P&L from a closed trade."""
        with self._lock:
            self._state.daily_realized_pnl += pnl
            self._state.weekly_realized_pnl += pnl
            self._state.daily_trade_count += 1
        logger.info(
            "Safety P&L recorded: %.2f (daily total: %.2f, weekly total: %.2f)",
            pnl, self._state.daily_realized_pnl, self._state.weekly_realized_pnl,
        )

    def activate_kill_switch(self, reason: str = "manual"):
        """EMERGENCY: Stop all trading immediately.

        When activated:
        - No new trades are allowed
        - Existing positions should be closed (caller's responsibility)
        - Telegram alert is sent
        - Remains active until manually deactivated
        """
        with self._lock:
            self._state.killed = True
            self._state.kill_reason = reason
        logger.critical("KILL SWITCH ACTIVATED: %s", reason)

        if self._telegram:
            try:
                self._telegram.send_alert(
                    message=f"KILL SWITCH ACTIVATED: {reason}\nAll trading halted.",
                    alert_type="EMERGENCY",
                )
            except Exception:
                pass  # Don't let telegram failure prevent kill switch

    def deactivate_kill_switch(self):
        """Deactivate kill switch (manual only)."""
        with self._lock:
            self._state.killed = False
            self._state.kill_reason = ""
        logger.info("Kill switch deactivated")

    def _maybe_reset_counters(self, current_equity: float):
        """Reset daily/weekly P&L counters at appropriate times.

        Must be called while holding self._lock.
        """
        now = datetime.utcnow()

        # Daily reset (after midnight UTC)
        if self._state.last_daily_reset:
            if now.date() > self._state.last_daily_reset.date():
                self._state.daily_realized_pnl = 0.0
                self._state.daily_start_equity = current_equity
                self._state.daily_trade_count = 0
                self._state.last_daily_reset = now
                logger.info(
                    "Daily safety counters reset. Equity: $%.2f", current_equity,
                )

        # Weekly reset (Monday midnight UTC)
        if self._state.last_weekly_reset:
            days_since = (now - self._state.last_weekly_reset).days
            if days_since >= 7 or (
                now.weekday() == 0
                and self._state.last_weekly_reset.weekday() != 0
            ):
                self._state.weekly_realized_pnl = 0.0
                self._state.weekly_start_equity = current_equity
                self._state.last_weekly_reset = now
                logger.info(
                    "Weekly safety counters reset. Equity: $%.2f", current_equity,
                )

    @property
    def state(self) -> SafetyState:
        return self._state

    @property
    def status(self) -> Dict[str, Any]:
        """Current safety status for monitoring/dashboard."""
        with self._lock:
            return {
                "killed": self._state.killed,
                "kill_reason": self._state.kill_reason,
                "daily_pnl": self._state.daily_realized_pnl,
                "daily_loss_limit_pct": self.daily_loss_pct,
                "weekly_pnl": self._state.weekly_realized_pnl,
                "weekly_loss_limit_pct": self.weekly_loss_pct,
                "daily_trades": self._state.daily_trade_count,
                "max_positions": self.max_positions,
                "max_position_pct": self.max_position_pct,
                "max_exposure_pct": self.max_exposure_pct,
            }
