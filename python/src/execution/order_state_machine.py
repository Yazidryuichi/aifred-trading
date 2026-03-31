"""Order state machine with enforced transitions and full lifecycle tracking."""

import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class OrderState(Enum):
    PENDING_CREATE = "pending_create"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    PENDING_CANCEL = "pending_cancel"
    CANCELLED = "cancelled"
    FAILED = "failed"
    EXPIRED = "expired"


class OrderRole(Enum):
    """Role of an order within a position lifecycle."""
    ENTRY = "entry"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    EXIT = "exit"


class InvalidTransition(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, order_id: str, from_state: OrderState, to_state: OrderState):
        self.order_id = order_id
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid transition for order {order_id}: "
            f"{from_state.value} -> {to_state.value}"
        )


# Valid state transitions: from_state -> set of allowed to_states
VALID_TRANSITIONS: Dict[OrderState, set] = {
    OrderState.PENDING_CREATE: {OrderState.OPEN, OrderState.FAILED},
    OrderState.OPEN: {
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.PENDING_CANCEL,
        OrderState.EXPIRED,
        OrderState.FAILED,
    },
    OrderState.PARTIALLY_FILLED: {
        OrderState.FILLED,
        OrderState.PENDING_CANCEL,
        OrderState.FAILED,
    },
    OrderState.PENDING_CANCEL: {
        OrderState.CANCELLED,
        OrderState.FILLED,  # filled before cancel was processed
    },
    # Terminal states -- no transitions out
    OrderState.FILLED: set(),
    OrderState.CANCELLED: set(),
    OrderState.FAILED: set(),
    OrderState.EXPIRED: set(),
}


class StateMachineOrder:
    """An order tracked through its full lifecycle with enforced state transitions.

    This replaces the simple OrderState enum from order_manager.py with a
    proper state machine that validates every transition.
    """

    def __init__(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float = 0.0,
        role: OrderRole = OrderRole.ENTRY,
        parent_order_id: Optional[str] = None,
    ):
        self.id: str = str(uuid.uuid4())[:12]
        self.symbol: str = symbol
        self.side: str = side  # "buy" or "sell"
        self.order_type: str = order_type
        self.amount: float = amount
        self.price: float = price
        self.role: OrderRole = role
        self.state: OrderState = OrderState.PENDING_CREATE

        # Exchange linkage
        self.exchange_order_id: Optional[str] = None

        # Parent/child order linkage (for SL/TP chained to entry)
        self.parent_order_id: Optional[str] = parent_order_id
        self.children: List[str] = []  # child order IDs

        # Timing
        self.created_at: datetime = datetime.utcnow()
        self.updated_at: datetime = datetime.utcnow()

        # Fill tracking
        self.filled_amount: float = 0.0
        self.average_fill_price: float = 0.0
        self.fees: float = 0.0

        # Error info
        self.error: Optional[str] = None

        # Transition history for audit
        self._history: List[Dict[str, Any]] = [
            {
                "from": None,
                "to": OrderState.PENDING_CREATE.value,
                "timestamp": self.created_at.isoformat(),
                "detail": "order_created",
            }
        ]

    def _transition(self, new_state: OrderState, detail: str = "") -> None:
        """Validate and perform a state transition."""
        allowed = VALID_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise InvalidTransition(self.id, self.state, new_state)

        old_state = self.state
        self.state = new_state
        self.updated_at = datetime.utcnow()
        self._history.append({
            "from": old_state.value,
            "to": new_state.value,
            "timestamp": self.updated_at.isoformat(),
            "detail": detail,
        })
        logger.info(
            "Order %s (%s %s %s): %s -> %s%s",
            self.id, self.side, self.symbol, self.role.value,
            old_state.value, new_state.value,
            f" ({detail})" if detail else "",
        )

    # -- Public transition methods --

    def submit(self, exchange_order_id: Optional[str] = None) -> None:
        """Transition PENDING_CREATE -> OPEN (submitted to exchange)."""
        self._transition(OrderState.OPEN, "submitted_to_exchange")
        if exchange_order_id:
            self.exchange_order_id = exchange_order_id

    def partial_fill(self, amount: float, price: float) -> None:
        """Transition OPEN -> PARTIALLY_FILLED."""
        self._transition(OrderState.PARTIALLY_FILLED, f"partial_fill: {amount}@{price}")
        self._update_fill(amount, price)

    def fill(self, amount: float, price: float) -> None:
        """Transition OPEN/PARTIALLY_FILLED/PENDING_CANCEL -> FILLED."""
        self._transition(OrderState.FILLED, f"filled: {amount}@{price}")
        self._update_fill(amount, price)

    def request_cancel(self) -> None:
        """Transition OPEN/PARTIALLY_FILLED -> PENDING_CANCEL."""
        self._transition(OrderState.PENDING_CANCEL, "cancel_requested")

    def cancel(self) -> None:
        """Transition PENDING_CANCEL -> CANCELLED."""
        self._transition(OrderState.CANCELLED, "cancelled")

    def fail(self, error: str = "") -> None:
        """Transition any non-terminal state -> FAILED."""
        self.error = error
        self._transition(OrderState.FAILED, f"failed: {error}")

    def expire(self) -> None:
        """Transition OPEN -> EXPIRED."""
        self._transition(OrderState.EXPIRED, "ttl_exceeded")

    # -- Fill helpers --

    def _update_fill(self, amount: float, price: float) -> None:
        """Update running fill average and total."""
        if amount <= 0:
            return
        total_cost = self.average_fill_price * self.filled_amount + price * amount
        self.filled_amount += amount
        if self.filled_amount > 0:
            self.average_fill_price = total_cost / self.filled_amount

    # -- Query helpers --

    @property
    def is_terminal(self) -> bool:
        return self.state in (
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.FAILED,
            OrderState.EXPIRED,
        )

    @property
    def is_active(self) -> bool:
        return self.state in (
            OrderState.PENDING_CREATE,
            OrderState.OPEN,
            OrderState.PARTIALLY_FILLED,
            OrderState.PENDING_CANCEL,
        )

    @property
    def remaining_amount(self) -> float:
        return max(0.0, self.amount - self.filled_amount)

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "role": self.role.value,
            "amount": self.amount,
            "price": self.price,
            "state": self.state.value,
            "exchange_order_id": self.exchange_order_id,
            "parent_order_id": self.parent_order_id,
            "children": self.children,
            "filled_amount": self.filled_amount,
            "average_fill_price": self.average_fill_price,
            "fees": self.fees,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "history": self._history,
        }

    def __repr__(self) -> str:
        return (
            f"<StateMachineOrder {self.id} {self.side} {self.symbol} "
            f"{self.role.value} state={self.state.value} "
            f"filled={self.filled_amount}/{self.amount}>"
        )


