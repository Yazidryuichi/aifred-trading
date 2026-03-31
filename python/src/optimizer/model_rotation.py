"""Model rotation manager: auto-swap degraded models via A/B testing.

Integrates with ``monitoring.model_tracker.ModelTracker`` to detect when
a champion model is degrading, and with ``optimizer.model_ab_testing``
to automatically spawn an A/B test with the next-best challenger.

Includes a cooldown period (default 24 h) between rotations to prevent
thrashing when models oscillate.

State (rotation history + cooldown timestamps) is persisted as JSON.
"""

import json
import logging
from datetime import datetime, timedelta
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RotationEvent:
    """Record of a single champion swap."""
    timestamp: str = ""
    model_type: str = ""
    old_champion_id: str = ""
    new_champion_id: str = ""
    reason: str = ""             # "degradation", "ab_test_winner", "manual"
    ab_session_id: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RotationEvent":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class ModelRotationManager:
    """Orchestrates model rotation: degradation detection -> A/B test -> swap.

    Typical usage from the orchestrator's periodic tick::

        rotation_manager.check_and_rotate()
    """

    def __init__(
        self,
        ab_framework: "ModelABTestingFramework",
        model_tracker: Optional[Any] = None,
        cooldown_hours: float = 24.0,
        min_ab_signals: int = 50,
        confidence_threshold: float = 0.95,
        data_dir: str = "data/ab_testing",
    ):
        from src.optimizer.model_ab_testing import ModelABTestingFramework  # noqa: F811

        self._ab: ModelABTestingFramework = ab_framework
        self._tracker = model_tracker         # monitoring.model_tracker.ModelTracker
        self._cooldown = timedelta(hours=cooldown_hours)
        self._min_ab_signals = min_ab_signals
        self._confidence = confidence_threshold

        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._history: List[RotationEvent] = []
        self._last_rotation_by_type: Dict[str, datetime] = {}
        self._load_state()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _state_path(self) -> Path:
        return self._data_dir / "rotation_state.json"

    def _save_state(self) -> None:
        state = {
            "history": [e.to_dict() for e in self._history],
            "last_rotation_by_type": {
                k: v.isoformat() for k, v in self._last_rotation_by_type.items()
            },
        }
        try:
            self._state_path().write_text(json.dumps(state, indent=2))
        except Exception as e:
            logger.error("Failed to save rotation state: %s", e)

    def _load_state(self) -> None:
        path = self._state_path()
        if not path.exists():
            return
        try:
            state = json.loads(path.read_text())
            self._history = [
                RotationEvent.from_dict(d) for d in state.get("history", [])
            ]
            self._last_rotation_by_type = {
                k: datetime.fromisoformat(v)
                for k, v in state.get("last_rotation_by_type", {}).items()
            }
            logger.info(
                "Loaded rotation state: %d events in history", len(self._history),
            )
        except Exception as e:
            logger.error("Failed to load rotation state: %s", e)

    # ------------------------------------------------------------------
    # Cooldown
    # ------------------------------------------------------------------

    def _in_cooldown(self, model_type: str) -> bool:
        last = self._last_rotation_by_type.get(model_type)
        if last is None:
            return False
        return datetime.utcnow() - last < self._cooldown

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def check_and_rotate(self) -> List[Dict[str, Any]]:
        """Run one rotation cycle. Call periodically from the orchestrator.

        Steps:
        1. Check for degraded models via model_tracker
        2. For each degraded champion, find the next-best challenger
        3. If no active A/B test exists, spawn one
        4. For active A/B tests, try auto-promote
        5. Respect cooldown between rotations

        Returns a list of action summaries.
        """
        actions: List[Dict[str, Any]] = []

        # --- Step 1: evaluate existing A/B sessions ---
        for session_dict in self._ab.get_active_sessions():
            session_id = session_dict["session_id"]
            result = self._ab.auto_promote(session_id, self._confidence)
            action = result.get("action", "wait")

            if action == "promoted":
                new_champ = result["new_champion"]
                session = self._ab.get_session(session_id)
                old_champ = session["champion_id"] if session else "unknown"
                candidate = self._ab.get_candidate(new_champ)
                model_type = candidate.model_type if candidate else "unknown"

                event = RotationEvent(
                    timestamp=datetime.utcnow().isoformat(),
                    model_type=model_type,
                    old_champion_id=old_champ,
                    new_champion_id=new_champ,
                    reason="ab_test_winner",
                    ab_session_id=session_id,
                    details=result.get("evaluation", {}),
                )
                self._record_event(event)
                actions.append({
                    "type": "promotion",
                    "model_type": model_type,
                    "new_champion": new_champ,
                    "old_champion": old_champ,
                })
            elif action == "retained":
                actions.append({"type": "retained", "session_id": session_id})

        # --- Step 2: check degradation and spawn new tests ---
        if self._tracker is not None:
            degraded = self._tracker.check_degradation()
            for d in degraded:
                model_name = d["model"]
                self._handle_degraded_model(model_name, d, actions)

        return actions

    def _handle_degraded_model(
        self,
        model_name: str,
        degradation_info: Dict[str, Any],
        actions: List[Dict[str, Any]],
    ) -> None:
        """Spawn an A/B test for a degraded champion if conditions are met."""
        # Find the corresponding champion candidate
        champion = self._ab.get_candidate(model_name)
        if champion is None:
            logger.debug("Degraded model '%s' not registered in A/B framework", model_name)
            return
        if champion.status != "champion":
            return

        model_type = champion.model_type

        # Cooldown check
        if self._in_cooldown(model_type):
            logger.debug(
                "Model type '%s' in rotation cooldown, skipping", model_type,
            )
            return

        # Check if there's already an active session for this champion
        for s in self._ab.get_active_sessions():
            if s["champion_id"] == model_name:
                logger.debug("Active A/B session already exists for champion '%s'", model_name)
                return

        # Find best challenger: highest composite score among non-champion, non-retired
        # of the same model type
        leaderboard = self._ab.get_leaderboard()
        challenger_id = None
        for entry in leaderboard:
            if (entry["model_type"] == model_type
                    and entry["status"] not in ("champion", "retired")
                    and entry["model_id"] != model_name):
                challenger_id = entry["model_id"]
                break

        if challenger_id is None:
            logger.warning(
                "No challenger available for degraded champion '%s' (type=%s)",
                model_name, model_type,
            )
            return

        session_id = self._ab.start_ab_test(
            champion_id=model_name,
            challenger_id=challenger_id,
            min_signals=self._min_ab_signals,
        )

        if session_id:
            logger.info(
                "Spawned A/B test %s for degraded champion '%s' vs challenger '%s'",
                session_id, model_name, challenger_id,
            )
            actions.append({
                "type": "ab_test_spawned",
                "session_id": session_id,
                "champion": model_name,
                "challenger": challenger_id,
                "degradation": degradation_info,
            })

    def _record_event(self, event: RotationEvent) -> None:
        """Record a rotation event and update cooldown timestamps."""
        self._history.append(event)
        self._last_rotation_by_type[event.model_type] = datetime.utcnow()
        self._save_state()

    def force_rotate(
        self,
        model_type: str,
        new_champion_id: str,
        reason: str = "manual",
    ) -> bool:
        """Force a champion rotation without A/B testing (manual override).

        Bypasses cooldown. Use sparingly.
        """
        current = self._ab.get_active_champion(model_type)
        old_id = current.model_id if current else "none"

        if not self._ab.promote_champion(new_champion_id):
            return False

        event = RotationEvent(
            timestamp=datetime.utcnow().isoformat(),
            model_type=model_type,
            old_champion_id=old_id,
            new_champion_id=new_champion_id,
            reason=reason,
        )
        self._record_event(event)
        logger.info(
            "Forced rotation for type '%s': %s -> %s (reason=%s)",
            model_type, old_id, new_champion_id, reason,
        )
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_rotation_history(self, model_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return audit trail of all rotations, optionally filtered by model type."""
        events = self._history
        if model_type:
            events = [e for e in events if e.model_type == model_type]
        return [e.to_dict() for e in events]

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "total_rotations": len(self._history),
            "cooldowns_active": {
                k: v.isoformat()
                for k, v in self._last_rotation_by_type.items()
                if self._in_cooldown(k)
            },
            "ab_framework": self._ab.status,
        }
