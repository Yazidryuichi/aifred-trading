"""Graceful degradation manager — maintains system availability when components fail.

Implements a capability-based degradation model where the system tracks which
subsystems are healthy and automatically adjusts its behavior based on what's available.

Degradation levels (from full capability to minimal):
  Level 0: FULL — All systems operational
  Level 1: REDUCED_SIGNALS — LLM/sentiment unavailable, trading on ML+technical only
  Level 2: TECHNICAL_ONLY — ML models also failed, trading on technical indicators only
  Level 3: MONITORING_ONLY — Can't generate reliable signals, only monitoring positions
  Level 4: SAFE_MODE — Critical failure, close positions and halt

Each subsystem reports health status. The manager computes the overall degradation
level and provides guidance to the orchestrator on what operations are safe.
"""

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class DegradationLevel(IntEnum):
    FULL = 0
    REDUCED_SIGNALS = 1
    TECHNICAL_ONLY = 2
    MONITORING_ONLY = 3
    SAFE_MODE = 4


class SubsystemStatus(IntEnum):
    HEALTHY = 0
    DEGRADED = 1  # working but slow/unreliable
    FAILED = 2
    UNKNOWN = 3


@dataclass
class SubsystemHealth:
    """Health status of a single subsystem."""
    name: str
    status: SubsystemStatus = SubsystemStatus.UNKNOWN
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    consecutive_failures: int = 0
    error_message: str = ""
    response_time_ms: float = 0.0

    @property
    def is_healthy(self) -> bool:
        return self.status == SubsystemStatus.HEALTHY

    @property
    def is_available(self) -> bool:
        """Available unless explicitly FAILED. UNKNOWN = not yet reported = assumed OK."""
        return self.status != SubsystemStatus.FAILED