class OrderStateMachineRegistry:
    """Registry of all orders managed by the state machine.

    Provides lookup by internal ID, exchange ID, and parent linkage.
    """

    def __init__(self):
        self._orders: Dict[str, StateMachineOrder] = {}
        self._exchange_id_map: Dict[str, str] = {}  # exchange_order_id -> internal id

    def register(self, order: StateMachineOrder) -> None:
        """Register a new order and link to parent if applicable."""
        self._orders[order.id] = order
        if order.exchange_order_id:
            self._exchange_id_map[order.exchange_order_id] = order.id
        # Auto-link child to parent's children list
        if order.parent_order_id:
            parent = self._orders.get(order.parent_order_id)
            if parent is not None and order.id not in parent.children:
                parent.children.append(order.id)

    def get(self, order_id: str) -> Optional[StateMachineOrder]:
        return self._orders.get(order_id)

    def get_by_exchange_id(self, exchange_order_id: str) -> Optional[StateMachineOrder]:
        internal_id = self._exchange_id_map.get(exchange_order_id)
        if internal_id:
            return self._orders.get(internal_id)
        return None

    def get_children(self, parent_order_id: str) -> List[StateMachineOrder]:
        """Get all child orders (SL/TP) linked to a parent entry order."""
        parent = self._orders.get(parent_order_id)
        if parent is None:
            return []
        return [self._orders[cid] for cid in parent.children if cid in self._orders]

    def get_active_orders(self) -> List[StateMachineOrder]:
        return [o for o in self._orders.values() if o.is_active]

    def get_orders_for_symbol(self, symbol: str) -> List[StateMachineOrder]:
        return [o for o in self._orders.values() if o.symbol == symbol]

    def link_exchange_id(self, order_id: str, exchange_order_id: str) -> None:
        """Link an exchange order ID after submission."""
        order = self._orders.get(order_id)
        if order:
            order.exchange_order_id = exchange_order_id
            self._exchange_id_map[exchange_order_id] = order_id

    def link_child(self, parent_id: str, child_id: str) -> None:
        """Link a child order (SL/TP) to a parent entry order."""
        parent = self._orders.get(parent_id)
        child = self._orders.get(child_id)
        if parent and child:
            parent.children.append(child_id)
            child.parent_order_id = parent_id

    def all_orders(self) -> List[StateMachineOrder]:
        return list(self._orders.values())
