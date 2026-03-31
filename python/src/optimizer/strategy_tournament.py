"""Strategy tournament: parallel paper configs with promotion/demotion.

Runs N strategy configurations simultaneously on BacktestExchange,
ranks by Sortino ratio, promotes best to live after validation period.
"""

import asyncio
import logging
import random
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ContestantPerformance:
    sortino: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    trade_count: int = 0
    equity: float = 10000.0
    peak_equity: float = 10000.0


@dataclass
class StrategyContestant:
    id: str = ""
    name: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    status: str = "competing"  # competing, promoted, retired
    created_at: datetime = field(default_factory=datetime.utcnow)
    performance: ContestantPerformance = field(default_factory=ContestantPerformance)
    _exchange: Any = None
    _returns: List[float] = field(default_factory=list)
    _prev_equity: float = 10000.0

    @property
    def days_active(self) -> float:
        return (datetime.utcnow() - self.created_at).total_seconds() / 86400

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "params": self.params,
            "status": self.status, "days_active": round(self.days_active, 1),
            "performance": {
                "sortino": round(self.performance.sortino, 3),
                "return_pct": round(self.performance.total_return_pct, 2),
                "max_drawdown_pct": round(self.performance.max_drawdown_pct, 2),
                "win_rate": round(self.performance.win_rate, 1),
                "trade_count": self.performance.trade_count,
                "equity": round(self.performance.equity, 2),
            },
        }