class DegradationManager:
    """Manages system degradation state and provides operational guidance.

    Usage:
        dm = DegradationManager(config)

        # Report health from each subsystem
        dm.report_success("technical_analysis", response_time_ms=150)
        dm.report_failure("sentiment_analysis", "API timeout")

        # Check what's allowed
        level = dm.current_level
        if dm.can_open_positions():
            # proceed with trading
        if dm.should_use_sentiment():
            # include sentiment in signal fusion
    """

    # How many consecutive failures before marking subsystem as FAILED
    FAILURE_THRESHOLD = 3

    # How long to wait before retrying a failed subsystem
    RECOVERY_BACKOFF_SECONDS = 300  # 5 minutes

    # Subsystem names
    TECHNICAL = "technical_analysis"
    SENTIMENT = "sentiment_analysis"
    ML_MODELS = "ml_models"
    LLM = "llm_reasoning"
    EXCHANGE = "exchange_api"
    DATA_FEED = "data_feed"
    WEBSOCKET = "websocket"

    def __init__(self, config: Dict[str, Any]):
        self._config = config
        deg_cfg = config.get("degradation", {})
        self.failure_threshold = deg_cfg.get("failure_threshold", self.FAILURE_THRESHOLD)
        self.recovery_backoff = deg_cfg.get("recovery_backoff_seconds", self.RECOVERY_BACKOFF_SECONDS)
        self.safe_mode_close_positions = deg_cfg.get("safe_mode_close_positions", False)

        # Track all subsystems
        self._subsystems: Dict[str, SubsystemHealth] = {}
        for name in [self.TECHNICAL, self.SENTIMENT, self.ML_MODELS,
                     self.LLM, self.EXCHANGE, self.DATA_FEED, self.WEBSOCKET]:
            self._subsystems[name] = SubsystemHealth(name=name)

        self._lock = threading.Lock()
        self._level_change_callbacks: List[Callable] = []
        self._previous_level = DegradationLevel.FULL

        # Alert callback
        self._alert_callback: Optional[Callable] = None

    def set_alert_callback(self, callback: Callable):
        """Set callback for degradation alerts: callback(level, message)."""
        self._alert_callback = callback

    def on_level_change(self, callback: Callable):
        """Register a callback for level changes: callback(new_level, old_level, message)."""
        self._level_change_callbacks.append(callback)

    def report_success(self, subsystem: str, response_time_ms: float = 0.0):
        """Report a successful operation from a subsystem."""
        with self._lock:
            health = self._subsystems.get(subsystem)
            if not health:
                return
            was_failed = health.status == SubsystemStatus.FAILED
            health.status = SubsystemStatus.HEALTHY
            health.last_success = datetime.utcnow()
            health.consecutive_failures = 0
            health.response_time_ms = response_time_ms
            health.error_message = ""

            if was_failed:
                logger.info("Subsystem %s RECOVERED", subsystem)
                self._check_level_change()

    def report_failure(self, subsystem: str, error: str = ""):
        """Report a failed operation from a subsystem."""
        with self._lock:
            health = self._subsystems.get(subsystem)
            if not health:
                return
            health.consecutive_failures += 1
            health.last_failure = datetime.utcnow()
            health.error_message = error

            if health.consecutive_failures >= self.failure_threshold:
                if health.status != SubsystemStatus.FAILED:
                    health.status = SubsystemStatus.FAILED
                    logger.error(
                        "Subsystem %s marked FAILED after %d consecutive failures: %s",
                        subsystem, health.consecutive_failures, error,
                    )
                    self._check_level_change()
            else:
                health.status = SubsystemStatus.DEGRADED
                logger.warning(
                    "Subsystem %s degraded (failure %d/%d): %s",
                    subsystem, health.consecutive_failures,
                    self.failure_threshold, error,
                )

    def report_degraded(self, subsystem: str, reason: str = ""):
        """Report that a subsystem is working but degraded (slow, partial data, etc.)."""
        with self._lock:
            health = self._subsystems.get(subsystem)
            if health:
                health.status = SubsystemStatus.DEGRADED
                health.error_message = reason

    @property
    def current_level(self) -> DegradationLevel:
        """Compute current degradation level from subsystem health."""
        with self._lock:
            return self._compute_level()

    def _compute_level(self) -> DegradationLevel:
        """Determine degradation level based on subsystem states.

        Must be called with self._lock held.
        """
        exchange_ok = self._subsystems[self.EXCHANGE].is_available
        data_ok = self._subsystems[self.DATA_FEED].is_available
        technical_ok = self._subsystems[self.TECHNICAL].is_available
        sentiment_ok = self._subsystems[self.SENTIMENT].is_available
        ml_ok = self._subsystems[self.ML_MODELS].is_available
        llm_ok = self._subsystems[self.LLM].is_available

        # SAFE_MODE: exchange or data feed is down
        if not exchange_ok or not data_ok:
            return DegradationLevel.SAFE_MODE

        # MONITORING_ONLY: technical analysis is down
        if not technical_ok:
            return DegradationLevel.MONITORING_ONLY

        # TECHNICAL_ONLY: ML models are down
        if not ml_ok and not sentiment_ok and not llm_ok:
            return DegradationLevel.TECHNICAL_ONLY

        # REDUCED_SIGNALS: some signal sources are down
        if not sentiment_ok or not llm_ok:
            return DegradationLevel.REDUCED_SIGNALS

        return DegradationLevel.FULL

    def _check_level_change(self):
        """Check if degradation level changed and fire alerts.

        Must be called with self._lock held.
        """
        new_level = self._compute_level()
        if new_level != self._previous_level:
            old_level = self._previous_level
            direction = "DEGRADED" if new_level > old_level else "RECOVERED"
            message = f"System {direction}: {old_level.name} -> {new_level.name}"
            logger.warning("DEGRADATION LEVEL CHANGE: %s", message)

            if self._alert_callback:
                try:
                    self._alert_callback(new_level, message)
                except Exception:
                    logger.debug("Alert callback failed", exc_info=True)

            for cb in self._level_change_callbacks:
                try:
                    cb(new_level, old_level, message)
                except Exception:
                    logger.debug("Level change callback failed", exc_info=True)

            self._previous_level = new_level

    # --- Operational guidance methods ---

    def can_open_positions(self) -> bool:
        """Can the system safely open new positions?"""
        return self.current_level <= DegradationLevel.TECHNICAL_ONLY

    def can_close_positions(self) -> bool:
        """Can the system close positions? (almost always yes)"""
        return self._subsystems[self.EXCHANGE].is_available

    def should_use_sentiment(self) -> bool:
        """Should sentiment be included in signal fusion?"""
        return self._subsystems[self.SENTIMENT].is_available

    def should_use_ml(self) -> bool:
        """Should ML models be included in signal fusion?"""
        return self._subsystems[self.ML_MODELS].is_available

    def should_use_llm(self) -> bool:
        """Should LLM reasoning be used?"""
        return self._subsystems[self.LLM].is_available

    def should_retry_subsystem(self, subsystem: str) -> bool:
        """Should we retry a failed subsystem (based on backoff)?"""
        health = self._subsystems.get(subsystem)
        if not health or health.status != SubsystemStatus.FAILED:
            return True
        if health.last_failure is None:
            return True
        elapsed = (datetime.utcnow() - health.last_failure).total_seconds()
        return elapsed >= self.recovery_backoff

    def get_signal_weights(self) -> Dict[str, float]:
        """Get adjusted signal weights based on available subsystems.

        Returns weights that the orchestrator should use for signal fusion,
        redistributing weight from unavailable sources.
        """
        level = self.current_level
        if level == DegradationLevel.FULL:
            base_tech = self._config.get("orchestrator", {}).get("tech_weight", 0.60)
            base_sent = self._config.get("orchestrator", {}).get("sentiment_weight", 0.40)
            return {"technical": base_tech, "sentiment": base_sent}
        elif level == DegradationLevel.REDUCED_SIGNALS:
            # Shift sentiment weight to technical
            return {"technical": 0.85, "sentiment": 0.15}
        elif level == DegradationLevel.TECHNICAL_ONLY:
            return {"technical": 1.0, "sentiment": 0.0}
        else:
            return {"technical": 1.0, "sentiment": 0.0}

    def get_confidence_penalty(self) -> float:
        """Get a confidence penalty based on degradation level.

        Applied to all signals when system is degraded, making the
        confidence threshold harder to meet.
        """
        level = self.current_level
        if level == DegradationLevel.FULL:
            return 0.0
        elif level == DegradationLevel.REDUCED_SIGNALS:
            return 5.0  # subtract 5% from confidence
        elif level == DegradationLevel.TECHNICAL_ONLY:
            return 10.0  # subtract 10%
        else:
            return 100.0  # effectively blocks all trades

    @property
    def status(self) -> Dict[str, Any]:
        """Full status for monitoring/dashboard."""
        with self._lock:
            level = self._compute_level()
            return {
                "level": level.name,
                "level_value": int(level),
                "can_open_positions": level <= DegradationLevel.TECHNICAL_ONLY,
                "can_close_positions": self._subsystems[self.EXCHANGE].is_available,
                "subsystems": {
                    name: {
                        "status": health.status.name,
                        "consecutive_failures": health.consecutive_failures,
                        "last_success": health.last_success.isoformat() if health.last_success else None,
                        "last_failure": health.last_failure.isoformat() if health.last_failure else None,
                        "response_time_ms": health.response_time_ms,
                        "error": health.error_message,
                    }
                    for name, health in self._subsystems.items()
                },
                "signal_weights": self.get_signal_weights(),
                "confidence_penalty": self.get_confidence_penalty(),
            }
