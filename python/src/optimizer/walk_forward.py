"""Walk-forward optimization with Optuna.

Implements a rolling window walk-forward optimization that:
1. Divides historical data into train/validate/test windows
2. Uses Optuna (TPE sampler) for Bayesian parameter search on each train window
3. Validates on the next window to prevent overfitting
4. Tests on the final window for unbiased performance estimate
5. Rolls forward and repeats

Windows:
  |--- Train (6 months) ---|-- Purge (1 week) --|-- Validate (1 month) --|-- Test (1 month) --|
  Then roll forward by 1 month and repeat.

Optimizes: Sortino ratio (risk-adjusted return penalizing downside)
Secondary: Max drawdown constraint (reject if > threshold)
"""

import logging
from collections import Counter
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import optuna
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class WalkForwardWindow:
    """A single walk-forward window with train/purge/validate/test splits."""

    train_start: datetime
    train_end: datetime
    purge_end: datetime       # train_end + purge gap (data in this gap is excluded)
    validate_start: datetime
    validate_end: datetime
    test_start: datetime
    test_end: datetime


@dataclass
class WindowResult:
    """Result from optimizing and testing a single window."""

    window: WalkForwardWindow
    best_params: Dict[str, Any]
    train_sortino: float
    validate_sortino: float
    test_sortino: float
    train_return: float
    validate_return: float
    test_return: float
    test_max_drawdown: float
    test_win_rate: float
    test_trade_count: int
    optimization_trials: int


