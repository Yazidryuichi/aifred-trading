"""Position reconciliation: ensures local state matches exchange reality.

Called on startup and periodically (every 5 minutes) to:
1. Fetch actual positions/balances from exchange
2. Compare with local tracking state
3. Resolve discrepancies (orphaned orders, missing positions, stale data)
4. Persist state to SQLite for crash recovery
"""

import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.utils.types import AssetClass, Position

logger = logging.getLogger(__name__)

# Stablecoins and fiat to exclude when inferring spot positions from balances
_QUOTE_CURRENCIES = frozenset({
    "USD", "USDT", "USDC", "BUSD", "DAI", "TUSD", "UST", "EUR", "GBP", "JPY",
})

# Minimum balance (in base units) to consider a non-zero spot holding a position
_MIN_DUST_THRESHOLD = 1e-8


@dataclass
class ReconciliationResult:
    """Result of a reconciliation cycle."""

    timestamp: datetime = field(default_factory=datetime.utcnow)
    positions_local: int = 0       # positions tracked locally
    positions_exchange: int = 0    # positions on exchange
    matched: int = 0               # positions that match
    orphaned_on_exchange: List[str] = field(default_factory=list)  # on exchange but not local
    missing_from_exchange: List[str] = field(default_factory=list)  # local but not on exchange
    size_mismatches: List[str] = field(default_factory=list)        # same asset, different size
    actions_taken: List[str] = field(default_factory=list)          # what was done to resolve


class PositionStore:
    """SQLite-backed position persistence for crash recovery.

    Saves position state to disk so it survives process restarts.
    Uses WAL mode for safe concurrent writes.
    """

    def __init__(self, db_path: str = "data/positions.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Create a new connection with WAL mode for concurrency safety."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create positions table if not exists."""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        try:
            conn = self._get_conn()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    asset TEXT PRIMARY KEY,
                    asset_class TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    current_price REAL NOT NULL,
                    size REAL NOT NULL,
                    stop_loss REAL NOT NULL DEFAULT 0,
                    take_profit REAL NOT NULL DEFAULT 0,
                    unrealized_pnl REAL NOT NULL DEFAULT 0,
                    realized_pnl REAL NOT NULL DEFAULT 0,
                    entry_time TEXT NOT NULL,
                    order_id TEXT NOT NULL DEFAULT '',
                    strategy TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Failed to initialize position store DB: %s", e)

    def save_positions(self, positions: List[Position]) -> None:
        """Upsert all positions to DB."""
        if not positions:
            return
        now = datetime.utcnow().isoformat()
        try:
            conn = self._get_conn()
            for pos in positions:
                conn.execute(
                    """INSERT OR REPLACE INTO positions
                       (asset, asset_class, side, entry_price, current_price,
                        size, stop_loss, take_profit, unrealized_pnl, realized_pnl,
                        entry_time, order_id, strategy, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        pos.asset,
                        pos.asset_class.value if isinstance(pos.asset_class, AssetClass) else str(pos.asset_class),
                        pos.side,
                        pos.entry_price,
                        pos.current_price,
                        pos.size,
                        pos.stop_loss,
                        pos.take_profit,
                        pos.unrealized_pnl,
                        pos.realized_pnl,
                        pos.entry_time.isoformat() if isinstance(pos.entry_time, datetime) else str(pos.entry_time),
                        pos.order_id,
                        pos.strategy,
                        now,
                    ),
                )
            conn.commit()
            conn.close()
            logger.debug("Persisted %d positions to %s", len(positions), self.db_path)
        except Exception as e:
            logger.error("Failed to save positions: %s", e)

    def load_positions(self) -> List[Position]:
        """Load all positions from DB."""
        positions: List[Position] = []
        try:
            conn = self._get_conn()
            rows = conn.execute("SELECT * FROM positions").fetchall()
            for row in rows:
                try:
                    asset_class = AssetClass(row["asset_class"])
                except ValueError:
                    asset_class = AssetClass.CRYPTO

                try:
                    entry_time = datetime.fromisoformat(row["entry_time"])
                except (ValueError, TypeError):
                    entry_time = datetime.utcnow()

                pos = Position(
                    asset=row["asset"],
                    asset_class=asset_class,
                    side=row["side"],
                    entry_price=row["entry_price"],
                    current_price=row["current_price"],
                    size=row["size"],
                    stop_loss=row["stop_loss"],
                    take_profit=row["take_profit"],
                    unrealized_pnl=row["unrealized_pnl"],
                    realized_pnl=row["realized_pnl"],
                    entry_time=entry_time,
                    order_id=row["order_id"],
                    strategy=row["strategy"],
                )
                positions.append(pos)
            conn.close()
            logger.info("Loaded %d positions from %s", len(positions), self.db_path)
        except Exception as e:
            logger.error("Failed to load positions: %s", e)
        return positions

    def remove_position(self, asset: str) -> None:
        """Remove a closed position."""
        try:
            conn = self._get_conn()
            conn.execute("DELETE FROM positions WHERE asset = ?", (asset,))
            conn.commit()
            conn.close()
            logger.debug("Removed position for %s from store", asset)
        except Exception as e:
            logger.error("Failed to remove position %s: %s", asset, e)

    def clear_all(self) -> None:
        """Clear all positions (for testing)."""
        try:
            conn = self._get_conn()
            conn.execute("DELETE FROM positions")
            conn.commit()
            conn.close()
            logger.info("Cleared all positions from store")
        except Exception as e:
            logger.error("Failed to clear positions: %s", e)


