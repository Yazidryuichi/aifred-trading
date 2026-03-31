"""Main execution engine: coordinates order routing, execution, and safety."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.utils.types import (
    AssetClass, Direction, OrderType, Position, PortfolioState,
    RiskDecision, TradeProposal, TradeResult, TradeStatus,
)
from src.execution.credential_validator import CredentialValidator, ValidationReport
from src.execution.exchange_connector import ExchangeConnector
from src.execution.order_manager import OrderManager, ManagedOrder
from src.execution.order_state_machine import (
    OrderRole, OrderState as SMOrderState, OrderStateMachineRegistry,
    StateMachineOrder,
)
from src.execution.paper_trader import PaperTrader
from src.execution.reconciler import PositionReconciler, ReconciliationResult
from src.execution.safety_checks import SafetyChecks
from src.execution.smart_router import SmartRouter
from src.risk.account_safety import AccountSafety
from src.risk.dynamic_kelly import DynamicKelly, TradeRecord

logger = logging.getLogger(__name__)


class ExecutionAgent:
    """Main execution interface that coordinates all execution subsystems."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        exec_config = config.get("execution", {})
        self._paper_mode = exec_config.get("mode", "paper") == "paper"
        self._dry_run = exec_config.get("dry_run", False)
        if self._dry_run:
            logger.warning("DRY RUN: Trade execution will be simulated (no orders submitted)")

        # Initialize subsystems
        self.order_manager = OrderManager(
            max_retries=exec_config.get("max_consecutive_failures", 3)
        )
        self.safety = SafetyChecks(config)

        # Hard account-level safety limits (non-overridable)
        self._safety_limits = AccountSafety(config)

        # Exchange connectors
        self._connectors: Dict[str, ExchangeConnector] = {}
        self._paper_trader: Optional[PaperTrader] = None
        self._router: Optional[SmartRouter] = None

        if self._paper_mode:
            self._paper_trader = PaperTrader(
                slippage_pct=exec_config.get("slippage_tolerance_pct", 0.1) / 2,
            )
            logger.info("Execution engine initialized in PAPER mode")
        else:
            self._init_connectors(config)
            logger.info("Execution engine initialized in LIVE mode")

        # Position reconciler for crash recovery and exchange sync
        self._reconciler = PositionReconciler(config)

        # Order state machine registry
        self._sm_registry = OrderStateMachineRegistry()

        # Dynamic Kelly calibration from rolling trade history
        self._dynamic_kelly = DynamicKelly(config)

        # Pending stop-loss/take-profit orders for paper mode
        # Maps asset -> list of {side, price, amount, type}
        self._pending_exit_orders: Dict[str, List[Dict[str, Any]]] = {}

        # Portfolio state (tracked internally)
        self._positions: Dict[str, Position] = {}

    def _init_connectors(self, config: Dict[str, Any]) -> None:
        """Initialize exchange connectors from config."""
        exchanges = config.get("exchanges", {})
        for asset_class_name, exchange_list in exchanges.items():
            for exch in exchange_list:
                name = exch.get("name", "")
                connector = ExchangeConnector(
                    name=name,
                    api_key=exch.get("api_key", ""),
                    secret=exch.get("secret", ""),
                    sandbox=False,
                    extra_params={k: v for k, v in exch.items()
                                  if k not in ("name", "api_key", "secret")},
                )
                connector.connect()
                self._connectors[name] = connector

        if self._connectors:
            self._router = SmartRouter(self._connectors)

    def is_paper_mode(self) -> bool:
        return self._paper_mode

    def reconcile_positions(self, on_startup: bool = False) -> ReconciliationResult:
        """Reconcile local positions with exchange / persisted state.

        Args:
            on_startup: If True, performs full startup reconciliation
                        (loads from SQLite, fetches from exchange).
                        If False, performs lighter periodic reconciliation.
        """
        if on_startup:
            result = self._reconciler.reconcile_on_startup(
                self._positions, self._connectors, self._paper_mode,
            )
        else:
            result = self._reconciler.reconcile_periodic(
                self._positions, self._connectors, self._paper_mode,
            )

        # Sync restored positions into paper trader if in paper mode
        if on_startup and self._paper_mode and self._paper_trader:
            for asset, pos in self._positions.items():
                if asset not in self._paper_trader._positions:
                    self._paper_trader.open_position(
                        asset=pos.asset, asset_class=pos.asset_class,
                        side=pos.side, entry_price=pos.entry_price,
                        size=pos.size, stop_loss=pos.stop_loss,
                        take_profit=pos.take_profit, order_id=pos.order_id,
                    )

        return result

    def persist_positions(self) -> None:
        """Persist current position state to SQLite for crash recovery."""
        self._reconciler.persist_state(self._positions)

    def execute(self, proposal: TradeProposal,
                risk_decision: RiskDecision) -> TradeResult:
        """Execute a trade proposal that has been approved by the risk gate.

        This is the main entry point for trade execution.
        """
        portfolio = self._get_portfolio_state()

        # HARD account-level safety limits (non-overridable, checked FIRST)
        allowed, safety_reason = self._safety_limits.check_trade_allowed(
            position_value_usd=proposal.position_value,
            account_equity=portfolio.total_value,
            current_positions=len(self._positions),
            total_exposure_usd=sum(
                p.current_price * p.size for p in self._positions.values()
            ),
        )
        if not allowed:
            logger.warning(
                "SAFETY BLOCK: %s for %s", safety_reason, proposal.asset,
            )
            return TradeResult(
                proposal=proposal,
                status=TradeStatus.REJECTED,
                error=f"safety_limit: {safety_reason}",
            )

        # Pre-execution safety checks
        passed, reason = self.safety.pre_execution_check(
            proposal, risk_decision, portfolio,
            self._paper_trader if self._paper_mode else None,
        )
        if not passed:
            logger.info("Trade rejected by safety checks: %s", reason)
            return TradeResult(
                proposal=proposal,
                status=TradeStatus.REJECTED,
                error=reason,
            )

        # Apply risk adjustments
        size = risk_decision.adjusted_size or proposal.position_size
        stop = risk_decision.adjusted_stop or proposal.stop_loss

        # Determine side
        side = "buy" if proposal.direction in (Direction.BUY, Direction.STRONG_BUY) else "sell"

        # Dry-run: log what WOULD be traded, but don't submit
        if self._dry_run:
            logger.info(
                "DRY RUN TRADE: %s %s %.6f @ ~$%.2f (confidence: %.1f%%, stop: $%.2f)",
                side.upper(), proposal.asset, size,
                proposal.entry_price, proposal.confidence, stop,
            )
            return TradeResult(
                proposal=proposal,
                status=TradeStatus.REJECTED,
                error="dry_run: order not submitted",
            )

        # Execute
        if self._paper_mode:
            result = self._execute_paper(proposal, side, size, stop)
        else:
            result = self._execute_live(proposal, side, size, stop)

        # Post-execution checks
        post_ok, post_reason = self.safety.post_execution_check(result, proposal)
        if not post_ok and result.status not in (TradeStatus.FILLED, TradeStatus.PARTIAL):
            logger.warning("Post-execution check flagged: %s", post_reason)

        # Place stop-loss if needed
        if result.status == TradeStatus.FILLED and self.safety.should_place_stop_loss(proposal):
            self._place_stop_loss(proposal, stop, size, side)

        # Track position
        if result.status == TradeStatus.FILLED:
            self._track_position(proposal, result, side, stop)

        return result

    def _execute_paper(self, proposal: TradeProposal, side: str,
                       size: float, stop: float) -> TradeResult:
        """Execute via paper trader."""
        assert self._paper_trader is not None
        self._paper_trader.set_price(proposal.asset, proposal.entry_price)

        order_type = proposal.order_type.value
        order = self._paper_trader.place_order(
            symbol=proposal.asset,
            side=side,
            order_type=order_type,
            amount=size,
            price=proposal.entry_price,
        )

        if order.get("status") == "rejected":
            return TradeResult(
                proposal=proposal,
                status=TradeStatus.FAILED,
                error=order.get("info", "paper_trade_rejected"),
            )

        fill_price = float(order.get("average", proposal.entry_price))
        slippage = abs(fill_price - proposal.entry_price) / proposal.entry_price * 100 if proposal.entry_price > 0 else 0
        fee_info = order.get("fee", {})

        return TradeResult(
            proposal=proposal,
            status=TradeStatus.FILLED,
            fill_price=fill_price,
            fill_size=size,
            slippage=slippage,
            fees=float(fee_info.get("cost", 0)),
            exchange="paper",
            order_id=order.get("id", ""),
        )

    def _execute_live(self, proposal: TradeProposal, side: str,
                      size: float, stop: float) -> TradeResult:
        """Execute on a real exchange via smart routing."""
        # Route to best exchange
        exchange_name = None
        if self._router:
            exchange_name = self._router.route_order(proposal.asset, side, size)

        if exchange_name is None:
            # Fall back to first available connector
            if not self._connectors:
                return TradeResult(
                    proposal=proposal, status=TradeStatus.FAILED,
                    error="no_exchange_available",
                )
            exchange_name = next(iter(self._connectors))

        connector = self._connectors[exchange_name]
        order_type = self._map_order_type(proposal.order_type)

        # Create and submit managed order
        managed = self.order_manager.create_order(
            symbol=proposal.asset, side=side,
            order_type=proposal.order_type,
            amount=size, price=proposal.entry_price,
        )

        try:
            result = self.order_manager.submit_order(managed, connector)
        except Exception as e:
            return TradeResult(
                proposal=proposal, status=TradeStatus.FAILED,
                error=str(e), exchange=exchange_name,
            )

        # Update status from exchange
        self.order_manager.update_order_status(managed, connector)

        # Record fill rate for smart router
        if self._router and managed.filled_amount > 0:
            self._router.record_fill(exchange_name, size, managed.filled_amount)

        status = TradeStatus.FILLED if managed.state.value == "filled" else TradeStatus.PARTIAL
        if managed.state.value in ("failed", "cancelled"):
            status = TradeStatus.FAILED

        slippage = 0.0
        if proposal.entry_price > 0 and managed.average_fill_price > 0:
            slippage = abs(managed.average_fill_price - proposal.entry_price) / proposal.entry_price * 100

        return TradeResult(
            proposal=proposal,
            status=status,
            fill_price=managed.average_fill_price,
            fill_size=managed.filled_amount,
            slippage=slippage,
            fees=managed.fees,
            exchange=exchange_name,
            order_id=managed.exchange_order_id or managed.id,
        )

    def _place_stop_loss(self, proposal: TradeProposal, stop: float,
                         size: float, entry_side: str) -> None:
        """Place a stop-loss order immediately after fill.

        In paper mode, the stop is tracked internally so the PositionMonitor
        can detect when it's hit. In live mode, it's placed on the exchange.
        """
        sl_side = "sell" if entry_side == "buy" else "buy"

        # Register in the state machine regardless of mode
        sm_order = StateMachineOrder(
            symbol=proposal.asset,
            side=sl_side,
            order_type="stop_loss",
            amount=size,
            price=stop,
            role=OrderRole.STOP_LOSS,
        )
        self._sm_registry.register(sm_order)

        if self._paper_mode:
            sm_order.submit(exchange_order_id=f"paper_sl_{sm_order.id}")
            logger.info(
                "[PAPER] Stop-loss tracked for %s at %.4f (order=%s)",
                proposal.asset, stop, sm_order.id,
            )
            return

        # Live mode: place on the exchange
        for name, connector in self._connectors.items():
            try:
                result = connector.place_order(
                    symbol=proposal.asset, side=sl_side,
                    order_type="stop", amount=size, price=stop,
                    params={"stopPrice": stop},
                )
                exchange_id = result.get("id", "")
                sm_order.submit(exchange_order_id=exchange_id)
                logger.info("Stop-loss placed for %s at %.4f on %s (order=%s)",
                            proposal.asset, stop, name, sm_order.id)
                return
            except Exception as e:
                logger.error("Failed to place stop-loss on %s: %s", name, e)

        sm_order.fail("failed_to_place_on_all_exchanges")

    def _place_take_profit(self, proposal: TradeProposal, take_profit: float,
                           size: float, entry_side: str) -> None:
        """Place a take-profit order after fill.

        In paper mode, tracked internally for the PositionMonitor.
        In live mode, placed on the exchange.
        """
        if take_profit <= 0:
            return

        tp_side = "sell" if entry_side == "buy" else "buy"

        sm_order = StateMachineOrder(
            symbol=proposal.asset,
            side=tp_side,
            order_type="take_profit",
            amount=size,
            price=take_profit,
            role=OrderRole.TAKE_PROFIT,
        )
        self._sm_registry.register(sm_order)

        if self._paper_mode:
            sm_order.submit(exchange_order_id=f"paper_tp_{sm_order.id}")
            logger.info(
                "[PAPER] Take-profit tracked for %s at %.4f (order=%s)",
                proposal.asset, take_profit, sm_order.id,
            )
            return

        for name, connector in self._connectors.items():
            try:
                result = connector.place_order(
                    symbol=proposal.asset, side=tp_side,
                    order_type="limit", amount=size, price=take_profit,
                )
                exchange_id = result.get("id", "")
                sm_order.submit(exchange_order_id=exchange_id)
                logger.info("Take-profit placed for %s at %.4f on %s (order=%s)",
                            proposal.asset, take_profit, name, sm_order.id)
                return
            except Exception as e:
                logger.error("Failed to place take-profit on %s: %s", name, e)

        sm_order.fail("failed_to_place_on_all_exchanges")

    def _track_position(self, proposal: TradeProposal, result: TradeResult,
                        side: str, stop: float) -> None:
        """Track a new open position and chain SL/TP exit orders."""
        pos = Position(
            asset=proposal.asset,
            asset_class=proposal.asset_class,
            side="LONG" if side == "buy" else "SHORT",
            entry_price=result.fill_price,
            current_price=result.fill_price,
            size=result.fill_size,
            stop_loss=stop,
            take_profit=proposal.take_profit,
            order_id=result.order_id,
            strategy=proposal.signal.source if proposal.signal else "",
        )
        self._positions[proposal.asset] = pos
        if self._paper_mode and self._paper_trader:
            self._paper_trader.open_position(
                asset=proposal.asset, asset_class=proposal.asset_class,
                side=pos.side, entry_price=result.fill_price,
                size=result.fill_size, stop_loss=stop,
                take_profit=proposal.take_profit, order_id=result.order_id,
            )

        # Persist to SQLite for crash recovery
        self.persist_positions()

        # Chain take-profit order (stop-loss was already placed in execute())
        self._place_take_profit(proposal, proposal.take_profit, result.fill_size, side)

    def close_position(self, position: Position, reason: str = "") -> TradeResult:
        """Close an open position."""
        side = "sell" if position.side == "LONG" else "buy"

        if self._paper_mode:
            assert self._paper_trader is not None
            self._paper_trader.set_price(position.asset, position.current_price)
            order = self._paper_trader.place_order(
                symbol=position.asset, side=side,
                order_type="market", amount=position.size,
            )
            pnl = self._paper_trader.close_position(position.asset, position.current_price)
            self._positions.pop(position.asset, None)
            self._reconciler.store.remove_position(position.asset)
            fill_price = float(order.get("average", position.current_price))

            # Record realized P&L in hard safety limits
            _pnl_val = pnl if pnl is not None else position.unrealized_pnl
            self._safety_limits.record_trade_pnl(_pnl_val)

            # Record trade for dynamic Kelly calibration
            _pnl_pct = (_pnl_val / (position.entry_price * position.size) * 100
                        if position.entry_price * position.size > 0 else 0.0)
            self._dynamic_kelly.record_trade(TradeRecord(
                asset=position.asset, side=position.side,
                entry_price=position.entry_price, exit_price=position.current_price,
                size=position.size, pnl=_pnl_val, pnl_pct=_pnl_pct,
                strategy=position.strategy,
            ))

            # Build a minimal proposal for the result
            from src.utils.types import Signal
            dummy_signal = Signal(
                asset=position.asset,
                direction=Direction.SELL if position.side == "LONG" else Direction.BUY,
                confidence=100.0, source="close:" + reason,
            )
            dummy_proposal = TradeProposal(
                signal=dummy_signal, asset=position.asset,
                asset_class=position.asset_class,
                direction=dummy_signal.direction,
                entry_price=position.current_price,
                position_size=position.size,
                position_value=position.size * position.current_price,
                stop_loss=0, take_profit=0,
            )
            return TradeResult(
                proposal=dummy_proposal, status=TradeStatus.FILLED,
                fill_price=fill_price, fill_size=position.size,
                exchange="paper", order_id=order.get("id", ""),
            )
        else:
            # Live close
            for name, connector in self._connectors.items():
                try:
                    result = connector.place_order(
                        symbol=position.asset, side=side,
                        order_type="market", amount=position.size,
                    )
                    self._positions.pop(position.asset, None)
                    self._reconciler.store.remove_position(position.asset)
                    from src.utils.types import Signal
                    dummy_signal = Signal(
                        asset=position.asset,
                        direction=Direction.SELL if position.side == "LONG" else Direction.BUY,
                        confidence=100.0, source="close:" + reason,
                    )
                    dummy_proposal = TradeProposal(
                        signal=dummy_signal, asset=position.asset,
                        asset_class=position.asset_class,
                        direction=dummy_signal.direction,
                        entry_price=position.current_price,
                        position_size=position.size,
                        position_value=position.size * position.current_price,
                        stop_loss=0, take_profit=0,
                    )
                    fill_price = float(result.get("average", position.current_price) or position.current_price)

                    # Record realized P&L in hard safety limits
                    _live_pnl = position.unrealized_pnl
                    self._safety_limits.record_trade_pnl(_live_pnl)

                    # Record for dynamic Kelly calibration
                    _live_pnl_pct = (_live_pnl / (position.entry_price * position.size) * 100
                                     if position.entry_price * position.size > 0 else 0.0)
                    self._dynamic_kelly.record_trade(TradeRecord(
                        asset=position.asset, side=position.side,
                        entry_price=position.entry_price, exit_price=fill_price,
                        size=position.size, pnl=_live_pnl, pnl_pct=_live_pnl_pct,
                        strategy=position.strategy,
                    ))

                    return TradeResult(
                        proposal=dummy_proposal, status=TradeStatus.FILLED,
                        fill_price=fill_price, fill_size=position.size,
                        exchange=name, order_id=result.get("id", ""),
                    )
                except Exception as e:
                    logger.error("Failed to close position on %s: %s", name, e)

            from src.utils.types import Signal
            dummy_signal = Signal(
                asset=position.asset, direction=Direction.HOLD,
                confidence=0, source="close_failed",
            )
            dummy_proposal = TradeProposal(
                signal=dummy_signal, asset=position.asset,
                asset_class=position.asset_class, direction=Direction.HOLD,
                entry_price=0, position_size=0, position_value=0,
                stop_loss=0, take_profit=0,
            )
            return TradeResult(
                proposal=dummy_proposal, status=TradeStatus.FAILED,
                error="failed_to_close_on_all_exchanges",
            )

    def update_position_price(self, asset: str, price: float) -> None:
        """Update the current price and unrealized PnL for a tracked position.

        Called by the PositionMonitor on each check cycle.
        """
        pos = self._positions.get(asset)
        if pos is None:
            return
        pos.current_price = price
        if pos.side == "LONG":
            pos.unrealized_pnl = (price - pos.entry_price) * pos.size
        else:
            pos.unrealized_pnl = (pos.entry_price - price) * pos.size

    def get_position(self, asset: str) -> Optional[Position]:
        """Get a single open position by asset symbol."""
        return self._positions.get(asset)

    def modify_stop(self, position: Position, new_stop: float) -> bool:
        """Modify the stop-loss for an open position."""
        if position.asset not in self._positions:
            logger.warning("Position %s not found", position.asset)
            return False
        self._positions[position.asset].stop_loss = new_stop
        logger.info("Stop-loss for %s updated to %.4f", position.asset, new_stop)
        return True

    def get_open_orders(self) -> List[ManagedOrder]:
        return self.order_manager.get_open_orders()

    def get_open_positions(self) -> List[Position]:
        return list(self._positions.values())

    def _get_portfolio_state(self) -> PortfolioState:
        """Build current portfolio state."""
        positions = list(self._positions.values())
        if self._paper_mode and self._paper_trader:
            total_value = self._paper_trader.get_total_value()
            balances = self._paper_trader.get_balance()
            cash = balances.get("free", {}).get("USD", 0) + balances.get("free", {}).get("USDT", 0)
        else:
            total_value = sum(p.current_price * p.size for p in positions)
            cash = 0.0
            for connector in self._connectors.values():
                try:
                    bal = connector.get_balance()
                    cash += float(bal.get("free", {}).get("USD", 0) or 0)
                    cash += float(bal.get("free", {}).get("USDT", 0) or 0)
                except Exception:
                    pass
            total_value += cash

        return PortfolioState(
            total_value=total_value,
            cash=cash,
            positions=positions,
        )

    def validate_ready(self) -> ValidationReport:
        """Validate that the execution engine is ready to trade.

        In paper mode, always returns a passing report.
        In live mode, runs full credential/connectivity/balance validation.
        """
        validator = CredentialValidator(self.config)
        report = validator.validate()

        for result in report.results:
            log_fn = logger.info if result.passed else logger.error
            log_fn("ExecutionAgent validation: %s — %s", result.check, result.message)

        return report

    def get_account_balance(self) -> Dict[str, float]:
        """Return actual account balance from exchanges (for position sizing).

        Returns:
            Dict with keys like 'total_usd', 'free_usd', and per-exchange breakdowns.
        """
        result: Dict[str, float] = {"total_usd": 0.0, "free_usd": 0.0}

        if self._paper_mode and self._paper_trader:
            balances = self._paper_trader.get_balance()
            free = balances.get("free", {})
            free_usd = float(free.get("USD", 0) or 0) + float(free.get("USDT", 0) or 0)
            total = self._paper_trader.get_total_value()
            result["total_usd"] = total
            result["free_usd"] = free_usd
            result["paper"] = total
            return result

        for name, connector in self._connectors.items():
            try:
                bal = connector.get_balance()
                free = bal.get("free", {})
                exchange_free = 0.0
                for currency in ("USD", "USDT", "USDC", "BUSD"):
                    val = free.get(currency, 0)
                    if val:
                        exchange_free += float(val)
                result[f"{name}_free_usd"] = exchange_free
                result["free_usd"] += exchange_free
                result["total_usd"] += exchange_free
            except Exception as e:
                logger.warning("Failed to fetch balance from %s: %s", name, e)
                result[f"{name}_free_usd"] = 0.0

        return result

    def get_dynamic_kelly_status(self) -> Dict[str, Any]:
        """Return current dynamic Kelly calibration status."""
        return self._dynamic_kelly.status

    @staticmethod
    def _map_order_type(order_type: OrderType) -> str:
        return {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
            OrderType.STOP_LIMIT: "stop",
            OrderType.TRAILING_STOP: "trailing_stop",
        }.get(order_type, "limit")