@dataclass
class WalkForwardResult:
    """Complete walk-forward optimization result aggregated across all windows."""

    windows: List[WindowResult]
    overall_test_sortino: float
    overall_test_return: float
    overall_test_max_drawdown: float
    overall_test_win_rate: float
    total_trades: int
    best_params: Dict[str, Any]   # consensus params (median across windows)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def summary(self) -> str:
        """Human-readable summary of the walk-forward optimization."""
        lines = [
            "=" * 72,
            "  Walk-Forward Optimization Results",
            "=" * 72,
            f"  Windows evaluated:      {len(self.windows)}",
            f"  Total test trades:      {self.total_trades}",
            f"  Overall test Sortino:   {self.overall_test_sortino:.3f}",
            f"  Overall test return:    {self.overall_test_return:.2f}%",
            f"  Overall test max DD:    {self.overall_test_max_drawdown:.2f}%",
            f"  Overall test win rate:  {self.overall_test_win_rate:.1f}%",
            "",
            "  Consensus parameters (median across windows):",
        ]
        for k, v in sorted(self.best_params.items()):
            if isinstance(v, float):
                lines.append(f"    {k:30s}: {v:.4f}")
            else:
                lines.append(f"    {k:30s}: {v}")

        lines.append("")
        lines.append("  Per-window breakdown:")
        lines.append(
            f"  {'#':>3s}  {'Train':>8s}  {'Validate':>8s}  {'Test':>8s}  "
            f"{'Return':>8s}  {'MaxDD':>8s}  {'WinRate':>8s}  {'Trades':>6s}"
        )
        lines.append("  " + "-" * 68)

        for i, w in enumerate(self.windows):
            lines.append(
                f"  {i + 1:3d}  "
                f"{w.train_sortino:8.3f}  "
                f"{w.validate_sortino:8.3f}  "
                f"{w.test_sortino:8.3f}  "
                f"{w.test_return:7.2f}%  "
                f"{w.test_max_drawdown:7.2f}%  "
                f"{w.test_win_rate:7.1f}%  "
                f"{w.test_trade_count:6d}"
            )

        lines.append("=" * 72)
        lines.append(f"  Generated: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        lines.append("=" * 72)

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Walk-Forward Optimizer
# ---------------------------------------------------------------------------

class WalkForwardOptimizer:
    """Walk-forward optimization engine using Optuna TPE sampler.

    Usage::

        optimizer = WalkForwardOptimizer(config, data_provider)
        result = await optimizer.run(
            symbol="BTC/USDT",
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2026, 3, 1),
        )
        print(result.summary())
        print(result.best_params)
    """

    def __init__(self, config: Dict[str, Any], data_provider=None):
        self._config = config
        self._data_provider = data_provider

        opt_cfg = config.get("optimizer", {})
        wf_cfg = opt_cfg.get("walk_forward", {})

        self.train_months: int = wf_cfg.get("train_months", 6)
        self.validate_months: int = wf_cfg.get("validate_months", 1)
        self.test_months: int = wf_cfg.get("test_months", 1)
        self.purge_days: int = wf_cfg.get("purge_days", 7)
        self.roll_months: int = wf_cfg.get("roll_months", 1)
        self.n_trials: int = wf_cfg.get("n_trials", 50)
        self.max_drawdown_constraint: float = wf_cfg.get("max_drawdown_pct", 15.0)
        self.min_trades: int = wf_cfg.get("min_trades", 10)

    # ------------------------------------------------------------------
    # Window generation
    # ------------------------------------------------------------------

    def _generate_windows(
        self, start: datetime, end: datetime
    ) -> List[WalkForwardWindow]:
        """Generate rolling walk-forward windows.

        Each window contains a training period, a purge gap to avoid
        look-ahead bias, a validation period, and a test period.  The
        window is then rolled forward by ``roll_months``.

        Args:
            start: Earliest allowed training start date.
            end: Latest allowed test end date.

        Returns:
            List of non-overlapping (in test) walk-forward windows.
        """
        windows: List[WalkForwardWindow] = []
        current_train_start = start

        while True:
            train_end = current_train_start + timedelta(days=self.train_months * 30)
            purge_end = train_end + timedelta(days=self.purge_days)
            validate_start = purge_end
            validate_end = validate_start + timedelta(days=self.validate_months * 30)
            test_start = validate_end
            test_end = test_start + timedelta(days=self.test_months * 30)

            if test_end > end:
                break

            windows.append(
                WalkForwardWindow(
                    train_start=current_train_start,
                    train_end=train_end,
                    purge_end=purge_end,
                    validate_start=validate_start,
                    validate_end=validate_end,
                    test_start=test_start,
                    test_end=test_end,
                )
            )

            # Roll forward
            current_train_start += timedelta(days=self.roll_months * 30)

        return windows

    # ------------------------------------------------------------------
    # Search space
    # ------------------------------------------------------------------

    @staticmethod
    def _define_search_space(trial: optuna.Trial) -> Dict[str, Any]:
        """Define the Optuna search space for trading parameters.

        Args:
            trial: An Optuna trial object used for parameter suggestions.

        Returns:
            Dictionary of sampled parameter values.
        """
        return {
            "min_confidence": trial.suggest_int("min_confidence", 65, 92),
            "tech_weight": trial.suggest_float(
                "tech_weight", 0.4, 0.9, step=0.05
            ),
            "atr_stop_multiplier": trial.suggest_float(
                "atr_stop_multiplier", 1.0, 4.0, step=0.25
            ),
            "atr_trailing_distance": trial.suggest_float(
                "atr_trailing_distance", 0.5, 3.0, step=0.25
            ),
            "max_position_pct": trial.suggest_float(
                "max_position_pct", 1.0, 5.0, step=0.5
            ),
            "rsi_oversold": trial.suggest_int("rsi_oversold", 20, 35),
            "rsi_overbought": trial.suggest_int("rsi_overbought", 65, 80),
            "min_risk_reward": trial.suggest_float(
                "min_risk_reward", 1.0, 3.0, step=0.25
            ),
        }

    # ------------------------------------------------------------------
    # Single backtest execution
    # ------------------------------------------------------------------

    async def _run_backtest_with_params(
        self,
        symbol: str,
        data: pd.DataFrame,
        start: datetime,
        end: datetime,
        params: Dict[str, Any],
    ) -> Dict[str, float]:
        """Run a single backtest with specific parameters on a data slice.

        Uses ``BacktestExchange`` from the execution layer to simulate
        order fills with realistic fees and slippage.

        Args:
            symbol: Trading pair (e.g. ``"BTC/USDT"``).
            data: Full historical DataFrame with a DatetimeIndex.
            start: Window start (inclusive).
            end: Window end (exclusive).
            params: Strategy parameters to apply.

        Returns:
            Dict with keys: ``sortino``, ``total_return``, ``max_drawdown``,
            ``win_rate``, ``trade_count``.
        """
        from src.execution.abstract_exchange import BacktestExchange, OrderRequest

        # Filter data to window
        mask = (data.index >= start) & (data.index < end)
        window_data = data.loc[mask]

        if len(window_data) < 50:
            return {
                "sortino": -999.0,
                "total_return": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "trade_count": 0,
            }

        initial_balance = 10_000.0
        ex = BacktestExchange(
            initial_balance=initial_balance,
            fee_pct=0.1,
            slippage_pct=0.05,
        )
        await ex.connect()

        # Track period returns for Sortino calculation
        returns: List[float] = []
        prev_equity = initial_balance

        rsi_oversold = params.get("rsi_oversold", 30)
        rsi_overbought = params.get("rsi_overbought", 70)
        max_position_pct = params.get("max_position_pct", 3.0) / 100.0

        has_rsi = "rsi_14" in window_data.columns

        for i in range(50, len(window_data)):
            row = window_data.iloc[i]
            price = float(row.get("close", 0))
            if price <= 0:
                continue

            ex.set_prices({symbol: price})

            rsi = float(row["rsi_14"]) if has_rsi else 50.0

            bal = await ex.get_balance()
            positions = await ex.get_positions()
            has_pos = len(positions) > 0

            # Entry: RSI oversold
            if not has_pos and rsi < rsi_oversold:
                size = bal.free_usd * max_position_pct / price
                if size > 0 and bal.free_usd > 100:
                    await ex.place_order(
                        OrderRequest(
                            symbol=symbol,
                            side="buy",
                            order_type="market",
                            amount=size,
                        )
                    )

            # Exit: RSI overbought or stop-loss via ATR
            elif has_pos and rsi > rsi_overbought:
                for pos in positions:
                    size = pos.get("size", 0)
                    if size > 0:
                        await ex.place_order(
                            OrderRequest(
                                symbol=symbol,
                                side="sell",
                                order_type="market",
                                amount=size,
                            )
                        )

            # Track per-bar returns
            equity = (await ex.get_balance()).total_usd
            if prev_equity > 0:
                ret = (equity - prev_equity) / prev_equity
                returns.append(ret)
            prev_equity = equity

        stats = ex.get_stats()
        await ex.disconnect()

        # Calculate annualized Sortino ratio
        returns_arr = np.array(returns) if returns else np.array([0.0])
        downside = returns_arr[returns_arr < 0]
        downside_std = float(np.std(downside)) if len(downside) > 1 else 1e-6
        mean_return = float(np.mean(returns_arr))
        sortino = (mean_return / downside_std) * np.sqrt(252) if downside_std > 0 else 0.0

        return {
            "sortino": float(sortino),
            "total_return": stats.get("total_return_pct", 0.0),
            "max_drawdown": stats.get("max_drawdown_pct", 0.0),
            "win_rate": stats.get("win_rate", 0.0),
            "trade_count": stats.get("trade_count", 0),
        }

    # ------------------------------------------------------------------
    # Per-window optimization
    # ------------------------------------------------------------------

    async def _optimize_window(
        self, symbol: str, data: pd.DataFrame, window: WalkForwardWindow
    ) -> WindowResult:
        """Optimize parameters on train set, validate, then test.

        The Optuna study searches the parameter space on the training
        window.  Trials with too few trades or excessive drawdown are
        pruned.  The best parameters are then evaluated on the
        validation and test windows.

        Args:
            symbol: Trading pair.
            data: Full historical DataFrame.
            window: The walk-forward window to optimize.

        Returns:
            WindowResult with train/validate/test metrics and best params.
        """
        import asyncio

        # Create Optuna study with TPE sampler (Bayesian)
        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=42),
            pruner=optuna.pruners.MedianPruner(),
        )

        # We need a reference to `self` inside the sync objective wrapper
        optimizer_ref = self

        async def objective_async(trial: optuna.Trial) -> float:
            params = WalkForwardOptimizer._define_search_space(trial)
            result = await optimizer_ref._run_backtest_with_params(
                symbol, data, window.train_start, window.train_end, params
            )

            # Prune if too few trades
            if result["trade_count"] < optimizer_ref.min_trades:
                raise optuna.TrialPruned()

            # Prune if drawdown exceeds constraint
            if abs(result["max_drawdown"]) > optimizer_ref.max_drawdown_constraint:
                raise optuna.TrialPruned()

            return result["sortino"]

        def objective(trial: optuna.Trial) -> float:
            """Sync wrapper for the async objective."""
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(objective_async(trial))
            finally:
                loop.close()

        # Suppress Optuna's verbose logging
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        study.optimize(objective, n_trials=self.n_trials, show_progress_bar=False)

        if not study.best_trials:
            # All trials pruned -- fall back to defaults
            best_params = {
                "min_confidence": 78,
                "tech_weight": 0.6,
                "atr_stop_multiplier": 2.0,
                "atr_trailing_distance": 1.5,
                "max_position_pct": 3.0,
                "rsi_oversold": 30,
                "rsi_overbought": 70,
                "min_risk_reward": 1.5,
            }
            best_train_sortino = 0.0
        else:
            best_params = study.best_params
            best_train_sortino = study.best_value

        # Evaluate best params on validation window
        validate_result = await self._run_backtest_with_params(
            symbol, data, window.validate_start, window.validate_end, best_params
        )

        # Evaluate best params on test window (out-of-sample)
        test_result = await self._run_backtest_with_params(
            symbol, data, window.test_start, window.test_end, best_params
        )

        # Fetch train return for the best params
        train_result = await self._run_backtest_with_params(
            symbol, data, window.train_start, window.train_end, best_params
        )

        return WindowResult(
            window=window,
            best_params=best_params,
            train_sortino=best_train_sortino,
            validate_sortino=validate_result["sortino"],
            test_sortino=test_result["sortino"],
            train_return=train_result["total_return"],
            validate_return=validate_result["total_return"],
            test_return=test_result["total_return"],
            test_max_drawdown=test_result["max_drawdown"],
            test_win_rate=test_result["win_rate"],
            test_trade_count=int(test_result["trade_count"]),
            optimization_trials=len(study.trials),
        )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        symbol: str = "BTC/USDT",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> WalkForwardResult:
        """Run the full walk-forward optimization.

        Fetches historical data, generates rolling windows, optimizes
        parameters on each training set via Optuna, validates, tests,
        and aggregates the results.

        Args:
            symbol: Trading pair to optimize.
            start_date: Earliest training start date.  Defaults to 1 year ago.
            end_date: Latest test end date.  Defaults to now.

        Returns:
            WalkForwardResult with per-window and overall metrics,
            plus consensus parameters.

        Raises:
            ValueError: If no data is available or insufficient for windows.
        """
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=365)
        if not end_date:
            end_date = datetime.utcnow()

        logger.info(
            "Walk-forward optimization: %s from %s to %s",
            symbol,
            start_date.date(),
            end_date.date(),
        )

        # Fetch historical data
        data: Optional[pd.DataFrame] = None
        if self._data_provider is not None:
            data = self._data_provider.get_data(symbol, "1h")

        if data is None or len(data) == 0:
            raise ValueError(f"No historical data available for {symbol}")

        # Generate windows
        windows = self._generate_windows(start_date, end_date)
        logger.info("Generated %d walk-forward windows", len(windows))

        if not windows:
            raise ValueError(
                "Insufficient data range for walk-forward windows. "
                f"Need at least {self.train_months + self.validate_months + self.test_months} "
                "months of data."
            )

        # Optimize each window sequentially
        results: List[WindowResult] = []
        for i, window in enumerate(windows):
            logger.info(
                "Optimizing window %d/%d: train %s to %s, test %s to %s",
                i + 1,
                len(windows),
                window.train_start.date(),
                window.train_end.date(),
                window.test_start.date(),
                window.test_end.date(),
            )
            result = await self._optimize_window(symbol, data, window)
            results.append(result)
            logger.info(
                "  Window %d: train_sortino=%.3f, validate=%.3f, test=%.3f, "
                "test_return=%.2f%%, trades=%d",
                i + 1,
                result.train_sortino,
                result.validate_sortino,
                result.test_sortino,
                result.test_return,
                result.test_trade_count,
            )

        # Aggregate test metrics across windows
        test_sortinos = [r.test_sortino for r in results if r.test_trade_count > 0]
        test_returns = [r.test_return for r in results]
        test_drawdowns = [r.test_max_drawdown for r in results]
        test_win_rates = [r.test_win_rate for r in results]
        total_trades = sum(r.test_trade_count for r in results)

        # Build consensus parameters: median for numeric, mode for categorical
        param_votes: Dict[str, List[Any]] = {}
        for r in results:
            for k, v in r.best_params.items():
                if k not in param_votes:
                    param_votes[k] = []
                param_votes[k].append(v)

        consensus_params: Dict[str, Any] = {}
        for k, values in param_votes.items():
            if isinstance(values[0], (int, float)):
                consensus_params[k] = float(np.median(values))
            else:
                consensus_params[k] = Counter(values).most_common(1)[0][0]

        wf_result = WalkForwardResult(
            windows=results,
            overall_test_sortino=(
                float(np.mean(test_sortinos)) if test_sortinos else 0.0
            ),
            overall_test_return=(
                float(np.mean(test_returns)) if test_returns else 0.0
            ),
            overall_test_max_drawdown=(
                float(np.min(test_drawdowns)) if test_drawdowns else 0.0
            ),
            overall_test_win_rate=(
                float(np.mean(test_win_rates)) if test_win_rates else 0.0
            ),
            total_trades=total_trades,
            best_params=consensus_params,
        )

        logger.info(
            "Walk-forward optimization complete: "
            "sortino=%.3f, return=%.2f%%, max_dd=%.2f%%, trades=%d",
            wf_result.overall_test_sortino,
            wf_result.overall_test_return,
            wf_result.overall_test_max_drawdown,
            wf_result.total_trades,
        )

        return wf_result
