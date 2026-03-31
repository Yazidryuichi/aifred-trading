"""Dynamic Kelly criterion calibration from real trade history.

Replaces hardcoded Kelly parameters with rolling window actuals:
- win_rate: computed from last N trades
- avg_win: average winning trade P&L %
- avg_loss: average losing trade P&L %
- Kelly fraction: f* = (p*b - q) / b

Applies fractional Kelly (default 50%) and adjustments for tier, volatility, drawdown.
"""

import logging
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    asset: str
    side: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    strategy: str = ""
    closed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class KellyState:
    win_rate: float = 0.5
    avg_win: float = 1.0
    avg_loss: float = 1.0
    kelly_fraction: float = 0.0
    fractional_kelly: float = 0.0
    sample_size: int = 0
    is_calibrated: bool = False
    last_updated: Optional[datetime] = None


class DynamicKelly:
    """Dynamic Kelly criterion that calibrates from trade history."""

    def __init__(self, config: Dict[str, Any]):
        cfg = config.get("risk", {}).get("dynamic_kelly", {})
        self.lookback_trades = cfg.get("lookback_trades", 50)
        self.lookback_days = cfg.get("lookback_days", 30)
        self.fractional_multiplier = cfg.get("fractional_multiplier", 0.5)
        self.min_samples = cfg.get("min_samples", 20)
        self.max_position_pct = cfg.get("max_position_pct", 5.0)
        self.min_position_pct = cfg.get("min_position_pct", 0.5)
        self.default_win_rate = cfg.get("default_win_rate", 0.55)
        self.default_avg_win = cfg.get("default_avg_win", 2.0)
        self.default_avg_loss = cfg.get("default_avg_loss", 1.0)
        self.drawdown_shrink_start = cfg.get("drawdown_shrink_start_pct", 3.0)
        self.drawdown_shrink_max = cfg.get("drawdown_shrink_max_pct", 8.0)
        self.tier_multipliers: Dict[str, float] = cfg.get("tier_multipliers", {
            "A+": 1.0, "A": 0.75, "B": 0.5, "C": 0.0,
        })
        self._trades: List[TradeRecord] = []
        self._state = KellyState()
        self._lock = threading.Lock()
        self._db_path = config.get("system", {}).get("db_path", "data/trading.db")
        self._init_db()
        self._load_history()

    def _init_db(self) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""CREATE TABLE IF NOT EXISTS kelly_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset TEXT NOT NULL, side TEXT NOT NULL,
                entry_price REAL NOT NULL, exit_price REAL NOT NULL,
                size REAL NOT NULL, pnl REAL NOT NULL, pnl_pct REAL NOT NULL,
                strategy TEXT, closed_at TEXT NOT NULL)""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kelly_closed ON kelly_trades(closed_at)")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Could not init Kelly DB: %s", e)

    def _load_history(self) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            cutoff = (datetime.utcnow() - timedelta(days=self.lookback_days)).isoformat()
            rows = conn.execute(
                "SELECT asset,side,entry_price,exit_price,size,pnl,pnl_pct,strategy,closed_at "
                "FROM kelly_trades WHERE closed_at>=? ORDER BY closed_at DESC LIMIT ?",
                (cutoff, self.lookback_trades)).fetchall()
            conn.close()
            self._trades = [TradeRecord(r[0],r[1],r[2],r[3],r[4],r[5],r[6],r[7] or "",
                            datetime.fromisoformat(r[8])) for r in rows]
            self._recalibrate()
            logger.info("Loaded %d trades for Kelly calibration", len(self._trades))
        except Exception as e:
            logger.warning("Could not load Kelly history: %s", e)

    def record_trade(self, record: TradeRecord) -> None:
        with self._lock:
            self._trades.append(record)
            try:
                conn = sqlite3.connect(self._db_path)
                conn.execute(
                    "INSERT INTO kelly_trades (asset,side,entry_price,exit_price,size,pnl,pnl_pct,strategy,closed_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (record.asset, record.side, record.entry_price, record.exit_price,
                     record.size, record.pnl, record.pnl_pct, record.strategy, record.closed_at.isoformat()))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.warning("Could not persist Kelly trade: %s", e)
            cutoff = datetime.utcnow() - timedelta(days=self.lookback_days)
            self._trades = [t for t in self._trades if t.closed_at >= cutoff][-self.lookback_trades:]
            self._recalibrate()

    def _recalibrate(self) -> None:
        if not self._trades:
            self._state = KellyState()
            return
        wins = [t for t in self._trades if t.pnl > 0]
        losses = [t for t in self._trades if t.pnl <= 0]
        n = len(self._trades)
        win_rate = len(wins) / n if n > 0 else 0.5
        avg_win = sum(t.pnl_pct for t in wins) / len(wins) if wins else self.default_avg_win
        avg_loss = abs(sum(t.pnl_pct for t in losses) / len(losses)) if losses else self.default_avg_loss
        b = avg_win / avg_loss if avg_loss > 0 else 1.0
        kelly_raw = max(0.0, (win_rate * b - (1 - win_rate)) / b) if b > 0 else 0.0
        fractional = kelly_raw * self.fractional_multiplier
        self._state = KellyState(win_rate=win_rate, avg_win=avg_win, avg_loss=avg_loss,
            kelly_fraction=kelly_raw, fractional_kelly=fractional, sample_size=n,
            is_calibrated=n >= self.min_samples, last_updated=datetime.utcnow())
        if self._state.is_calibrated:
            logger.info("Kelly recalibrated: wr=%.1f%% kelly=%.3f frac=%.3f (n=%d)",
                        win_rate*100, kelly_raw, fractional, n)

    def get_position_size(self, account_equity: float, signal_confidence: float = 80.0,
                          signal_tier: str = "A", volatility_regime: str = "normal",
                          current_drawdown_pct: float = 0.0) -> float:
        with self._lock:
            if self._state.is_calibrated:
                base_pct = self._state.fractional_kelly * 100
            else:
                b = self.default_avg_win / self.default_avg_loss
                kelly = max(0, (self.default_win_rate * b - (1-self.default_win_rate)) / b)
                base_pct = kelly * self.fractional_multiplier * 100
            tier_mult = self.tier_multipliers.get(signal_tier, 0.5)
            conf_scale = max(0.0, min(1.0, (signal_confidence - 70) / 30))
            vol_mult = {"low": 1.05, "normal": 1.0, "high": 0.7, "extreme": 0.3}.get(volatility_regime, 1.0)
            dd_mult = 1.0
            if current_drawdown_pct > self.drawdown_shrink_start:
                shrink_range = self.drawdown_shrink_max - self.drawdown_shrink_start
                if shrink_range > 0:
                    factor = min(1.0, (current_drawdown_pct - self.drawdown_shrink_start) / shrink_range)
                    dd_mult = max(0.1, 1 - factor * 0.8)
            pct = max(self.min_position_pct, min(self.max_position_pct,
                      base_pct * tier_mult * conf_scale * vol_mult * dd_mult))
            return account_equity * pct / 100

    @property
    def state(self) -> KellyState:
        return self._state

    @property
    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "calibrated": self._state.is_calibrated,
                "sample_size": self._state.sample_size,
                "min_samples": self.min_samples,
                "win_rate": round(self._state.win_rate * 100, 1),
                "avg_win_pct": round(self._state.avg_win, 2),
                "avg_loss_pct": round(self._state.avg_loss, 2),
                "kelly_fraction": round(self._state.kelly_fraction, 4),
                "fractional_kelly": round(self._state.fractional_kelly, 4),
                "last_updated": self._state.last_updated.isoformat() if self._state.last_updated else None,
            }
