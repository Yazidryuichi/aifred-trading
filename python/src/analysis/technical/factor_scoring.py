"""Factor scoring using Information Coefficient (IC) and ICIR.

IC = Spearman rank correlation between factor value and forward returns.
ICIR = IC mean / IC std (stability of predictive power).

Factors with high IC and ICIR are genuinely predictive.
Factors with low IC/ICIR are noise — they should be downweighted.
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

logger = logging.getLogger(__name__)


class FactorScorer:
    """Score indicators by their actual predictive power using IC/ICIR."""

    def __init__(self, forward_periods: int = 8, window: int = 200, step: int = 24):
        """
        Args:
            forward_periods: How many bars ahead to measure returns (default 8 = prediction horizon).
            window: Sliding window size for IC calculation.
            step: Step size for sliding window.
        """
        self.forward_periods = forward_periods
        self.window = window
        self.step = step
        self._scores: Dict[str, Dict[str, float]] = {}  # factor_name -> {ic, icir, win_rate}

    def score_factors(self, df: pd.DataFrame, factor_columns: List[str]) -> Dict[str, Dict[str, float]]:
        """Score each factor column against forward returns.

        Args:
            df: DataFrame with OHLCV + indicator columns.
            factor_columns: List of column names to score.

        Returns:
            Dict mapping factor name to {ic, icir, win_rate, rank}.
        """
        if len(df) < self.window + self.forward_periods:
            logger.warning("Not enough data for factor scoring (%d bars, need %d)",
                          len(df), self.window + self.forward_periods)
            return {}

        # Compute forward returns
        df = df.copy()
        df['_forward_return'] = df['close'].pct_change(self.forward_periods).shift(-self.forward_periods)
        df = df.dropna(subset=['_forward_return'])

        results = {}
        for col in factor_columns:
            if col not in df.columns:
                continue
            series = df[col].dropna()
            if len(series) < self.window:
                continue

            try:
                ic_values = self._sliding_ic(df, col)
                if not ic_values:
                    continue

                ic_mean = float(np.mean(ic_values))
                ic_std = float(np.std(ic_values)) if len(ic_values) > 1 else 1.0
                icir = ic_mean / ic_std if ic_std > 0.001 else 0.0

                # Win rate: how often does the factor correctly predict direction?
                win_rate = float(np.mean([1 if ic > 0 else 0 for ic in ic_values]))

                results[col] = {
                    "ic": round(ic_mean, 4),
                    "icir": round(icir, 4),
                    "win_rate": round(win_rate, 4),
                    "n_windows": len(ic_values),
                }
            except Exception as e:
                logger.debug("Factor scoring failed for %s: %s", col, e)

        # Rank by absolute IC
        ranked = sorted(results.items(), key=lambda x: abs(x[1]["ic"]), reverse=True)
        for rank, (name, scores) in enumerate(ranked, 1):
            scores["rank"] = rank

        self._scores = results
        return results

    def _sliding_ic(self, df: pd.DataFrame, factor_col: str) -> List[float]:
        """Compute IC over sliding windows."""
        ic_values = []
        n = len(df)
        for start in range(0, n - self.window, self.step):
            end = start + self.window
            window_df = df.iloc[start:end]

            factor_vals = window_df[factor_col].values
            return_vals = window_df['_forward_return'].values

            # Drop NaN pairs
            mask = ~(np.isnan(factor_vals) | np.isnan(return_vals))
            if mask.sum() < 20:
                continue

            corr, _ = spearmanr(factor_vals[mask], return_vals[mask])
            if not np.isnan(corr):
                ic_values.append(corr)

        return ic_values

    def get_top_factors(self, n: int = 10) -> List[Tuple[str, Dict]]:
        """Get top N factors by absolute IC."""
        return sorted(self._scores.items(), key=lambda x: abs(x[1]["ic"]), reverse=True)[:n]

    def get_weak_factors(self, ic_threshold: float = 0.02) -> List[str]:
        """Get factors with IC below threshold (likely noise)."""
        return [name for name, scores in self._scores.items()
                if abs(scores["ic"]) < ic_threshold]

    def get_summary(self) -> str:
        """Get human-readable summary for logging."""
        if not self._scores:
            return "No factor scores computed yet"
        top = self.get_top_factors(5)
        weak = self.get_weak_factors()
        lines = [f"Factor Scoring: {len(self._scores)} factors scored"]
        lines.append(f"Top 5: {', '.join(f'{n}(IC={s['ic']:.3f})' for n,s in top)}")
        if weak:
            lines.append(f"Weak ({len(weak)}): {', '.join(weak[:5])}{'...' if len(weak)>5 else ''}")
        return " | ".join(lines)
