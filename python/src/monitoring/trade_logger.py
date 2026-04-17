"""Structured trade logging to SQLite with query interface."""

import json
import logging
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.utils.types import TradeResult, TradeStatus

logger = logging.getLogger(__name__)


class TradeLogger:
    """Persists every trade to SQLite with full metadata for analysis."""

    def __init__(self, db_path: str = "data/trading.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create tables on first run."""
        try:
            conn = self._get_conn()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT,
                    asset TEXT NOT NULL,
                    asset_class TEXT,
                    direction TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT,
                    size REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    fill_price REAL,
                    fill_size REAL,
                    slippage REAL DEFAULT 0,
                    fees REAL DEFAULT 0,
                    pnl REAL,
                    status TEXT NOT NULL,
                    exchange TEXT,
                    signal_source TEXT,
                    confidence REAL,
                    model_version TEXT,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            # Migration: add signal_sources column for multi-source attribution
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN signal_sources TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_asset ON trades(asset)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)
            """)
            conn.commit()
            conn.close()
            logger.info("Trade logger initialized (db=%s)", self.db_path)
        except Exception as e:
            logger.error("Failed to initialize trade logger DB: %s", e)

    def log_trade(self, result: TradeResult, signal_sources: Optional[List[str]] = None) -> int:
        """Log a completed trade result. Returns the row ID.

        Args:
            result: The TradeResult from execution.
            signal_sources: List of signal source identifiers that contributed
                to this trade (e.g. ["lstm_sell", "bb_squeeze_release",
                "whale_accumulation", "oi_bullish"]).
        """
        proposal = result.proposal
        signal = proposal.signal

        side = "buy"
        if proposal.direction.value in ("SELL", "STRONG_SELL"):
            side = "sell"

        # Build signal_sources JSON string
        sources_json = None
        if signal_sources:
            sources_json = json.dumps(signal_sources)
        elif signal and signal.metadata:
            # Auto-extract signal sources from metadata if not explicitly provided
            auto_sources = self._extract_signal_sources(signal)
            if auto_sources:
                sources_json = json.dumps(auto_sources)

        try:
            conn = self._get_conn()
            cursor = conn.execute(
                """INSERT INTO trades
                   (order_id, asset, asset_class, direction, side, order_type,
                    size, entry_price, stop_loss, take_profit,
                    fill_price, fill_size, slippage, fees,
                    status, exchange, signal_source, confidence,
                    entry_time, signal_sources)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.order_id,
                    proposal.asset,
                    proposal.asset_class.value if proposal.asset_class else None,
                    proposal.direction.value,
                    side,
                    proposal.order_type.value if proposal.order_type else None,
                    proposal.position_size,
                    proposal.entry_price,
                    proposal.stop_loss,
                    proposal.take_profit,
                    result.fill_price,
                    result.fill_size,
                    result.slippage,
                    result.fees,
                    result.status.value,
                    result.exchange,
                    signal.source if signal else None,
                    signal.confidence if signal else None,
                    result.timestamp.isoformat(),
                    sources_json,
                ),
            )
            conn.commit()
            row_id = cursor.lastrowid
            conn.close()
            logger.info("Trade logged: id=%d asset=%s status=%s sources=%s",
                        row_id, proposal.asset, result.status.value,
                        signal_sources or "auto")
            return row_id
        except Exception as e:
            logger.error("Failed to log trade: %s", e)
            return -1

    @staticmethod
    def _extract_signal_sources(signal) -> List[str]:
        """Auto-extract signal source identifiers from signal metadata."""
        sources = []
        md = signal.metadata or {}

        # Source from signal itself
        if signal.source:
            sources.append(signal.source)

        # ML model predictions
        ml_preds = md.get("ml_predictions", {})
        for model_name, pred in ml_preds.items():
            direction = pred if isinstance(pred, str) else pred.get("direction", "")
            if direction:
                sources.append(f"{model_name}_{direction.lower()}")

        # Whale signal
        whale = md.get("whale_signal", {})
        if isinstance(whale, dict) and whale.get("type"):
            sources.append(f"whale_{whale.get('direction', 'unknown')}")

        # Meta-reasoning
        meta = md.get("meta_reasoning", {})
        if isinstance(meta, dict) and meta.get("action"):
            sources.append(f"meta_{meta['action'].lower()}")

        # Confluences info
        confluences = md.get("confluences", 0)
        if confluences:
            sources.append(f"confluences_{confluences}")

        return sources

    def log_exit(self, order_id: str, exit_price: float, pnl: float,
                 exit_time: Optional[datetime] = None) -> None:
        """Update a trade record with exit information."""
        exit_t = (exit_time or datetime.utcnow()).isoformat()
        try:
            conn = self._get_conn()
            conn.execute(
                """UPDATE trades SET exit_price = ?, pnl = ?, exit_time = ?,
                   status = 'filled' WHERE order_id = ?""",
                (exit_price, pnl, exit_t, order_id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Failed to log exit for %s: %s", order_id, e)

    # --- Query interface ---

    def get_trades(self, start_date: Optional[str] = None,
                   end_date: Optional[str] = None,
                   asset: Optional[str] = None,
                   strategy: Optional[str] = None,
                   limit: int = 100) -> List[Dict[str, Any]]:
        """Query trades with optional filters."""
        query = "SELECT * FROM trades WHERE 1=1"
        params: List[Any] = []

        if start_date:
            query += " AND entry_time >= ?"
            params.append(start_date)
        if end_date:
            query += " AND entry_time <= ?"
            params.append(end_date)
        if asset:
            query += " AND asset = ?"
            params.append(asset)
        if strategy:
            query += " AND signal_source = ?"
            params.append(strategy)

        query += " ORDER BY entry_time DESC LIMIT ?"
        params.append(limit)

        try:
            conn = self._get_conn()
            rows = conn.execute(query, params).fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error("Failed to query trades: %s", e)
            return []

    def get_trade_count(self) -> int:
        try:
            conn = self._get_conn()
            count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            conn.close()
            return count
        except Exception:
            return 0

    def get_winning_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM trades WHERE pnl > 0 ORDER BY pnl DESC LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception:
            return []

    def get_losing_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM trades WHERE pnl < 0 ORDER BY pnl ASC LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception:
            return []

    def get_attribution_summary(self) -> Dict[str, Dict]:
        """Get P&L attribution by signal source.

        Parses the signal_sources JSON column and attributes each trade's P&L
        to every signal source that contributed to it.

        Returns:
            {signal_source: {trades: N, total_pnl: X, win_rate: Y, avg_pnl: Z}}
        """
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT signal_sources, signal_source, pnl FROM trades "
                "WHERE pnl IS NOT NULL"
            ).fetchall()
            conn.close()
        except Exception as e:
            logger.error("Failed to get attribution summary: %s", e)
            return {}

        attribution: Dict[str, Dict] = {}

        for row in rows:
            pnl = row["pnl"] or 0.0
            sources = []

            # Parse JSON signal_sources column
            if row["signal_sources"]:
                try:
                    sources = json.loads(row["signal_sources"])
                except (json.JSONDecodeError, TypeError):
                    pass

            # Fall back to single signal_source column
            if not sources and row["signal_source"]:
                sources = [row["signal_source"]]

            for src in sources:
                if src not in attribution:
                    attribution[src] = {
                        "trades": 0,
                        "total_pnl": 0.0,
                        "wins": 0,
                    }
                attribution[src]["trades"] += 1
                attribution[src]["total_pnl"] += pnl
                if pnl > 0:
                    attribution[src]["wins"] += 1

        # Compute derived metrics
        for src, stats in attribution.items():
            n = stats["trades"]
            stats["win_rate"] = round(stats["wins"] / n * 100, 1) if n > 0 else 0.0
            stats["avg_pnl"] = round(stats["total_pnl"] / n, 4) if n > 0 else 0.0
            stats["total_pnl"] = round(stats["total_pnl"], 4)
            del stats["wins"]  # internal counter, not exposed

        return attribution

    def get_pnl_summary(self) -> Dict[str, float]:
        """Get aggregate P&L statistics."""
        try:
            conn = self._get_conn()
            row = conn.execute("""
                SELECT
                    COALESCE(SUM(pnl), 0) as total_pnl,
                    COALESCE(AVG(pnl), 0) as avg_pnl,
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                    COALESCE(SUM(fees), 0) as total_fees,
                    COALESCE(AVG(slippage), 0) as avg_slippage
                FROM trades WHERE pnl IS NOT NULL
            """).fetchone()
            conn.close()
            total = row["total_trades"] or 1
            wins = row["winning_trades"] or 0
            return {
                "total_pnl": row["total_pnl"],
                "avg_pnl": row["avg_pnl"],
                "total_trades": row["total_trades"],
                "winning_trades": wins,
                "losing_trades": row["losing_trades"] or 0,
                "win_rate": wins / total * 100 if total > 0 else 0,
                "total_fees": row["total_fees"],
                "avg_slippage": row["avg_slippage"],
            }
        except Exception as e:
            logger.error("Failed to get P&L summary: %s", e)
            return {}
