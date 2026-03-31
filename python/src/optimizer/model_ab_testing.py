"""Model A/B Testing (Champion/Challenger) framework.

Provides statistical A/B testing for ML prediction models (LSTM, Transformer,
CNN, XGBoost, etc.). When the orchestrator suspects a model is degrading, or
when a newly-trained model is available, a test session pits the current
champion against a challenger and auto-promotes if the challenger is
statistically better.

Statistical method: binomial test (scipy.stats.binom_test / binomial_test)
for directional win comparison, with optional chi-squared test for multi-
metric comparison.

State is persisted as JSON files so the framework survives restarts.
"""

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

STATUS_CHAMPION = "champion"
STATUS_CHALLENGER = "challenger"
STATUS_RETIRED = "retired"
STATUS_CANDIDATE = "candidate"


@dataclass
class ModelMetricsSnapshot:
    """Performance metrics for a model candidate."""
    sharpe: float = 0.0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0


@dataclass
class ModelCandidate:
    """A registered model that can participate in A/B tests."""
    model_id: str = ""
    model_type: str = ""           # e.g. "lstm", "transformer", "cnn", "xgboost"
    params: Dict[str, Any] = field(default_factory=dict)
    metrics: ModelMetricsSnapshot = field(default_factory=ModelMetricsSnapshot)
    status: str = STATUS_CANDIDATE  # champion / challenger / candidate / retired
    registered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_type": self.model_type,
            "params": self.params,
            "metrics": asdict(self.metrics),
            "status": self.status,
            "registered_at": self.registered_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ModelCandidate":
        metrics = ModelMetricsSnapshot(**d.get("metrics", {}))
        return cls(
            model_id=d["model_id"],
            model_type=d.get("model_type", ""),
            params=d.get("params", {}),
            metrics=metrics,
            status=d.get("status", STATUS_CANDIDATE),
            registered_at=d.get("registered_at", ""),
        )


@dataclass
class ABTestSession:
    """A running A/B test between a champion and a challenger."""
    session_id: str = ""
    champion_id: str = ""
    challenger_id: str = ""
    start_date: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    min_signals: int = 50
    signals_compared: int = 0
    wins_champion: int = 0
    wins_challenger: int = 0
    ties: int = 0
    concluded: bool = False
    conclusion: str = ""          # "champion_retained" / "challenger_promoted" / "inconclusive"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ABTestSession":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Composite score helper
# ---------------------------------------------------------------------------

def _composite_score(m: ModelMetricsSnapshot) -> float:
    """Weighted composite of model metrics for leaderboard ranking.

    Higher is better. Drawdown is penalised.
    """
    return (
        0.35 * m.sharpe
        + 0.30 * m.win_rate
        + 0.20 * m.profit_factor
        - 0.15 * m.max_drawdown
    )


# ---------------------------------------------------------------------------
# Main framework
# ---------------------------------------------------------------------------

