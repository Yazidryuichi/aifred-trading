"""Central orchestrator that coordinates all trading agents.

Runs a configurable scan loop that:
1. Collects signals from Technical Analysis and Sentiment agents
2. Fuses signals using weighted ensemble (default 60% tech, 40% sentiment)
3. Applies confidence threshold (default 70%)
4. Routes approved signals through Risk Management for sizing/stops
5. Routes approved+sized orders through Execution agent
6. Logs all decisions with full reasoning
7. Handles errors gracefully (one agent failing does not crash the system)
8. Supports paper trading mode by default
9. Includes circuit breakers (max daily trades, max daily loss, etc.)
"""

import asyncio
import logging
import os
import time
import traceback
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from src.analysis.meta_reasoning import MetaDecision, MetaReasoningAgent
from src.analysis.onchain.onchain_aggregator import OnChainAggregator, OnChainSignal
from src.analysis.sentiment.sentiment_signals import SentimentAnalysisAgent
from src.analysis.technical.signals import TechnicalAnalysisAgent
from src.config import get_config
from src.execution.execution_engine import ExecutionAgent
from src.execution.position_monitor import PositionMonitor
from src.monitoring.degradation_manager import DegradationManager, DegradationLevel
from src.monitoring.model_tracker import ModelTracker
from src.monitoring.trade_logger import TradeLogger
from src.monitoring.telegram_alerts import AlertType, TelegramAlerts
from src.monitoring.telegram_commands import TelegramCommandHandler
from src.optimizer.model_ab_testing import ModelABTestingFramework
from src.optimizer.model_rotation import ModelRotationManager
from src.risk.correlation_tracker import CorrelationTracker
from src.risk.drawdown_manager import DrawdownManager
from src.risk.portfolio_monitor import PortfolioMonitor
from src.risk.account_safety import AccountSafety
from src.risk.risk_gate import RiskGate
from src.risk.stop_manager import calculate_stop_loss, calculate_take_profit
from src.risk.volatility_regime import detect_regime, get_regime_adjustments
from src.utils.types import (
    AssetClass,
    Direction,
    OrderType,
    Position,
    PortfolioState,
    Signal,
    TradeProposal,
    TradeResult,
    TradeStatus,
)

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit breakers to prevent runaway trading.

    Tracks daily trade counts, daily P&L, consecutive failures,
    and enforces hard limits.
    """

    def __init__(self, config: Dict[str, Any]):
        orch_cfg = config.get("orchestrator", {})
        risk_cfg = config.get("risk", {})
        exec_cfg = config.get("execution", {})

        self.max_daily_trades = orch_cfg.get("max_daily_trades", 8)
        safety_cfg = config.get("safety", {})
        self.max_daily_loss_pct = safety_cfg.get("daily_loss_limit_pct", 2.0)
        self.max_consecutive_failures = exec_cfg.get("max_consecutive_failures", 3)

        self._daily_trade_count: int = 0
        self._daily_pnl: float = 0.0
        self._portfolio_value: float = 0.0
        self._consecutive_failures: int = 0
        self._last_reset_date: Optional[datetime] = None
        self._tripped: bool = False
        self._trip_reason: str = ""
        self._trip_until: Optional[datetime] = None

    def reset_daily(self, portfolio_value: float) -> None:
        """Reset daily counters (call at start of each trading day)."""
        self._daily_trade_count = 0
        self._daily_pnl = 0.0
        self._portfolio_value = portfolio_value
        self._last_reset_date = datetime.utcnow()
        # Clear trip if it was daily
        if self._tripped and self._trip_until and datetime.utcnow() >= self._trip_until:
            self._tripped = False
            self._trip_reason = ""
            self._trip_until = None
            logger.info("Circuit breaker reset after cooldown expired")

    def record_trade(self, pnl: float, success: bool) -> None:
        """Record a trade outcome."""
        self._daily_trade_count += 1
        self._daily_pnl += pnl

        if success:
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1

    def check(self) -> tuple:
        """Check all circuit breakers.

        Returns:
            (tripped: bool, reason: str)
        """
        # Check existing trip with cooldown
        if self._tripped:
            if self._trip_until and datetime.utcnow() >= self._trip_until:
                self._tripped = False
                self._trip_reason = ""
                self._trip_until = None
                logger.info("Circuit breaker cooldown expired, resuming")
            else:
                return True, self._trip_reason

        # Check daily trade limit
        if self._daily_trade_count >= self.max_daily_trades:
            self._trip("max_daily_trades", hours=4)
            return True, (
                f"Daily trade limit reached: {self._daily_trade_count}/{self.max_daily_trades}"
            )

        # Check daily loss limit
        if self._portfolio_value > 0:
            daily_loss_pct = abs(min(0, self._daily_pnl)) / self._portfolio_value * 100
            if daily_loss_pct >= self.max_daily_loss_pct:
                self._trip("max_daily_loss", hours=24)
                return True, (
                    f"Daily loss limit reached: {daily_loss_pct:.2f}% "
                    f"(limit: {self.max_daily_loss_pct:.1f}%)"
                )

        # Check consecutive execution failures
        if self._consecutive_failures >= self.max_consecutive_failures:
            self._trip("consecutive_failures", hours=1)
            return True, (
                f"Consecutive execution failures: {self._consecutive_failures} "
                f"(limit: {self.max_consecutive_failures})"
            )

        return False, "OK"

    def _trip(self, reason_type: str, hours: int = 4) -> None:
        """Trip the circuit breaker."""
        self._tripped = True
        self._trip_reason = f"Circuit breaker tripped: {reason_type}"
        self._trip_until = datetime.utcnow() + timedelta(hours=hours)
        logger.warning(
            "CIRCUIT BREAKER TRIPPED: %s. Cooldown until %s",
            reason_type, self._trip_until.isoformat(),
        )

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "tripped": self._tripped,
            "reason": self._trip_reason,
            "trip_until": self._trip_until.isoformat() if self._trip_until else None,
            "daily_trades": self._daily_trade_count,
            "max_daily_trades": self.max_daily_trades,
            "daily_pnl": self._daily_pnl,
            "consecutive_failures": self._consecutive_failures,
        }


class Orchestrator:
    """Central coordinator for the multi-agent trading system.

    Runs a scan loop at configurable intervals, collects signals from
    all analysis agents, fuses them, applies risk management, and
    routes approved trades through execution.
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the orchestrator with full configuration.

        Args:
            config: Full configuration dict (from default.yaml).
        """
        self.config = config
        orch_cfg = config.get("orchestrator", {})

        # Core parameters
        self.scan_interval = config.get("system", {}).get("scan_interval", 60)
        self.min_confidence = orch_cfg.get("min_confidence_threshold", 78)
        self.signal_weights = orch_cfg.get("signal_weights", {
            "technical": 0.60,
            "sentiment": 0.40,
        })
        self.max_daily_trades = orch_cfg.get("max_daily_trades", 8)

        # Trading mode
        exec_cfg = config.get("execution", {})
        self._paper_mode = exec_cfg.get("mode", "paper") == "paper"

        # Assets to scan
        self._assets = self._build_asset_list(config)

        # Initialize agents (with graceful error handling)
        self._tech_agent: Optional[TechnicalAnalysisAgent] = None
        self._sentiment_agent: Optional[SentimentAnalysisAgent] = None
        self._risk_gate: Optional[RiskGate] = None
        self._execution_agent: Optional[ExecutionAgent] = None
        self._trade_logger: Optional[TradeLogger] = None
        self._telegram: Optional[TelegramAlerts] = None
        self._drawdown_manager: Optional[DrawdownManager] = None
        self._portfolio_monitor: Optional[PortfolioMonitor] = None
        self._correlation_tracker: Optional[CorrelationTracker] = None
        self._position_monitor: Optional[PositionMonitor] = None
        self._meta_agent: Optional[MetaReasoningAgent] = None
        self._onchain_aggregator: Optional[OnChainAggregator] = None

        # Circuit breaker
        self._circuit_breaker = CircuitBreaker(config)

        # Graceful degradation manager
        self._degradation = DegradationManager(config)

        # Hard account safety limits (non-overridable)
        self._safety_limits = AccountSafety(config)

        # Model A/B testing and rotation
        data_cfg = config.get("data", {})
        ab_data_dir = os.path.join(
            os.path.dirname(data_cfg.get("sqlite_path", "data/trading.db")),
            "ab_testing",
        )
        self._model_tracker = ModelTracker()
        self._ab_framework = ModelABTestingFramework(data_dir=ab_data_dir)
        self._rotation_manager = ModelRotationManager(
            ab_framework=self._ab_framework,
            model_tracker=self._model_tracker,
            data_dir=ab_data_dir,
        )
        self._rotation_check_interval = orch_cfg.get(
            "rotation_check_every_n_cycles", 10
        )

        # State
        self._running = False
        self._scan_count = 0
        self._last_scan_time: Optional[datetime] = None
        self._daily_trade_count = 0
        self._error_counts: Dict[str, int] = defaultdict(int)
        self._decision_log: List[Dict[str, Any]] = []

        # Data provider callback (set externally)
        self._data_provider: Optional[Callable] = None
        self._news_provider: Optional[Callable] = None

        # New P1 integrations (set via setter methods)
        self._exchange: Optional[Any] = None       # AbstractExchange instance
        self._ws_manager: Optional[Any] = None     # WebSocketManager instance
        self._reconciler: Optional[Any] = None     # PositionReconciler instance
        self._last_reconciliation_time: float = 0.0
        self._reconciliation_interval: int = config.get(
            "reconciliation", {}
        ).get("interval_seconds", 300)  # default 5 min

        # Telegram command handler (initialized via setup_telegram_commands)
        self._telegram_commands: Optional[TelegramCommandHandler] = None

    def _build_asset_list(self, config: Dict[str, Any]) -> Dict[str, AssetClass]:
        """Build flat asset -> asset_class mapping from config."""
        assets = {}
        asset_cfg = config.get("assets", {})
        for class_name, class_enum in [
            ("crypto", AssetClass.CRYPTO),
            ("stocks", AssetClass.STOCKS),
            ("forex", AssetClass.FOREX),
        ]:
            for symbol in asset_cfg.get(class_name, []):
                assets[symbol] = class_enum
        return assets

    def initialize_agents(self) -> Dict[str, bool]:
        """Initialize all sub-agents. Returns status per agent.

        Each agent is initialized independently so one failure
        does not prevent others from running.
        """
        status = {}

        # Technical Analysis Agent
        try:
            self._tech_agent = TechnicalAnalysisAgent(config_override=self.config)
            status["technical"] = True
            logger.info("Technical Analysis Agent initialized")
        except Exception as e:
            logger.error("Failed to initialize Technical Analysis Agent: %s", e)
            status["technical"] = False
            self._error_counts["init_technical"] += 1

        # Sentiment Analysis Agent
        try:
            sentiment_cfg = self.config.get("sentiment", {})
            social_cfg = sentiment_cfg.get("social", {})
            self._sentiment_agent = SentimentAnalysisAgent(
                subreddits=social_cfg.get("reddit_subreddits"),
            )
            status["sentiment"] = True
            logger.info("Sentiment Analysis Agent initialized")
        except Exception as e:
            logger.error("Failed to initialize Sentiment Analysis Agent: %s", e)
            status["sentiment"] = False
            self._error_counts["init_sentiment"] += 1

        # On-Chain Aggregator (DeFiLlama + Etherscan)
        try:
            onchain_cfg = self.config.get("onchain", {})
            etherscan_key = onchain_cfg.get("etherscan_api_key")
            self._onchain_aggregator = OnChainAggregator(
                etherscan_api_key=etherscan_key,
            )
            status["onchain"] = True
            logger.info("On-Chain Aggregator initialized")
        except Exception as e:
            logger.error("Failed to initialize On-Chain Aggregator: %s", e)
            status["onchain"] = False
            self._error_counts["init_onchain"] += 1

        # Risk Management subsystem
        try:
            self._portfolio_monitor = PortfolioMonitor(self.config)
            self._drawdown_manager = DrawdownManager(self.config)
            self._correlation_tracker = CorrelationTracker(self.config)
            self._risk_gate = RiskGate(
                portfolio_monitor=self._portfolio_monitor,
                drawdown_manager=self._drawdown_manager,
                correlation_tracker=self._correlation_tracker,
                config=self.config,
            )
            status["risk"] = True
            logger.info("Risk Management Agent initialized")
        except Exception as e:
            logger.error("Failed to initialize Risk Management Agent: %s", e)
            status["risk"] = False
            self._error_counts["init_risk"] += 1

        # Execution Agent
        try:
            self._execution_agent = ExecutionAgent(self.config)
            status["execution"] = True
            mode_str = "PAPER" if self._paper_mode else "LIVE"
            logger.info("Execution Agent initialized (%s mode)", mode_str)
        except Exception as e:
            logger.error("Failed to initialize Execution Agent: %s", e)
            status["execution"] = False
            self._error_counts["init_execution"] += 1

        # Position Monitor (requires execution agent)
        try:
            if self._execution_agent is not None:
                monitor_cfg = self.config.get("position_monitor", {})
                check_interval = monitor_cfg.get(
                    "check_interval_seconds",
                    self.config.get("orchestrator", {}).get("position_check_interval", 30),
                )
                self._position_monitor = PositionMonitor(
                    execution_agent=self._execution_agent,
                    price_provider=self._get_price_for_monitor,
                    config=self.config,
                    check_interval=float(check_interval),
                )
                status["position_monitor"] = True
                logger.info("Position Monitor initialized (interval=%ds)", check_interval)
            else:
                status["position_monitor"] = False
                logger.warning("Position Monitor not initialized: execution agent unavailable")
        except Exception as e:
            logger.error("Failed to initialize Position Monitor: %s", e)
            status["position_monitor"] = False
            self._error_counts["init_position_monitor"] += 1

        # Trade Logger
        try:
            data_cfg = self.config.get("data", {})
            db_path = data_cfg.get("sqlite_path", "data/trading.db")
            self._trade_logger = TradeLogger(db_path=db_path)
            status["trade_logger"] = True
        except Exception as e:
            logger.error("Failed to initialize Trade Logger: %s", e)
            status["trade_logger"] = False

        # Telegram Alerts
        try:
            mon_cfg = self.config.get("monitoring", {})
            tg_cfg = mon_cfg.get("telegram", {})
            alert_cfg = mon_cfg.get("alerts", {})
            self._telegram = TelegramAlerts(
                bot_token=tg_cfg.get("bot_token", ""),
                chat_id=tg_cfg.get("chat_id", ""),
                alert_config=alert_cfg,
            )
            status["telegram"] = True
        except Exception as e:
            logger.error("Failed to initialize Telegram Alerts: %s", e)
            status["telegram"] = False

        # Meta-Reasoning Agent (LLM-powered decision layer)
        try:
            meta_cfg = self.config.get("meta_reasoning", {})
            if meta_cfg.get("enabled", False):
                self._meta_agent = MetaReasoningAgent(self.config)
                status["meta_reasoning"] = self._meta_agent.enabled
                if self._meta_agent.enabled:
                    logger.info("Meta-Reasoning Agent initialized (model=%s)", meta_cfg.get("model"))
                else:
                    logger.warning("Meta-Reasoning Agent created but disabled (missing API key?)")
            else:
                status["meta_reasoning"] = False
                logger.info("Meta-Reasoning Agent disabled by config")
        except Exception as e:
            logger.error("Failed to initialize Meta-Reasoning Agent: %s", e)
            status["meta_reasoning"] = False
            self._error_counts["init_meta_reasoning"] += 1

        # Wire up degradation manager alert callback to Telegram
        if self._telegram:
            tg = self._telegram
            def _degradation_alert(level: DegradationLevel, message: str):
                tg.send_alert(
                    f"DEGRADATION: {message} (level={level.name})",
                    AlertType.SYSTEM_ERROR,
                )
            self._degradation.set_alert_callback(_degradation_alert)

        # Wire up account safety limits
        if self._telegram:
            self._safety_limits.set_telegram(self._telegram)
        if self._execution_agent is not None:
            # Share the same AccountSafety instance with the execution engine
            self._execution_agent._safety_limits = self._safety_limits

        return status

    def setup_telegram_commands(self) -> None:
        """Initialize Telegram command handler for /kill, /resume, /status."""
        if not self._telegram or not self._telegram._enabled:
            return
        self._telegram_commands = TelegramCommandHandler(
            bot_token=self._telegram.bot_token,
            chat_id=self._telegram.chat_id,
            safety_ref=self._safety_limits,
            orchestrator_ref=self,
        )
        logger.info("Telegram commands enabled: /kill, /resume, /status")

    def set_data_provider(self, provider: Callable) -> None:
        """Set callback to fetch market data for an asset.

        Provider signature: (asset: str, timeframe: str) -> pd.DataFrame
        Must return OHLCV DataFrame with DatetimeIndex.
        """
        self._data_provider = provider

    def set_news_provider(self, provider: Callable) -> None:
        """Set callback to fetch news for an asset.

        Provider signature: (asset: str) -> List[str]
        Returns list of news text strings.
        """
        self._news_provider = provider

    def set_portfolio_value(self, total_value: float, cash: float) -> None:
        """Set initial portfolio value for risk calculations."""
        if self._portfolio_monitor:
            self._portfolio_monitor.set_portfolio_value(total_value, cash)
        if self._drawdown_manager:
            self._drawdown_manager.initialize(total_value)
        self._circuit_breaker.reset_daily(total_value)
        self._safety_limits.initialize_session(total_value)

    def set_exchange(self, exchange: Any) -> None:
        """Set the AbstractExchange instance for unified order routing.

        Args:
            exchange: An AbstractExchange subclass (Live, Paper, or Backtest).
        """
        self._exchange = exchange
        logger.info("Exchange set: %s (live=%s)", exchange.name, exchange.is_live)

    def set_websocket_manager(self, ws_manager: Any) -> None:
        """Set the WebSocketManager for real-time price feeds.

        When set, the position monitor and price lookups will prefer
        WebSocket prices over REST data provider calls.

        Args:
            ws_manager: A WebSocketManager instance (may be None).
        """
        self._ws_manager = ws_manager
        if ws_manager is not None:
            logger.info("WebSocket manager attached to orchestrator")

    def set_reconciler(self, reconciler: Any) -> None:
        """Set the PositionReconciler for startup and periodic reconciliation.

        Args:
            reconciler: A PositionReconciler instance.
        """
        self._reconciler = reconciler
        logger.info("Position reconciler attached to orchestrator")

    def get_execution_agent(self) -> Optional[ExecutionAgent]:
        """Return the execution agent (for external wiring, e.g. reconciliation)."""
        return self._execution_agent

    async def cancel_pending_orders(self) -> None:
        """Cancel all pending orders on exchanges. Called during graceful shutdown."""
        if not self._execution_agent:
            return
        connectors = getattr(self._execution_agent, '_connectors', {})
        for name, connector in connectors.items():
            try:
                open_orders = connector.fetch_open_orders()
                for order in open_orders:
                    connector.cancel_order(order['id'], order.get('symbol'))
                    logger.info("Cancelled order %s on %s", order['id'], name)
            except Exception as e:
                logger.error("Error cancelling orders on %s: %s", name, e)

    async def run(self) -> None:
        """Start the main scan loop. Runs until stop() is called."""
        self._running = True
        mode_str = "PAPER" if self._paper_mode else "LIVE"
        logger.info(
            "Orchestrator starting scan loop: interval=%ds, mode=%s, "
            "confidence_threshold=%d%%, assets=%d",
            self.scan_interval, mode_str, self.min_confidence, len(self._assets),
        )

        # Start the background position monitor
        if self._position_monitor is not None:
            await self._position_monitor.start()
            logger.info("Position monitor started as background task")

        try:
            while self._running:
                scan_start = time.monotonic()
                try:
                    await self._run_scan_cycle()
                except Exception as e:
                    logger.error(
                        "Scan cycle failed with unhandled error: %s\n%s",
                        e, traceback.format_exc(),
                    )
                    self._error_counts["scan_cycle"] += 1
                    if self._telegram:
                        self._telegram.alert_system_error("orchestrator", str(e))

                # Sleep for remainder of interval
                elapsed = time.monotonic() - scan_start
                sleep_time = max(0, self.scan_interval - elapsed)
                if sleep_time > 0 and self._running:
                    await asyncio.sleep(sleep_time)
        finally:
            # Ensure position monitor is stopped on exit
            if self._position_monitor is not None:
                await self._position_monitor.stop()
                logger.info("Position monitor stopped")
            # Close on-chain aggregator HTTP sessions
            if self._onchain_aggregator is not None:
                await self._onchain_aggregator.close()
                logger.info("On-chain aggregator closed")

        logger.info("Orchestrator scan loop stopped")

    def stop(self) -> None:
        """Signal the orchestrator to stop after the current scan cycle.

        This is synchronous -- it just sets the flag. The run() method's
        finally block handles stopping the position monitor gracefully.
        """
        logger.info("Orchestrator stop requested")
        self._running = False

    def kill_switch(self, reason: str = "manual") -> Dict[str, Any]:
        """EMERGENCY: Activate the kill switch and close all open positions.

        This activates the hard safety kill switch (blocking all new trades)
        and then attempts to close every open position immediately.

        Args:
            reason: Why the kill switch was activated.

        Returns:
            Dict with kill switch status and position close results.
        """
        # Activate the hard kill switch first (blocks all new trades)
        self._safety_limits.activate_kill_switch(reason)

        # Also stop the scan loop
        self._running = False

        # Close all open positions
        close_results = []
        if self._execution_agent is not None:
            positions = self._execution_agent.get_open_positions()
            for position in positions:
                try:
                    result = self._execution_agent.close_position(
                        position, reason=f"kill_switch:{reason}",
                    )
                    close_results.append({
                        "asset": position.asset,
                        "status": result.status.value,
                        "fill_price": result.fill_price,
                        "error": result.error,
                    })
                    logger.critical(
                        "Kill switch: closed %s %s, status=%s",
                        position.side, position.asset, result.status.value,
                    )
                except Exception as e:
                    close_results.append({
                        "asset": position.asset,
                        "status": "error",
                        "error": str(e),
                    })
                    logger.critical(
                        "Kill switch: FAILED to close %s: %s",
                        position.asset, e,
                    )

        return {
            "killed": True,
            "reason": reason,
            "positions_closed": len(close_results),
            "close_results": close_results,
        }

    async def _run_scan_cycle(self) -> None:
        """Execute one complete scan cycle across all assets.

        Follows close-before-open pattern: check existing positions for exits
        BEFORE scanning for new entry signals.
        """
        # File-based kill switch (Railway-friendly emergency stop)
        kill_file = os.path.join(
            self.config.get("data", {}).get("base_dir", "data"),
            "KILL_SWITCH",
        )
        if os.path.exists(kill_file):
            if not self._safety_limits._state.killed:
                try:
                    with open(kill_file) as f:
                        reason = f.read().strip() or "file-based kill switch"
                except Exception:
                    reason = "file-based kill switch"
                self._safety_limits.activate_kill_switch(reason)
                logger.critical("FILE-BASED KILL SWITCH DETECTED: %s", kill_file)
            return  # Skip this scan cycle

        # Poll for Telegram commands
        if self._telegram_commands and self._telegram:
            try:
                await self._telegram_commands.poll_updates(
                    self._telegram.send_alert_async
                )
            except Exception as e:
                logger.debug("Telegram command poll error: %s", e)

        self._scan_count += 1
        self._last_scan_time = datetime.utcnow()
        cycle_start = time.monotonic()

        logger.info("=== Scan cycle #%d started ===", self._scan_count)

        # Check circuit breakers first
        tripped, trip_reason = self._circuit_breaker.check()
        if tripped:
            logger.warning("Circuit breaker active: %s. Skipping scan.", trip_reason)
            return

        # Check drawdown pause
        if self._drawdown_manager:
            paused, pause_reason = self._drawdown_manager.check_pause_rules()
            if paused:
                logger.warning("Trading paused (drawdown): %s", pause_reason)
                return

        # --- Periodic reconciliation (every N seconds, controlled by config) ---
        await self._run_periodic_reconciliation()

        # --- Periodic model rotation check (every N cycles) ---
        if (
            self._rotation_check_interval > 0
            and self._scan_count % self._rotation_check_interval == 0
        ):
            try:
                rotation_actions = self._rotation_manager.check_and_rotate()
                for ra in rotation_actions:
                    logger.info("Model rotation action: %s", ra)
                    if self._telegram and ra.get("type") == "promotion":
                        self._telegram.send_alert(
                            f"Model rotation: {ra.get('model_type')} champion "
                            f"changed from {ra.get('old_champion')} to "
                            f"{ra.get('new_champion')}",
                            AlertType.SYSTEM_ERROR,
                        )
            except Exception as e:
                logger.error("Model rotation check failed: %s", e)
                self._error_counts["model_rotation"] += 1

        # --- Phase 1: Process exits for existing positions (close-before-open) ---
        exits_processed = await self._process_exits()

        # --- Phase 2: Scan each asset for new entry signals ---
        signals_generated = 0
        trades_executed = 0

        for asset, asset_class in self._assets.items():
            try:
                result = await self._process_asset(asset, asset_class)
                if result.get("signal_generated"):
                    signals_generated += 1
                if result.get("trade_executed"):
                    trades_executed += 1
            except Exception as e:
                logger.error(
                    "Error processing asset %s: %s\n%s",
                    asset, e, traceback.format_exc(),
                )
                self._error_counts[f"asset_{asset}"] += 1

        elapsed = time.monotonic() - cycle_start
        logger.info(
            "=== Scan cycle #%d complete: %.1fs, %d signals, %d trades, %d exits ===",
            self._scan_count, elapsed, signals_generated, trades_executed,
            exits_processed,
        )

        # Write heartbeat file so the health server knows the loop is alive
        try:
            heartbeat_dir = self.config.get("data", {}).get("base_dir", "data")
            os.makedirs(heartbeat_dir, exist_ok=True)
            heartbeat_path = os.path.join(heartbeat_dir, ".heartbeat")
            with open(heartbeat_path, "w") as hb:
                hb.write(str(time.time()))
        except Exception as e:
            logger.warning("Failed to write heartbeat file: %s", e)

    async def _run_periodic_reconciliation(self) -> None:
        """Run periodic position reconciliation if enough time has elapsed.

        Checks whether the configured reconciliation interval has passed since
        the last reconciliation. If so, delegates to the PositionReconciler
        which persists state to SQLite and (in live mode) compares with
        exchange positions.
        """
        if self._reconciler is None:
            return

        now = time.monotonic()
        if (now - self._last_reconciliation_time) < self._reconciliation_interval:
            return

        self._last_reconciliation_time = now
        try:
            if self._execution_agent is not None:
                local_positions = {
                    p.asset: p
                    for p in self._execution_agent.get_open_positions()
                }
                # Exchange connectors dict expected by reconciler
                exchange_connectors = {}
                if hasattr(self._execution_agent, '_connectors') and self._execution_agent._connectors:
                    exchange_connectors = self._execution_agent._connectors
                elif hasattr(self._execution_agent, '_connector') and self._execution_agent._connector:
                    exchange_connectors = {"default": self._execution_agent._connector}

                result = self._reconciler.reconcile_periodic(
                    local_positions=local_positions,
                    exchange_connectors=exchange_connectors,
                    paper_mode=self._paper_mode,
                )
                if result.actions_taken:
                    logger.info(
                        "Periodic reconciliation: actions=%s",
                        result.actions_taken,
                    )
                else:
                    logger.debug("Periodic reconciliation: no discrepancies")
        except Exception as e:
            logger.error("Periodic reconciliation failed: %s", e)
            self._error_counts["reconciliation"] += 1

    async def _process_exits(self) -> int:
        """Check all open positions and close any that meet exit criteria.

        This is a synchronous check that runs at the START of each scan cycle
        (complementing the background PositionMonitor). The monitor handles
        real-time stop/TP hits between cycles; this handles any that were missed
        and provides an extra safety net.

        Returns:
            Number of positions closed.
        """
        if self._execution_agent is None:
            return 0

        positions = self._execution_agent.get_open_positions()
        if not positions:
            return 0

        exits = 0
        for position in positions:
            try:
                close_reason = self._check_position_exit(position)
                if close_reason is not None:
                    result = self._execution_agent.close_position(
                        position, reason=close_reason,
                    )
                    if result.status == TradeStatus.FILLED:
                        exits += 1
                        self._log_decision(
                            position.asset, "EXIT",
                            f"Position closed: {close_reason} @ {result.fill_price:.4f}",
                        )
                        self._circuit_breaker.record_trade(
                            position.unrealized_pnl, success=True,
                        )
                        if self._telegram:
                            self._telegram.alert_trade_executed(
                                asset=position.asset,
                                side="SELL" if position.side == "LONG" else "BUY",
                                size=position.size,
                                price=result.fill_price,
                                exchange=result.exchange,
                            )
                        logger.info(
                            "Exit executed: %s %s, reason=%s, PnL=%.2f",
                            position.side, position.asset, close_reason,
                            position.unrealized_pnl,
                        )
                    else:
                        logger.warning(
                            "Exit failed for %s: status=%s, error=%s",
                            position.asset, result.status.value, result.error,
                        )
            except Exception as e:
                logger.error(
                    "Error processing exit for %s: %s\n%s",
                    position.asset, e, traceback.format_exc(),
                )
                self._error_counts[f"exit_{position.asset}"] += 1

        return exits

    def _check_position_exit(self, position: Position) -> Optional[str]:
        """Check if a position should be closed based on current price.

        Returns:
            Close reason string, or None if position should stay open.
        """
        current_price = self._get_current_price(position.asset)
        if current_price is None:
            return None

        # Update position price
        position.current_price = current_price
        if position.side == "LONG":
            position.unrealized_pnl = (current_price - position.entry_price) * position.size
        else:
            position.unrealized_pnl = (position.entry_price - current_price) * position.size

        # Check stop-loss
        if position.stop_loss > 0:
            if position.side == "LONG" and current_price <= position.stop_loss:
                return "stop_loss_hit"
            if position.side == "SHORT" and current_price >= position.stop_loss:
                return "stop_loss_hit"

        # Check take-profit
        if position.take_profit > 0:
            if position.side == "LONG" and current_price >= position.take_profit:
                return "take_profit_hit"
            if position.side == "SHORT" and current_price <= position.take_profit:
                return "take_profit_hit"

        return None

    async def _process_asset(
        self, asset: str, asset_class: AssetClass
    ) -> Dict[str, Any]:
        """Process a single asset: analyze, fuse signals, risk check, execute.

        Returns:
            Result dict with processing outcome.
        """
        result = {
            "asset": asset,
            "signal_generated": False,
            "trade_executed": False,
            "reason": "",
        }

        logger.info("Processing asset %s (class=%s)", asset, asset_class.value)

        # -- Step 0: Check degradation level --
        if not self._degradation.can_open_positions():
            result["reason"] = (
                f"degradation_level_{self._degradation.current_level.name}"
                "_blocks_new_entries"
            )
            logger.info(
                "Degradation level %s — skipping new entries for %s",
                self._degradation.current_level.name, asset,
            )
            return result

        # -- Step 1: Collect Technical Signal --
        tech_signal = self._get_technical_signal(asset)

        # -- Step 2: Collect Sentiment Signal (skip if degradation says so) --
        sentiment_signal = None
        if self._degradation.should_use_sentiment():
            sentiment_signal = self._get_sentiment_signal(asset)

        # -- Step 2.5: Collect On-Chain Signal --
        onchain_signal = await self._get_onchain_signal(asset)

        # -- Step 3: Fuse signals (using degradation-adjusted weights) --
        fused_signal = self._fuse_signals(asset, tech_signal, sentiment_signal, onchain_signal)

        if fused_signal is None or fused_signal.direction == Direction.HOLD:
            result["reason"] = "no_actionable_signal"
            return result

        result["signal_generated"] = True

        # -- Step 3.5: Apply degradation confidence penalty --
        confidence_penalty = self._degradation.get_confidence_penalty()
        if confidence_penalty > 0:
            original_conf = fused_signal.confidence
            fused_signal.confidence = max(0.0, fused_signal.confidence - confidence_penalty)
            if fused_signal.metadata is None:
                fused_signal.metadata = {}
            fused_signal.metadata["degradation_penalty"] = confidence_penalty
            fused_signal.metadata["pre_penalty_confidence"] = original_conf
            logger.debug(
                "Applied degradation penalty %.1f%% to %s: %.1f%% -> %.1f%%",
                confidence_penalty, asset, original_conf, fused_signal.confidence,
            )

        # -- Step 3.7: Meta-reasoning (LLM evaluation, optional) --
        meta_decision: Optional[MetaDecision] = None
        meta_size_adjustment = 1.0
        if (
            self._meta_agent is not None
            and self._meta_agent.enabled
            and self._degradation.should_retry_subsystem(DegradationManager.LLM)
        ):
            try:
                meta_decision = await self._run_meta_reasoning(
                    asset, fused_signal, tech_signal, sentiment_signal,
                )
                if meta_decision is not None:
                    # Apply confidence adjustment from meta-reasoning
                    pre_meta_conf = fused_signal.confidence
                    fused_signal.confidence = meta_decision.adjusted_confidence
                    meta_size_adjustment = meta_decision.size_adjustment

                    if fused_signal.metadata is None:
                        fused_signal.metadata = {}
                    fused_signal.metadata["meta_reasoning"] = {
                        "action": meta_decision.action,
                        "original_confidence": meta_decision.original_confidence,
                        "adjusted_confidence": meta_decision.adjusted_confidence,
                        "size_adjustment": meta_decision.size_adjustment,
                        "conviction": meta_decision.conviction,
                        "reasoning": meta_decision.reasoning,
                        "concerns": meta_decision.concerns,
                        "latency_ms": meta_decision.latency_ms,
                    }

                    self._degradation.report_success(
                        DegradationManager.LLM, meta_decision.latency_ms,
                    )
                    logger.info(
                        "Meta-reasoning adjusted %s confidence: %.1f%% -> %.1f%% "
                        "(size x%.2f, conviction=%s)",
                        asset, pre_meta_conf, fused_signal.confidence,
                        meta_size_adjustment, meta_decision.conviction,
                    )

                    # If meta-reasoning says SKIP or HOLD, respect that
                    if meta_decision.action in ("SKIP", "HOLD"):
                        result["reason"] = (
                            f"meta_reasoning_{meta_decision.action.lower()}: "
                            f"{meta_decision.reasoning}"
                        )
                        self._log_decision(
                            asset, f"META_{meta_decision.action}",
                            result["reason"], fused_signal,
                        )
                        return result

            except Exception as e:
                logger.error("Meta-reasoning failed for %s: %s", asset, e)
                self._error_counts["meta_reasoning"] += 1
                self._degradation.report_failure(DegradationManager.LLM, str(e))
                # Continue with original signal (meta-reasoning is optional)

        # -- Step 4: Check confidence threshold --
        if fused_signal.confidence < self.min_confidence:
            result["reason"] = (
                f"confidence_below_threshold: {fused_signal.confidence:.1f}% "
                f"< {self.min_confidence}%"
            )
            self._log_decision(asset, "SKIPPED", result["reason"], fused_signal)
            return result

        # -- Step 5: Build trade proposal --
        proposal = self._build_trade_proposal(asset, asset_class, fused_signal)
        if proposal is None:
            result["reason"] = "failed_to_build_proposal"
            return result

        # Apply meta-reasoning size adjustment (if any)
        if meta_size_adjustment != 1.0:
            proposal.position_size *= meta_size_adjustment
            proposal.position_value *= meta_size_adjustment
            if proposal.metadata is None:
                proposal.metadata = {}
            proposal.metadata["meta_size_adjustment"] = meta_size_adjustment

        # -- Step 6: Risk gate evaluation --
        risk_decision = self._evaluate_risk(proposal)
        if risk_decision is None:
            result["reason"] = "risk_agent_unavailable"
            return result

        if not risk_decision.approved:
            result["reason"] = f"risk_rejected: {risk_decision.reason}"
            self._log_decision(asset, "REJECTED", risk_decision.reason, fused_signal)
            return result

        # -- Step 7: Execute trade --
        trade_result = self._execute_trade(proposal, risk_decision)
        if trade_result is None:
            result["reason"] = "execution_agent_unavailable"
            return result

        if trade_result.status == TradeStatus.FILLED:
            result["trade_executed"] = True
            self._on_trade_executed(asset, trade_result, fused_signal)
        elif trade_result.status == TradeStatus.FAILED:
            result["reason"] = f"execution_failed: {trade_result.error}"
            self._circuit_breaker.record_trade(0.0, success=False)

        return result

    def _get_technical_signal(self, asset: str) -> Optional[Signal]:
        """Get technical analysis signal for an asset.

        Returns None if the agent is unavailable or analysis fails.
        """
        if self._tech_agent is None:
            logger.info("Tech agent is None for %s — skipping", asset)
            return None

        if self._data_provider is None:
            logger.info("No data provider set, skipping technical analysis for %s", asset)
            return None

        # Skip if failed and backoff hasn't elapsed
        if not self._degradation.should_retry_subsystem(DegradationManager.TECHNICAL):
            logger.info("Technical analysis in backoff for %s, skipping", asset)
            return None

        try:
            t0 = time.monotonic()
            data = self._data_provider(asset, "1h")
            if data is None or len(data) < 100:
                logger.info("Insufficient data for technical analysis: %s (%d bars)", asset, len(data) if data is not None else 0)
                return None

            signal = self._tech_agent.analyze(asset, data, timeframe="1h")
            elapsed_ms = (time.monotonic() - t0) * 1000
            self._degradation.report_success(DegradationManager.TECHNICAL, elapsed_ms)
            logger.info(
                "Technical signal for %s: %s (conf=%.1f%%) [%.0fms]",
                asset, signal.direction.value, signal.confidence, elapsed_ms,
            )
            return signal
        except Exception as e:
            logger.error("Technical analysis failed for %s: %s", asset, e, exc_info=True)
            self._error_counts[f"tech_{asset}"] += 1
            self._degradation.report_failure(DegradationManager.TECHNICAL, str(e))
            return None

    def _get_sentiment_signal(self, asset: str) -> Optional[Signal]:
        """Get sentiment analysis signal for an asset.

        Returns None if the agent is unavailable or analysis fails.
        """
        if self._sentiment_agent is None:
            return None

        # Skip if failed and backoff hasn't elapsed
        if not self._degradation.should_retry_subsystem(DegradationManager.SENTIMENT):
            logger.debug("Sentiment analysis in backoff for %s, skipping", asset)
            return None

        try:
            t0 = time.monotonic()
            news_items = None
            if self._news_provider:
                news_items = self._news_provider(asset)

            signal = self._sentiment_agent.analyze(asset, news_items=news_items)
            elapsed_ms = (time.monotonic() - t0) * 1000
            self._degradation.report_success(DegradationManager.SENTIMENT, elapsed_ms)
            logger.debug(
                "Sentiment signal for %s: %s (conf=%.1f%%)",
                asset, signal.direction.value, signal.confidence,
            )
            return signal
        except Exception as e:
            logger.error("Sentiment analysis failed for %s: %s", asset, e)
            self._error_counts[f"sentiment_{asset}"] += 1
            self._degradation.report_failure(DegradationManager.SENTIMENT, str(e))
            return None

    async def _get_onchain_signal(self, asset: str) -> Optional[OnChainSignal]:
        """Get on-chain signal for an asset.

        Returns None if the aggregator is unavailable or the fetch fails.
        """
        if self._onchain_aggregator is None:
            return None

        try:
            t0 = time.monotonic()
            signal = await self._onchain_aggregator.generate_signal(asset)
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.debug(
                "On-chain signal for %s: sentiment=%s whales=%s flow=%s conf=%.2f (%.0fms)",
                asset, signal.defi_sentiment, signal.whale_activity,
                signal.exchange_flow, signal.confidence, elapsed_ms,
            )
            return signal
        except Exception as e:
            logger.error("On-chain analysis failed for %s: %s", asset, e)
            self._error_counts[f"onchain_{asset}"] += 1
            return None

    async def _run_meta_reasoning(
        self,
        asset: str,
        fused_signal: Signal,
        tech_signal: Optional[Signal],
        sentiment_signal: Optional[Signal],
    ) -> Optional[MetaDecision]:
        """Run the meta-reasoning agent on a fused signal.

        Gathers market context (indicators, positions, risk state) and
        asks the LLM to evaluate whether the signal should be acted upon.

        Returns MetaDecision or None if meta-reasoning is unavailable.
        """
        if self._meta_agent is None or not self._meta_agent.enabled:
            return None

        # Gather context for the LLM
        indicators: Dict[str, Any] = {}
        if self._data_provider is not None:
            try:
                data = self._data_provider(asset, "1h")
                if data is not None and len(data) > 0:
                    last = data.iloc[-1]
                    indicators["price"] = float(last.get("close", 0))
                    indicators["volume"] = float(last.get("volume", 0))
                    for col in ["rsi", "macd", "atr", "bb_upper", "bb_lower", "ema_20", "ema_50"]:
                        if col in data.columns:
                            val = last.get(col)
                            if val is not None and np.isfinite(val):
                                indicators[col] = round(float(val), 4)
            except Exception as e:
                logger.debug("Could not gather indicators for meta-reasoning: %s", e)

        # Get positions and portfolio
        positions: List[Position] = []
        portfolio_value = 0.0
        if self._execution_agent is not None:
            positions = self._execution_agent.get_open_positions()
        if self._portfolio_monitor is not None:
            state = self._portfolio_monitor.get_state()
            portfolio_value = state.total_value

        # Get risk state
        risk_state: Dict[str, Any] = {}
        if self._risk_gate is not None:
            risk_state = {
                "streak_info": self._risk_gate.streak_info,
            }
        if self._drawdown_manager is not None:
            risk_state["drawdown"] = {
                "current": getattr(self._drawdown_manager, "current_drawdown_pct", 0.0),
            }
        risk_state["circuit_breaker"] = self._circuit_breaker.status

        # Call meta-reasoning
        decision = await self._meta_agent.evaluate(
            symbol=asset,
            fused_signal=fused_signal,
            tech_signal=tech_signal,
            sentiment_signal=sentiment_signal,
            indicators=indicators,
            positions=positions,
            portfolio_value=portfolio_value,
            risk_state=risk_state,
        )

        # Log for audit
        self._log_decision(
            asset,
            f"META_{decision.action}",
            f"Meta-reasoning: {decision.reasoning} "
            f"(conf {decision.original_confidence:.1f}%->{decision.adjusted_confidence:.1f}%, "
            f"conviction={decision.conviction})",
            fused_signal,
        )

        return decision

    def _fuse_signals(
        self,
        asset: str,
        tech_signal: Optional[Signal],
        sentiment_signal: Optional[Signal],
        onchain_signal: Optional[OnChainSignal] = None,
    ) -> Optional[Signal]:
        """Fuse technical, sentiment, and on-chain signals using weighted combination.

        Default weights: 60% technical, 40% sentiment (configurable).
        When on-chain data is available, weights are re-normalized to include
        ~18% on-chain allocation (configurable via signal_weights.onchain).
        If only one signal is available, it is used with reduced confidence.

        Args:
            asset: Asset symbol.
            tech_signal: Technical analysis signal (may be None).
            sentiment_signal: Sentiment analysis signal (may be None).
            onchain_signal: On-chain aggregated signal (may be None).

        Returns:
            Fused Signal, or None if no signals available.
        """
        # Use degradation-adjusted weights when available
        degradation_weights = self._degradation.get_signal_weights()
        tech_weight = degradation_weights.get("technical", self.signal_weights.get("technical", 0.60))
        sent_weight = degradation_weights.get("sentiment", self.signal_weights.get("sentiment", 0.40))
        onchain_weight = self.signal_weights.get("onchain", 0.18)

        # Build on-chain metadata dict for inclusion in all signal paths
        onchain_meta: Optional[Dict[str, Any]] = None
        if onchain_signal is not None:
            onchain_meta = {
                "defi_sentiment": onchain_signal.defi_sentiment,
                "tvl_trend": onchain_signal.tvl_trend,
                "whale_activity": onchain_signal.whale_activity,
                "exchange_flow": onchain_signal.exchange_flow,
                "confidence": onchain_signal.confidence,
            }
            logger.info(
                "On-chain signal for %s: sentiment=%s tvl=%s whales=%s flow=%s conf=%.2f",
                asset, onchain_signal.defi_sentiment, onchain_signal.tvl_trend,
                onchain_signal.whale_activity, onchain_signal.exchange_flow,
                onchain_signal.confidence,
            )

        if tech_signal is None and sentiment_signal is None:
            return None

        # Single signal available: use its confidence with a mild 15% penalty
        # (not weight * 0.7 which destroys the score — e.g. 85% * 0.6 * 0.7 = 35%)
        if tech_signal is None:
            return Signal(
                asset=asset,
                direction=sentiment_signal.direction,
                confidence=sentiment_signal.confidence * 0.85,  # 15% single-source penalty
                source="fused_sentiment_only",
                timeframe=sentiment_signal.timeframe,
                metadata={
                    "fusion_method": "single_source",
                    "sentiment_signal": {
                        "direction": sentiment_signal.direction.value,
                        "confidence": sentiment_signal.confidence,
                    },
                    "onchain_signal": onchain_meta,
                },
            )

        if sentiment_signal is None:
            return Signal(
                asset=asset,
                direction=tech_signal.direction,
                confidence=tech_signal.confidence * 0.85,  # 15% single-source penalty
                source="fused_technical_only",
                timeframe=tech_signal.timeframe,
                metadata={
                    "fusion_method": "single_source",
                    "technical_signal": {
                        "direction": tech_signal.direction.value,
                        "confidence": tech_signal.confidence,
                        "tier": tech_signal.metadata.get("signal_tier", "?"),
                    },
                    "onchain_signal": onchain_meta,
                },
            )

        # Both tech + sentiment available: weighted fusion
        tech_dir = _direction_to_numeric(tech_signal.direction)
        sent_dir = _direction_to_numeric(sentiment_signal.direction)

        # If on-chain signal is available with non-zero confidence, include it
        if onchain_signal is not None and onchain_signal.confidence > 0:
            _onchain_dir_map = {"bullish": 1.0, "bearish": -1.0, "neutral": 0.0}
            onchain_dir = _onchain_dir_map.get(onchain_signal.defi_sentiment, 0.0)

            # Re-normalize: shrink tech + sentiment proportionally to make room
            scale = (1.0 - onchain_weight) / (tech_weight + sent_weight)
            adj_tech = tech_weight * scale
            adj_sent = sent_weight * scale
            adj_onchain = onchain_weight

            total_weight = adj_tech + adj_sent + adj_onchain
            fused_direction = (
                tech_dir * adj_tech
                + sent_dir * adj_sent
                + onchain_dir * adj_onchain
            ) / total_weight

            # Weighted geometric mean — normalize all confidences to 0-1 scale first
            # tech/sentiment confidence is 0-100, on-chain confidence is already 0-1
            fused_confidence = (
                ((tech_signal.confidence / 100.0) ** adj_tech)
                * ((sentiment_signal.confidence / 100.0) ** adj_sent)
                * (onchain_signal.confidence ** adj_onchain)
                * 100.0
            )
        else:
            adj_tech = tech_weight
            adj_sent = sent_weight
            adj_onchain = 0.0

            total_weight = tech_weight + sent_weight
            fused_direction = (tech_dir * tech_weight + sent_dir * sent_weight) / total_weight

            # Geometric mean for convergence — normalize to 0-1 scale before exponentiation
            fused_confidence = (
                ((tech_signal.confidence / 100.0) ** tech_weight)
                * ((sentiment_signal.confidence / 100.0) ** sent_weight)
                * 100.0
            )

        # Agreement bonus: if both agree, boost confidence
        if (tech_dir > 0 and sent_dir > 0) or (tech_dir < 0 and sent_dir < 0):
            fused_confidence = min(100.0, fused_confidence * 1.35)
            agreement = "aligned"
        elif tech_dir == 0 or sent_dir == 0:
            agreement = "partial"
        else:
            # Disagreement: strong confidence penalty
            fused_confidence *= 0.50
            agreement = "conflicting"

        # Map fused direction back to Direction enum
        final_direction = _numeric_to_direction(fused_direction, fused_confidence)

        return Signal(
            asset=asset,
            direction=final_direction,
            confidence=min(100.0, max(0.0, fused_confidence)),
            source="fused",
            timeframe=tech_signal.timeframe,
            metadata={
                "fusion_method": "weighted_average",
                "tech_weight": adj_tech,
                "sent_weight": adj_sent,
                "onchain_weight": adj_onchain,
                "agreement": agreement,
                "fused_direction_numeric": fused_direction,
                "technical_signal": {
                    "direction": tech_signal.direction.value,
                    "confidence": tech_signal.confidence,
                    "tier": tech_signal.metadata.get("signal_tier", "?"),
                },
                "sentiment_signal": {
                    "direction": sentiment_signal.direction.value,
                    "confidence": sentiment_signal.confidence,
                },
                "onchain_signal": onchain_meta,
            },
        )

    def _calculate_recent_win_rate(self, lookback: int = 30) -> tuple[float, float, float]:
        """Calculate win rate, avg win, avg loss from recent closed trades."""
        try:
            recent_trades = self._trade_logger.get_recent_trades(lookback)
            if len(recent_trades) < 10:
                return 0.55, 0.02, 0.015  # fallback if insufficient data

            wins = [t for t in recent_trades if t.get('pnl', 0) > 0]
            losses = [t for t in recent_trades if t.get('pnl', 0) <= 0]

            win_rate = len(wins) / len(recent_trades) if recent_trades else 0.55
            avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0.02
            avg_loss = abs(np.mean([t['pnl'] for t in losses])) if losses else 0.015

            # Normalize to percentages
            avg_win_pct = min(avg_win, 0.10)  # cap at 10%
            avg_loss_pct = min(avg_loss, 0.10)

            return win_rate, avg_win_pct, avg_loss_pct
        except Exception:
            return 0.55, 0.02, 0.015

    def _build_trade_proposal(
        self,
        asset: str,
        asset_class: AssetClass,
        signal: Signal,
    ) -> Optional[TradeProposal]:
        """Build a TradeProposal from a fused signal.

        Uses current market data for entry price, ATR-based stop/TP,
        and portfolio value for sizing.

        Returns None if insufficient data.
        """
        try:
            # Get current price from data provider
            entry_price = self._get_current_price(asset)
            if entry_price is None or entry_price <= 0:
                logger.warning("Cannot build proposal for %s: no price data", asset)
                return None

            # Get ATR for stop/TP calculation
            atr = self._get_current_atr(asset)
            if atr is None or atr <= 0:
                # Fallback: estimate ATR as 2% of price
                atr = entry_price * 0.02

            # Determine side
            side = "LONG" if signal.direction in (
                Direction.BUY, Direction.STRONG_BUY
            ) else "SHORT"

            # Calculate stop-loss and take-profit
            stop_loss = calculate_stop_loss(
                entry=entry_price, atr=atr, side=side, config=self.config,
            )
            tp_levels = calculate_take_profit(
                entry=entry_price, atr=atr, side=side, config=self.config,
            )
            take_profit = tp_levels[0] if tp_levels else entry_price

            # Calculate position size
            portfolio_value = self._get_portfolio_value()
            if portfolio_value <= 0:
                logger.warning("Portfolio value is zero, cannot size position")
                return None

            from src.risk.position_sizer import calculate_position_size
            streak = self._risk_gate.streak_info if self._risk_gate else {}

            win_rate, avg_win, avg_loss = self._calculate_recent_win_rate()

            # Compute actual stop distance so position sizer uses real risk
            stop_distance_pct = (
                abs(entry_price - stop_loss) / entry_price
                if entry_price > 0 and stop_loss > 0
                else None
            )

            position_value = calculate_position_size(
                portfolio_value=portfolio_value,
                signal_confidence=signal.confidence,
                win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
                config=self.config,
                consecutive_wins=streak.get("consecutive_wins", 0),
                consecutive_losses=streak.get("consecutive_losses", 0),
                stop_distance_pct=stop_distance_pct,
            )

            position_size = position_value / entry_price if entry_price > 0 else 0.0

            # Order type
            order_type_str = self.config.get("execution", {}).get(
                "default_order_type", "limit"
            )
            order_type_map = {
                "limit": OrderType.LIMIT,
                "market": OrderType.MARKET,
                "stop_limit": OrderType.STOP_LIMIT,
            }
            order_type = order_type_map.get(order_type_str, OrderType.LIMIT)

            proposal = TradeProposal(
                signal=signal,
                asset=asset,
                asset_class=asset_class,
                direction=signal.direction,
                entry_price=entry_price,
                position_size=position_size,
                position_value=position_value,
                stop_loss=stop_loss,
                take_profit=take_profit,
                order_type=order_type,
                confidence=signal.confidence,
                metadata={
                    "atr": atr,
                    "signal_source": signal.source,
                    "signal_metadata": signal.metadata,
                },
            )

            logger.info(
                "Trade proposal built: %s %s @ %.4f, size=%.4f ($%.2f), "
                "SL=%.4f, TP=%.4f, conf=%.1f%%",
                signal.direction.value, asset, entry_price,
                position_size, position_value, stop_loss, take_profit,
                signal.confidence,
            )
            return proposal

        except Exception as e:
            logger.error("Failed to build trade proposal for %s: %s", asset, e)
            return None

    def _evaluate_risk(self, proposal: TradeProposal) -> Optional[Any]:
        """Run the proposal through the risk gate.

        Returns RiskDecision or None if risk agent is unavailable.
        """
        if self._risk_gate is None:
            logger.warning("Risk gate not initialized, cannot evaluate proposal")
            return None

        try:
            portfolio = self._get_portfolio_state()
            decision = self._risk_gate.evaluate(proposal, portfolio)
            return decision
        except Exception as e:
            logger.error("Risk evaluation failed for %s: %s", proposal.asset, e)
            self._error_counts["risk_evaluation"] += 1
            return None

    def _execute_trade(
        self, proposal: TradeProposal, risk_decision: Any
    ) -> Optional[TradeResult]:
        """Execute a risk-approved trade.

        Returns TradeResult or None if execution agent is unavailable.
        """
        if self._execution_agent is None:
            logger.warning("Execution agent not initialized")
            return None

        try:
            t0 = time.monotonic()
            result = self._execution_agent.execute(proposal, risk_decision)
            elapsed_ms = (time.monotonic() - t0) * 1000
            if result.status == TradeStatus.FILLED:
                self._degradation.report_success(DegradationManager.EXCHANGE, elapsed_ms)
            elif result.status == TradeStatus.FAILED:
                self._degradation.report_failure(
                    DegradationManager.EXCHANGE, result.error or "execution_failed",
                )
            return result
        except Exception as e:
            logger.error("Trade execution failed for %s: %s", proposal.asset, e)
            self._error_counts["execution"] += 1
            self._degradation.report_failure(DegradationManager.EXCHANGE, str(e))
            return None

    def _on_trade_executed(
        self,
        asset: str,
        trade_result: TradeResult,
        signal: Signal,
    ) -> None:
        """Handle post-execution bookkeeping."""
        proposal = trade_result.proposal

        # Log the trade
        if self._trade_logger:
            try:
                self._trade_logger.log_trade(trade_result)
            except Exception as e:
                logger.error("Failed to log trade: %s", e)

        # Update circuit breaker
        self._circuit_breaker.record_trade(0.0, success=True)

        # Send telegram alert
        if self._telegram:
            side = "BUY" if proposal.direction in (
                Direction.BUY, Direction.STRONG_BUY
            ) else "SELL"
            self._telegram.alert_trade_executed(
                asset=asset,
                side=side,
                size=trade_result.fill_size,
                price=trade_result.fill_price,
                exchange=trade_result.exchange,
            )

        # Log decision
        self._log_decision(
            asset, "EXECUTED",
            f"Filled: {trade_result.fill_size:.6f} @ {trade_result.fill_price:.4f} "
            f"on {trade_result.exchange}",
            signal,
        )

        # Record outcomes for any active A/B test sessions
        active_sessions = self._ab_framework.get_active_sessions()
        if active_sessions and signal is not None:
            for sess in active_sessions:
                session_id = sess["session_id"]
                champion = self._ab_framework.get_candidate(
                    sess["champion_id"],
                )
                challenger = self._ab_framework.get_candidate(
                    sess["challenger_id"],
                )
                if champion is None or challenger is None:
                    continue
                # Only record if the signal source matches a tested model
                if signal.source in (
                    champion.model_type, challenger.model_type,
                    champion.model_id, challenger.model_id,
                ):
                    is_champ = signal.source in (
                        champion.model_type, champion.model_id,
                    )
                    self._ab_framework.record_signal_outcome(
                        session_id=session_id,
                        champion_correct=is_champ,
                        challenger_correct=not is_champ,
                    )

        logger.info(
            "Trade executed: %s %s @ %.4f, size=%.6f, exchange=%s, slippage=%.4f%%",
            proposal.direction.value, asset, trade_result.fill_price,
            trade_result.fill_size, trade_result.exchange, trade_result.slippage,
        )

    def _get_current_price(self, asset: str) -> Optional[float]:
        """Get current price for an asset.

        Checks WebSocket cache first, then falls back to REST data provider.
        Reports health to degradation manager.
        """
        # Try WebSocket cache first
        if self._ws_manager is not None:
            ws_price = self._ws_manager.get_price(asset)
            if ws_price is not None and ws_price > 0:
                self._degradation.report_success(DegradationManager.DATA_FEED)
                return ws_price

        # Fall back to REST data provider
        if self._data_provider is None:
            return None
        try:
            data = self._data_provider(asset, "1h")
            if data is not None and len(data) > 0:
                self._degradation.report_success(DegradationManager.DATA_FEED)
                return float(data["close"].iloc[-1])
        except Exception as e:
            logger.error("Failed to get price for %s: %s", asset, e)
            self._degradation.report_failure(DegradationManager.DATA_FEED, str(e))
        return None

    def _get_price_for_monitor(self, asset: str) -> Optional[float]:
        """Price provider callback for the PositionMonitor.

        Tries WebSocket cache first for sub-second latency, then falls
        back to the REST data provider.
        """
        # Try WebSocket cache first (fastest path)
        if self._ws_manager is not None:
            ws_price = self._ws_manager.get_price(asset)
            if ws_price is not None and ws_price > 0:
                return ws_price

        # Fall back to REST data provider
        return self._get_current_price(asset)

    def _get_current_atr(self, asset: str) -> Optional[float]:
        """Get current ATR for an asset."""
        if self._data_provider is None:
            return None
        try:
            data = self._data_provider(asset, "1h")
            if data is not None and "atr" in data.columns and len(data) > 0:
                val = data["atr"].iloc[-1]
                if np.isfinite(val):
                    return float(val)
        except Exception:
            pass
        return None

    def _get_portfolio_value(self) -> float:
        """Get current portfolio total value."""
        if self._portfolio_monitor:
            state = self._portfolio_monitor.get_state()
            return state.total_value
        return 0.0

    def _get_portfolio_state(self) -> PortfolioState:
        """Get current portfolio state."""
        if self._portfolio_monitor:
            return self._portfolio_monitor.get_state()
        return PortfolioState(total_value=0.0, cash=0.0)

    def _log_decision(
        self,
        asset: str,
        action: str,
        reason: str,
        signal: Optional[Signal] = None,
    ) -> None:
        """Log a decision with full context."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "scan_cycle": self._scan_count,
            "asset": asset,
            "action": action,
            "reason": reason,
        }
        if signal:
            entry["signal"] = {
                "direction": signal.direction.value,
                "confidence": signal.confidence,
                "source": signal.source,
            }
        self._decision_log.append(entry)

        # Keep log bounded
        if len(self._decision_log) > 10000:
            self._decision_log = self._decision_log[-5000:]

    # --- Status and diagnostics ---

    @property
    def is_running(self) -> bool:
        return self._running

    def get_status(self) -> Dict[str, Any]:
        """Get full orchestrator status for monitoring."""
        return {
            "running": self._running,
            "mode": "paper" if self._paper_mode else "live",
            "scan_count": self._scan_count,
            "scan_interval": self.scan_interval,
            "last_scan": self._last_scan_time.isoformat() if self._last_scan_time else None,
            "min_confidence": self.min_confidence,
            "signal_weights": self.signal_weights,
            "assets_count": len(self._assets),
            "circuit_breaker": self._circuit_breaker.status,
            "error_counts": dict(self._error_counts),
            "agents": {
                "technical": self._tech_agent is not None,
                "sentiment": self._sentiment_agent is not None,
                "risk": self._risk_gate is not None,
                "execution": self._execution_agent is not None,
                "position_monitor": self._position_monitor is not None,
                "trade_logger": self._trade_logger is not None,
                "telegram": self._telegram is not None,
                "meta_reasoning": (
                    self._meta_agent is not None and self._meta_agent.enabled
                ),
            },
            "meta_reasoning": (
                self._meta_agent.status if self._meta_agent else {"enabled": False}
            ),
            "position_monitor": (
                self._position_monitor.get_status()
                if self._position_monitor else None
            ),
            "account_safety": self._safety_limits.status,
            "exchange": (
                {"name": self._exchange.name, "is_live": self._exchange.is_live}
                if self._exchange else None
            ),
            "websocket": (
                self._ws_manager.status()
                if self._ws_manager else None
            ),
            "reconciler_active": self._reconciler is not None,
            "degradation": self._degradation.status,
            "model_ab_testing": self._ab_framework.status,
            "model_rotation": self._rotation_manager.status,
        }

    @property
    def decision_log(self) -> List[Dict[str, Any]]:
        """Return recent decision log entries."""
        return list(self._decision_log[-100:])


# --- Helper functions ---

def _direction_to_numeric(direction: Direction) -> float:
    """Convert Direction enum to numeric value for signal fusion."""
    mapping = {
        Direction.STRONG_BUY: 1.0,
        Direction.BUY: 0.5,
        Direction.HOLD: 0.0,
        Direction.SELL: -0.5,
        Direction.STRONG_SELL: -1.0,
    }
    return mapping.get(direction, 0.0)


def _numeric_to_direction(value: float, confidence: float) -> Direction:
    """Convert numeric direction value to Direction enum."""
    if value > 0.4:
        return Direction.STRONG_BUY if confidence > 75 else Direction.BUY
    elif value > 0.15:
        return Direction.BUY
    elif value < -0.4:
        return Direction.STRONG_SELL if confidence > 75 else Direction.SELL
    elif value < -0.15:
        return Direction.SELL
    return Direction.HOLD