class PositionReconciler:
    """Reconciles local position state with exchange reality."""

    def __init__(self, config: Dict[str, Any]):
        self._config = config
        recon_config = config.get("reconciliation", {})
        db_path = recon_config.get("db_path",
                                   config.get("system", {}).get("db_path", "data/positions.db"))
        self._store = PositionStore(db_path)
        self._reconcile_interval = recon_config.get("interval_seconds", 300)
        self._trust_exchange = recon_config.get("trust_exchange", True)

    @property
    def store(self) -> PositionStore:
        """Expose the underlying PositionStore for direct access."""
        return self._store

    def reconcile_on_startup(
        self,
        local_positions: Dict[str, Position],
        exchange_connectors: Dict[str, Any],
        paper_mode: bool,
    ) -> ReconciliationResult:
        """Full reconciliation on startup.

        1. Load persisted positions from SQLite
        2. If live mode: fetch positions from exchange and compare
        3. If paper mode: restore from SQLite only
        4. Resolve discrepancies
        """
        result = ReconciliationResult()

        # Step 1: load persisted positions
        persisted = self._store.load_positions()
        persisted_map: Dict[str, Position] = {p.asset: p for p in persisted}

        if paper_mode:
            # In paper mode, SQLite is the source of truth
            # Merge persisted positions into local (local is empty on fresh start)
            restored_count = 0
            for asset, pos in persisted_map.items():
                if asset not in local_positions:
                    local_positions[asset] = pos
                    restored_count += 1
                    result.actions_taken.append(f"restored {asset} from SQLite")

            result.positions_local = len(local_positions)
            result.positions_exchange = 0
            result.matched = len(local_positions)

            if restored_count > 0:
                logger.info(
                    "Startup reconciliation (paper): restored %d positions from SQLite",
                    restored_count,
                )
            else:
                logger.info("Startup reconciliation (paper): no positions to restore")

            return result

        # Step 2: live mode -- fetch exchange state
        exchange_positions = self._fetch_exchange_positions(exchange_connectors)

        # Merge persisted positions that aren't already tracked locally
        for asset, pos in persisted_map.items():
            if asset not in local_positions:
                local_positions[asset] = pos

        # Step 3: compare and resolve
        result = self._compare_positions(local_positions, exchange_positions)
        result.actions_taken.append("startup_full_reconciliation")

        if self._trust_exchange:
            resolved = self._resolve_discrepancies(result, local_positions, exchange_positions)
            local_positions.clear()
            local_positions.update(resolved)

        # Persist the reconciled state
        self._store.save_positions(list(local_positions.values()))

        logger.info(
            "Startup reconciliation (live): local=%d exchange=%d matched=%d "
            "orphaned=%d missing=%d size_mismatch=%d",
            result.positions_local, result.positions_exchange, result.matched,
            len(result.orphaned_on_exchange), len(result.missing_from_exchange),
            len(result.size_mismatches),
        )

        return result

    def reconcile_periodic(
        self,
        local_positions: Dict[str, Position],
        exchange_connectors: Dict[str, Any],
        paper_mode: bool,
    ) -> ReconciliationResult:
        """Periodic reconciliation (every 5 min).

        Lighter than startup -- only checks for discrepancies, doesn't rebuild state.
        """
        if paper_mode:
            # In paper mode, just persist current state for crash recovery
            self._store.save_positions(list(local_positions.values()))
            return ReconciliationResult(
                positions_local=len(local_positions),
                matched=len(local_positions),
                actions_taken=["paper_mode_persist"],
            )

        # Live mode: fetch and compare
        exchange_positions = self._fetch_exchange_positions(exchange_connectors)
        result = self._compare_positions(local_positions, exchange_positions)

        if result.orphaned_on_exchange or result.missing_from_exchange or result.size_mismatches:
            logger.warning(
                "Periodic reconciliation found discrepancies: "
                "orphaned=%s missing=%s size_mismatch=%s",
                result.orphaned_on_exchange,
                result.missing_from_exchange,
                result.size_mismatches,
            )

            if self._trust_exchange:
                resolved = self._resolve_discrepancies(result, local_positions, exchange_positions)
                local_positions.clear()
                local_positions.update(resolved)
        else:
            logger.debug("Periodic reconciliation: all positions match")

        # Persist reconciled state
        self._store.save_positions(list(local_positions.values()))

        return result

    def persist_state(self, positions: Dict[str, Position]) -> None:
        """Save current position state to SQLite for crash recovery."""
        self._store.save_positions(list(positions.values()))

    def _fetch_exchange_positions(self, connectors: Dict[str, Any]) -> Dict[str, Dict]:
        """Fetch actual positions from all connected exchanges.

        For each connector:
          - Try fetch_positions() (for futures/margin) via the underlying ccxt exchange
          - Try fetch_balance() (for spot -- infer positions from non-zero balances)
          - Try fetch_open_orders() (for pending orders)
        Return normalized dict: asset -> {side, size, entry_price, exchange}
        """
        positions: Dict[str, Dict] = {}

        for name, connector in connectors.items():
            # Try fetching explicit positions (futures / margin accounts)
            try:
                exchange = connector._ensure_connected()
                if hasattr(exchange, "fetch_positions"):
                    raw_positions = exchange.fetch_positions()
                    for pos in raw_positions:
                        symbol = pos.get("symbol", "")
                        contracts = abs(float(pos.get("contracts", 0) or 0))
                        notional = abs(float(pos.get("notional", 0) or 0))
                        size = contracts if contracts > _MIN_DUST_THRESHOLD else notional
                        if size <= _MIN_DUST_THRESHOLD:
                            continue

                        side_raw = pos.get("side", "long")
                        side = "LONG" if side_raw == "long" else "SHORT"
                        entry = float(pos.get("entryPrice", 0) or 0)

                        positions[symbol] = {
                            "side": side,
                            "size": size,
                            "entry_price": entry,
                            "exchange": name,
                        }
                        logger.debug(
                            "Exchange position found on %s: %s %s size=%.6f entry=%.4f",
                            name, side, symbol, size, entry,
                        )
            except Exception as e:
                logger.warning("Failed to fetch positions from %s: %s", name, e)

            # Infer spot positions from non-zero balances
            try:
                balance = connector.get_balance()
                total = balance.get("total", {})
                for currency, amount in total.items():
                    if currency in _QUOTE_CURRENCIES:
                        continue
                    amt = float(amount or 0)
                    if amt <= _MIN_DUST_THRESHOLD:
                        continue

                    # Build a synthetic symbol (e.g. BTC -> BTC/USDT)
                    symbol = f"{currency}/USDT"
                    if symbol not in positions:
                        positions[symbol] = {
                            "side": "LONG",
                            "size": amt,
                            "entry_price": 0.0,  # unknown for spot
                            "exchange": name,
                        }
                        logger.debug(
                            "Spot balance inferred on %s: %s size=%.6f",
                            name, symbol, amt,
                        )
            except Exception as e:
                logger.warning("Failed to fetch balance from %s: %s", name, e)

        return positions

    def _compare_positions(
        self,
        local: Dict[str, Position],
        exchange: Dict[str, Dict],
    ) -> ReconciliationResult:
        """Compare local and exchange positions, identify discrepancies."""
        result = ReconciliationResult()
        result.positions_local = len(local)
        result.positions_exchange = len(exchange)

        local_assets = set(local.keys())
        exchange_assets = set(exchange.keys())

        matched_assets = local_assets & exchange_assets
        orphaned = exchange_assets - local_assets
        missing = local_assets - exchange_assets

        result.orphaned_on_exchange = sorted(orphaned)
        result.missing_from_exchange = sorted(missing)

        # Check size mismatches among matched assets
        matched_count = 0
        for asset in matched_assets:
            local_size = local[asset].size
            exch_size = exchange[asset]["size"]
            # Allow 1% tolerance for rounding
            if abs(local_size - exch_size) / max(local_size, exch_size, 1e-10) > 0.01:
                result.size_mismatches.append(asset)
                logger.warning(
                    "Size mismatch for %s: local=%.6f exchange=%.6f",
                    asset, local_size, exch_size,
                )
            else:
                matched_count += 1

        result.matched = matched_count

        if result.orphaned_on_exchange:
            logger.warning("Orphaned on exchange (not tracked locally): %s", result.orphaned_on_exchange)
        if result.missing_from_exchange:
            logger.warning("Missing from exchange (tracked locally but not on exchange): %s", result.missing_from_exchange)

        return result

    def _resolve_discrepancies(
        self,
        result: ReconciliationResult,
        local: Dict[str, Position],
        exchange: Dict[str, Dict],
    ) -> Dict[str, Position]:
        """Resolve discrepancies by adopting exchange state as truth.

        - Orphaned on exchange: add to local tracking
        - Missing from exchange: remove from local (position was closed externally)
        - Size mismatch: update local to match exchange
        """
        resolved: Dict[str, Position] = dict(local)

        # Orphaned on exchange: adopt into local tracking
        for asset in result.orphaned_on_exchange:
            exch = exchange[asset]
            # Infer asset class from symbol
            asset_class = self._infer_asset_class(asset)
            pos = Position(
                asset=asset,
                asset_class=asset_class,
                side=exch["side"],
                entry_price=exch["entry_price"],
                current_price=exch["entry_price"],
                size=exch["size"],
                stop_loss=0.0,
                take_profit=0.0,
                order_id="",
                strategy="reconciled_orphan",
            )
            resolved[asset] = pos
            action = f"adopted orphaned exchange position: {asset} {exch['side']} size={exch['size']:.6f}"
            result.actions_taken.append(action)
            logger.info(action)

        # Missing from exchange: position was closed externally
        for asset in result.missing_from_exchange:
            removed = resolved.pop(asset, None)
            self._store.remove_position(asset)
            action = f"removed locally tracked position not on exchange: {asset}"
            result.actions_taken.append(action)
            logger.info(action)

        # Size mismatches: update local to match exchange
        for asset in result.size_mismatches:
            if asset in resolved and asset in exchange:
                exch = exchange[asset]
                old_size = resolved[asset].size
                resolved[asset].size = exch["size"]
                resolved[asset].side = exch["side"]
                if exch["entry_price"] > 0:
                    resolved[asset].entry_price = exch["entry_price"]
                action = (
                    f"updated size for {asset}: {old_size:.6f} -> {exch['size']:.6f} "
                    f"(exchange is source of truth)"
                )
                result.actions_taken.append(action)
                logger.info(action)

        return resolved

    @staticmethod
    def _infer_asset_class(symbol: str) -> AssetClass:
        """Infer asset class from a trading symbol."""
        symbol_upper = symbol.upper()
        # Forex pairs
        forex_currencies = {"EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD"}
        parts = symbol_upper.replace("/", " ").split()
        if len(parts) >= 2 and parts[0] in forex_currencies:
            return AssetClass.FOREX
        # Stock-like symbols (no slash, short uppercase)
        if "/" not in symbol and symbol_upper == symbol and len(symbol) <= 5:
            return AssetClass.STOCKS
        # Default to crypto
        return AssetClass.CRYPTO