class ModelABTestingFramework:
    """Manages model registration, A/B test sessions, and champion promotion."""

    def __init__(self, data_dir: str = "data/ab_testing"):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._candidates: Dict[str, ModelCandidate] = {}
        self._sessions: Dict[str, ABTestSession] = {}

        self._load_state()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _state_path(self) -> Path:
        return self._data_dir / "ab_state.json"

    def _save_state(self) -> None:
        state = {
            "candidates": {k: v.to_dict() for k, v in self._candidates.items()},
            "sessions": {k: v.to_dict() for k, v in self._sessions.items()},
        }
        try:
            self._state_path().write_text(json.dumps(state, indent=2))
        except Exception as e:
            logger.error("Failed to save A/B testing state: %s", e)

    def _load_state(self) -> None:
        path = self._state_path()
        if not path.exists():
            return
        try:
            state = json.loads(path.read_text())
            self._candidates = {
                k: ModelCandidate.from_dict(v)
                for k, v in state.get("candidates", {}).items()
            }
            self._sessions = {
                k: ABTestSession.from_dict(v)
                for k, v in state.get("sessions", {}).items()
            }
            logger.info(
                "Loaded A/B testing state: %d candidates, %d sessions",
                len(self._candidates), len(self._sessions),
            )
        except Exception as e:
            logger.error("Failed to load A/B testing state: %s", e)

    # ------------------------------------------------------------------
    # Model registration
    # ------------------------------------------------------------------

    def register_model(
        self,
        model_id: str,
        model_type: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> ModelCandidate:
        """Register a new model candidate."""
        if model_id in self._candidates:
            logger.warning("Model '%s' already registered, updating params", model_id)
            if params:
                self._candidates[model_id].params = params
            self._save_state()
            return self._candidates[model_id]

        candidate = ModelCandidate(
            model_id=model_id,
            model_type=model_type,
            params=params or {},
        )
        self._candidates[model_id] = candidate
        logger.info("Registered model candidate: %s (type=%s)", model_id, model_type)
        self._save_state()
        return candidate

    def update_metrics(
        self,
        model_id: str,
        sharpe: Optional[float] = None,
        win_rate: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        profit_factor: Optional[float] = None,
    ) -> None:
        """Update performance metrics for a registered model."""
        c = self._candidates.get(model_id)
        if c is None:
            logger.warning("Cannot update metrics: model '%s' not registered", model_id)
            return
        if sharpe is not None:
            c.metrics.sharpe = sharpe
        if win_rate is not None:
            c.metrics.win_rate = win_rate
        if max_drawdown is not None:
            c.metrics.max_drawdown = max_drawdown
        if profit_factor is not None:
            c.metrics.profit_factor = profit_factor
        self._save_state()

    def retire_model(self, model_id: str) -> bool:
        """Retire a model, removing it from active consideration."""
        c = self._candidates.get(model_id)
        if c is None:
            return False
        c.status = STATUS_RETIRED
        logger.info("Retired model: %s", model_id)
        self._save_state()
        return True

    # ------------------------------------------------------------------
    # Champion management
    # ------------------------------------------------------------------

    def promote_champion(self, model_id: str) -> bool:
        """Promote a model to champion status for its model_type.

        Any existing champion of the same type is demoted to candidate.
        """
        c = self._candidates.get(model_id)
        if c is None:
            logger.warning("Cannot promote: model '%s' not found", model_id)
            return False

        # Demote current champion of same type
        for other in self._candidates.values():
            if (other.model_type == c.model_type
                    and other.status == STATUS_CHAMPION
                    and other.model_id != model_id):
                other.status = STATUS_CANDIDATE
                logger.info(
                    "Demoted previous champion '%s' (type=%s) to candidate",
                    other.model_id, other.model_type,
                )

        c.status = STATUS_CHAMPION
        logger.info("Promoted model '%s' to champion (type=%s)", model_id, c.model_type)
        self._save_state()
        return True

    def get_active_champion(self, model_type: str) -> Optional[ModelCandidate]:
        """Return the current champion for a given model type."""
        for c in self._candidates.values():
            if c.model_type == model_type and c.status == STATUS_CHAMPION:
                return c
        return None

    # ------------------------------------------------------------------
    # A/B test sessions
    # ------------------------------------------------------------------

    def start_ab_test(
        self,
        champion_id: str,
        challenger_id: str,
        min_signals: int = 50,
    ) -> Optional[str]:
        """Begin an A/B test session between champion and challenger.

        Returns the session_id, or None if validation fails.
        """
        champion = self._candidates.get(champion_id)
        challenger = self._candidates.get(challenger_id)

        if champion is None or challenger is None:
            logger.error(
                "Cannot start A/B test: missing model(s) champion=%s challenger=%s",
                champion_id, challenger_id,
            )
            return None

        # Check no active session already exists for these two
        for s in self._sessions.values():
            if not s.concluded and s.champion_id == champion_id and s.challenger_id == challenger_id:
                logger.warning(
                    "Active session already exists for %s vs %s: %s",
                    champion_id, challenger_id, s.session_id,
                )
                return s.session_id

        session_id = str(uuid.uuid4())[:8]
        session = ABTestSession(
            session_id=session_id,
            champion_id=champion_id,
            challenger_id=challenger_id,
            min_signals=min_signals,
        )

        # Mark challenger status
        challenger.status = STATUS_CHALLENGER

        self._sessions[session_id] = session
        logger.info(
            "Started A/B test session %s: %s (champion) vs %s (challenger), min_signals=%d",
            session_id, champion_id, challenger_id, min_signals,
        )
        self._save_state()
        return session_id

    def record_signal_outcome(
        self,
        session_id: str,
        champion_correct: bool,
        challenger_correct: bool,
    ) -> bool:
        """Record the outcome of a single signal comparison.

        Args:
            session_id: The A/B test session
            champion_correct: Whether the champion's signal was correct
            challenger_correct: Whether the challenger's signal was correct
        """
        session = self._sessions.get(session_id)
        if session is None or session.concluded:
            return False

        session.signals_compared += 1
        if champion_correct and not challenger_correct:
            session.wins_champion += 1
        elif challenger_correct and not champion_correct:
            session.wins_challenger += 1
        else:
            session.ties += 1

        self._save_state()
        return True

    def evaluate_session(self, session_id: str) -> Dict[str, Any]:
        """Evaluate an A/B test session using statistical testing.

        Uses a binomial test to determine whether the challenger's win rate
        is significantly different from 50% (i.e. random chance vs champion).

        Returns a dict with evaluation results including p_value, winner,
        and whether the result is statistically significant.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return {"error": "Session not found"}

        result: Dict[str, Any] = {
            "session_id": session_id,
            "champion_id": session.champion_id,
            "challenger_id": session.challenger_id,
            "signals_compared": session.signals_compared,
            "wins_champion": session.wins_champion,
            "wins_challenger": session.wins_challenger,
            "ties": session.ties,
            "sufficient_data": session.signals_compared >= session.min_signals,
        }

        # Need non-tie comparisons for binomial test
        decisive_signals = session.wins_champion + session.wins_challenger
        if decisive_signals < 10:
            result["p_value"] = 1.0
            result["significant"] = False
            result["winner"] = "inconclusive"
            result["reason"] = "Insufficient decisive signals (need >= 10)"
            return result

        # Binomial test: under H0 the challenger wins 50% of decisive signals.
        # We test if challenger wins significantly more than 50%.
        try:
            from scipy.stats import binomtest
            btest = binomtest(session.wins_challenger, decisive_signals, 0.5, alternative="greater")
            p_value = btest.pvalue
        except ImportError:
            # Fallback: normal approximation for large n
            p_hat = session.wins_challenger / decisive_signals
            se = np.sqrt(0.5 * 0.5 / decisive_signals)
            z = (p_hat - 0.5) / se if se > 0 else 0
            # One-sided p-value from normal CDF
            from math import erfc
            p_value = 0.5 * erfc(z / np.sqrt(2))

        challenger_win_rate = session.wins_challenger / decisive_signals if decisive_signals else 0
        champion_win_rate = session.wins_champion / decisive_signals if decisive_signals else 0

        result["p_value"] = round(p_value, 6)
        result["challenger_win_rate"] = round(challenger_win_rate, 4)
        result["champion_win_rate"] = round(champion_win_rate, 4)
        result["significant"] = p_value < 0.05

        if p_value < 0.05 and challenger_win_rate > champion_win_rate:
            result["winner"] = "challenger"
        elif p_value < 0.05 and champion_win_rate > challenger_win_rate:
            result["winner"] = "champion"
        else:
            result["winner"] = "inconclusive"

        return result

    def auto_promote(self, session_id: str, confidence_threshold: float = 0.95) -> Dict[str, Any]:
        """Auto-promote challenger if it wins with statistical significance.

        Args:
            session_id: The A/B test session
            confidence_threshold: Required confidence level (1 - alpha).
                                  Default 0.95 means p < 0.05.

        Returns dict with action taken and evaluation details.
        """
        alpha = 1.0 - confidence_threshold
        evaluation = self.evaluate_session(session_id)
        session = self._sessions.get(session_id)

        if session is None:
            return {"action": "none", "reason": "Session not found"}

        if not evaluation.get("sufficient_data", False):
            return {
                "action": "wait",
                "reason": f"Need {session.min_signals} signals, have {session.signals_compared}",
                "evaluation": evaluation,
            }

        p_value = evaluation.get("p_value", 1.0)
        winner = evaluation.get("winner", "inconclusive")

        if p_value < alpha and winner == "challenger":
            # Promote challenger to champion
            self.promote_champion(session.challenger_id)
            session.concluded = True
            session.conclusion = "challenger_promoted"
            self._save_state()
            logger.info(
                "A/B test %s concluded: challenger '%s' promoted (p=%.4f)",
                session_id, session.challenger_id, p_value,
            )
            return {
                "action": "promoted",
                "new_champion": session.challenger_id,
                "evaluation": evaluation,
            }
        elif session.signals_compared >= session.min_signals * 2:
            # Enough data gathered, champion retained
            session.concluded = True
            session.conclusion = "champion_retained"
            self._save_state()
            logger.info(
                "A/B test %s concluded: champion '%s' retained (p=%.4f)",
                session_id, session.champion_id, p_value,
            )
            return {
                "action": "retained",
                "champion": session.champion_id,
                "evaluation": evaluation,
            }
        else:
            return {
                "action": "wait",
                "reason": "Not yet statistically significant, continuing test",
                "evaluation": evaluation,
            }

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_leaderboard(self) -> List[Dict[str, Any]]:
        """Return all non-retired models ranked by composite score."""
        active = [
            c for c in self._candidates.values()
            if c.status != STATUS_RETIRED
        ]
        active.sort(key=lambda c: _composite_score(c.metrics), reverse=True)
        return [
            {
                **c.to_dict(),
                "composite_score": round(_composite_score(c.metrics), 4),
            }
            for c in active
        ]

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Return session details."""
        s = self._sessions.get(session_id)
        return s.to_dict() if s else None

    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Return all non-concluded sessions."""
        return [
            s.to_dict() for s in self._sessions.values()
            if not s.concluded
        ]

    def get_candidate(self, model_id: str) -> Optional[ModelCandidate]:
        return self._candidates.get(model_id)

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "total_candidates": len(self._candidates),
            "champions": sum(1 for c in self._candidates.values() if c.status == STATUS_CHAMPION),
            "active_sessions": sum(1 for s in self._sessions.values() if not s.concluded),
            "concluded_sessions": sum(1 for s in self._sessions.values() if s.concluded),
        }