class StrategyTournament:
    """Tournament coordinator for parallel strategy evaluation."""

    def __init__(self, config: Dict[str, Any]):
        cfg = config.get("optimizer", {}).get("tournament", {})
        self.min_contestants = cfg.get("min_contestants", 5)
        self.max_contestants = cfg.get("max_contestants", 20)
        self.min_days_promote = cfg.get("min_days_before_promotion", 7)
        self.max_days_demote = cfg.get("max_days_before_demotion", 14)
        self.promote_min_sortino = cfg.get("promotion_min_sortino", 0.5)
        self.demote_max_drawdown = cfg.get("demotion_max_drawdown_pct", 15.0)
        self.initial_balance = cfg.get("initial_balance", 10000.0)

        self._contestants: Dict[str, StrategyContestant] = {}
        self._db_path = config.get("system", {}).get("db_path", "data/trading.db")
        self._init_db()

    def _init_db(self) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""CREATE TABLE IF NOT EXISTS tournament_contestants (
                id TEXT PRIMARY KEY, name TEXT, params TEXT, status TEXT,
                created_at TEXT, sortino REAL, return_pct REAL,
                max_drawdown REAL, win_rate REAL, trade_count INTEGER, equity REAL)""")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Could not init tournament DB: %s", e)

    async def add_contestant(self, name: str, params: Dict[str, Any]) -> Optional[str]:
        if len(self._contestants) >= self.max_contestants:
            logger.warning("Tournament full (%d/%d)", len(self._contestants), self.max_contestants)
            return None

        from src.execution.abstract_exchange import BacktestExchange
        cid = str(uuid.uuid4())[:8]
        exchange = BacktestExchange(
            initial_balance=self.initial_balance, fee_pct=0.1, slippage_pct=0.05)
        await exchange.connect()

        contestant = StrategyContestant(
            id=cid, name=name, params=params,
            _exchange=exchange, _prev_equity=self.initial_balance,
            performance=ContestantPerformance(equity=self.initial_balance,
                                               peak_equity=self.initial_balance),
        )
        self._contestants[cid] = contestant
        logger.info("Added contestant '%s' (%s) with params: %s", name, cid, params)
        return cid

    def remove_contestant(self, contestant_id: str) -> bool:
        c = self._contestants.pop(contestant_id, None)
        if c:
            logger.info("Removed contestant '%s' (%s)", c.name, c.id)
            return True
        return False

    async def process_tick(self, symbol: str, price: float,
                           indicators: Optional[Dict[str, float]] = None) -> None:
        """Process one market tick through all active contestants."""
        indicators = indicators or {}
        for c in list(self._contestants.values()):
            if c.status != "competing" or c._exchange is None:
                continue
            try:
                await self._run_contestant_strategy(c, symbol, price, indicators)
                self._update_performance(c)
            except Exception as e:
                logger.debug("Contestant %s tick error: %s", c.id, e)

    async def _run_contestant_strategy(self, c: StrategyContestant, symbol: str,
                                        price: float, indicators: Dict) -> None:
        """Simple RSI-based strategy parameterized by contestant's params."""
        from src.execution.abstract_exchange import OrderRequest

        ex = c._exchange
        ex.set_prices({symbol: price})

        rsi = indicators.get("rsi_14", 50)
        rsi_oversold = c.params.get("rsi_oversold", 30)
        rsi_overbought = c.params.get("rsi_overbought", 70)
        position_pct = c.params.get("position_pct", 3.0)

        bal = await ex.get_balance()
        positions = await ex.get_positions()
        has_pos = len(positions) > 0

        if not has_pos and rsi < rsi_oversold and bal.free_usd > 100:
            size = bal.free_usd * position_pct / 100 / price
            if size > 0:
                await ex.place_order(OrderRequest(
                    symbol=symbol, side="buy", order_type="market", amount=size))

        elif has_pos and rsi > rsi_overbought:
            for pos in positions:
                size = pos.get("size", 0)
                if size > 0:
                    await ex.place_order(OrderRequest(
                        symbol=symbol, side="sell", order_type="market", amount=size))

    def _update_performance(self, c: StrategyContestant) -> None:
        if c._exchange is None:
            return
        stats = c._exchange.get_stats()
        equity = stats.get("final_equity", c._prev_equity)

        if c._prev_equity > 0:
            ret = (equity - c._prev_equity) / c._prev_equity
            c._returns.append(ret)
        c._prev_equity = equity

        c.performance.equity = equity
        c.performance.peak_equity = max(c.performance.peak_equity, equity)
        c.performance.total_return_pct = stats.get("total_return_pct", 0)
        c.performance.max_drawdown_pct = abs(stats.get("max_drawdown_pct", 0))
        c.performance.trade_count = stats.get("trade_count", 0)
        c.performance.win_rate = stats.get("win_rate", 0)

        # Sortino ratio
        if len(c._returns) > 10:
            arr = np.array(c._returns)
            downside = arr[arr < 0]
            ds_std = np.std(downside) if len(downside) > 1 else 1e-6
            c.performance.sortino = float(np.mean(arr) / ds_std * np.sqrt(252)) if ds_std > 0 else 0

    def get_leaderboard(self) -> List[Dict[str, Any]]:
        active = [c for c in self._contestants.values() if c.status == "competing"]
        active.sort(key=lambda c: c.performance.sortino, reverse=True)
        return [c.to_dict() for c in active]

    def get_promotion_candidate(self) -> Optional[StrategyContestant]:
        for c in sorted(self._contestants.values(),
                        key=lambda x: x.performance.sortino, reverse=True):
            if (c.status == "competing"
                    and c.days_active >= self.min_days_promote
                    and c.performance.sortino >= self.promote_min_sortino
                    and c.performance.total_return_pct > 0
                    and c.performance.max_drawdown_pct < self.demote_max_drawdown):
                return c
        return None

    def get_demotion_candidates(self) -> List[StrategyContestant]:
        return [c for c in self._contestants.values()
                if c.status == "competing"
                and c.days_active >= self.max_days_demote
                and (c.performance.sortino < 0 or c.performance.max_drawdown_pct > self.demote_max_drawdown)]

    def promote_contestant(self, contestant_id: str) -> bool:
        c = self._contestants.get(contestant_id)
        if c and c.status == "competing":
            c.status = "promoted"
            logger.info("PROMOTED contestant '%s' (%s) — sortino=%.2f return=%.1f%%",
                        c.name, c.id, c.performance.sortino, c.performance.total_return_pct)
            self._persist_contestant(c)
            return True
        return False

    def run_tournament_cycle(self) -> Dict[str, Any]:
        """Check promotions/demotions, seed replacements."""
        actions = {"promoted": [], "retired": [], "seeded": []}

        # Demote underperformers
        for c in self.get_demotion_candidates():
            c.status = "retired"
            actions["retired"].append(c.id)
            logger.info("RETIRED contestant '%s' (%s)", c.name, c.id)

        # Clean up retired
        self._contestants = {k: v for k, v in self._contestants.items() if v.status != "retired"}

        return actions

    async def seed_from_optimizer(self, best_params: Dict[str, Any], n: int = 3) -> List[str]:
        """Create N contestants from random perturbation of best params."""
        ids = []
        for i in range(n):
            perturbed = {}
            for k, v in best_params.items():
                if isinstance(v, (int, float)):
                    noise = random.uniform(-0.15, 0.15)
                    perturbed[k] = type(v)(v * (1 + noise))
                else:
                    perturbed[k] = v
            cid = await self.add_contestant(f"seed_{i}", perturbed)
            if cid:
                ids.append(cid)
        return ids

    def _persist_contestant(self, c: StrategyContestant) -> None:
        try:
            import json
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "INSERT OR REPLACE INTO tournament_contestants VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (c.id, c.name, json.dumps(c.params), c.status, c.created_at.isoformat(),
                 c.performance.sortino, c.performance.total_return_pct,
                 c.performance.max_drawdown_pct, c.performance.win_rate,
                 c.performance.trade_count, c.performance.equity))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Could not persist contestant: %s", e)

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "total_contestants": len(self._contestants),
            "competing": sum(1 for c in self._contestants.values() if c.status == "competing"),
            "promoted": sum(1 for c in self._contestants.values() if c.status == "promoted"),
            "leaderboard_top3": self.get_leaderboard()[:3],
        }
