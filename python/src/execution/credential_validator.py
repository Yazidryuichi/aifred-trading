"""Pre-flight validation for exchange credentials and connectivity."""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.execution.exchange_connector import ExchangeConnector

logger = logging.getLogger(__name__)


def _mask_key(key: str) -> str:
    """Mask an API key for safe logging: show first 3 and last 3 chars."""
    if not key or len(key) < 8:
        return "***"
    return f"{key[:3]}...{key[-3:]}"


@dataclass
class ValidationResult:
    """Result of a single validation check."""
    check: str        # e.g. "binance_credentials", "binance_connectivity"
    passed: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationReport:
    """Complete validation report for all exchanges."""
    results: List[ValidationResult] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def all_passed(self) -> bool:
        # Balance checks are warnings, not blockers (especially for dry-run)
        return all(
            r.passed for r in self.results
            if "_balance" not in r.check
        )

    @property
    def critical_failures(self) -> List[ValidationResult]:
        return [r for r in self.results
                if not r.passed and "_balance" not in r.check]

    def summary(self) -> str:
        """Human-readable summary."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        lines = [
            f"Validation Report ({self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC)",
            f"  Total checks: {total}  |  Passed: {passed}  |  Failed: {failed}",
        ]
        if failed > 0:
            lines.append("  Failed checks:")
            for r in self.critical_failures:
                lines.append(f"    - {r.check}: {r.message}")
        return "\n".join(lines)


class CredentialValidator:
    """Validates exchange credentials, connectivity, and account state before trading."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._mode = config.get("execution", {}).get("mode", "paper")
        val_cfg = config.get("validation", {})
        self._min_balance_usd = val_cfg.get("min_balance_usd", 100)
        self._required_exchanges = val_cfg.get("required_exchanges", [])
        self._connectivity_timeout_ms = val_cfg.get("connectivity_timeout_ms", 10000)
        self._check_permissions = val_cfg.get("check_trading_permissions", True)

    def validate(self) -> ValidationReport:
        """Run all validation checks. Call this before starting the trading loop."""
        report = ValidationReport()

        if self._mode == "paper":
            report.results.append(ValidationResult(
                check="mode", passed=True,
                message="Paper mode — exchange credentials not required"
            ))
            return report

        # 1. Check that API keys are set and not placeholders
        self._validate_credentials(report)

        # Only proceed to connectivity/balance if credentials passed for at least one exchange
        exchanges_with_creds = self._get_credentialed_exchanges(report)
        if not exchanges_with_creds:
            report.results.append(ValidationResult(
                check="overall_credentials", passed=False,
                message="No exchange has valid credentials configured"
            ))
            return report

        # 2. Test connectivity to each exchange that passed credential check
        connectors = self._validate_connectivity(report, exchanges_with_creds)

        # 3. Verify account balance is non-zero
        if connectors:
            self._validate_balance(report, connectors)

        # 4. Verify trading permissions
        if connectors and self._check_permissions:
            self._validate_permissions(report, connectors)

        # 5. Check required exchanges
        self._validate_required_exchanges(report)

        # Clean up connectors
        for connector in connectors.values():
            try:
                connector._connected = False
            except Exception:
                pass

        return report

    def _validate_credentials(self, report: ValidationReport) -> None:
        """Check that API keys are set and not env var placeholders."""
        exchanges = self.config.get("execution", {}).get("exchanges", {})
        for name, exch_config in exchanges.items():
            if not exch_config.get("enabled", False):
                continue

            api_key = exch_config.get("api_key", "")
            api_secret = exch_config.get("api_secret", "")

            # Check for empty
            if not api_key or not api_secret:
                report.results.append(ValidationResult(
                    check=f"{name}_credentials", passed=False,
                    message=f"{name}: API key or secret is empty",
                    details={"exchange": name, "reason": "empty"},
                ))
                continue

            # Check for unresolved env var placeholders like "${BINANCE_API_KEY}"
            if api_key.startswith("${") or api_secret.startswith("${"):
                report.results.append(ValidationResult(
                    check=f"{name}_credentials", passed=False,
                    message=f"{name}: API key contains unresolved env var placeholder — "
                            f"set the environment variable or update your .env file",
                    details={"exchange": name, "reason": "unresolved_placeholder"},
                ))
                continue

            report.results.append(ValidationResult(
                check=f"{name}_credentials", passed=True,
                message=f"{name}: Credentials present (key={_mask_key(api_key)})",
                details={"exchange": name},
            ))

        # Also check Hyperliquid (separate config section)
        hl_config = self.config.get("execution", {}).get("hyperliquid", {})
        if hl_config.get("enabled", False):
            address = hl_config.get("user_address", "")
            private_key = hl_config.get("private_key", "")
            if address and private_key and not address.startswith("${") and not private_key.startswith("${"):
                report.results.append(ValidationResult(
                    check="hyperliquid_credentials", passed=True,
                    message=f"hyperliquid: Credentials present (address={_mask_key(address)})",
                    details={"exchange": "hyperliquid"},
                ))
            else:
                report.results.append(ValidationResult(
                    check="hyperliquid_credentials", passed=False,
                    message="hyperliquid: Address or private key is empty or unresolved",
                    details={"exchange": "hyperliquid", "reason": "empty_or_placeholder"},
                ))

    def _get_credentialed_exchanges(self, report: ValidationReport) -> Dict[str, Dict[str, Any]]:
        """Return exchange configs that passed credential validation."""
        passed_names = {
            r.details.get("exchange")
            for r in report.results
            if r.passed and r.check.endswith("_credentials")
        }
        exchanges = self.config.get("execution", {}).get("exchanges", {})
        result = {
            name: cfg for name, cfg in exchanges.items()
            if name in passed_names
        }
        # Include Hyperliquid if it passed
        if "hyperliquid" in passed_names:
            result["hyperliquid"] = self.config.get("execution", {}).get("hyperliquid", {})
        return result

    def _validate_connectivity(
        self,
        report: ValidationReport,
        exchanges: Dict[str, Dict[str, Any]],
    ) -> Dict[str, ExchangeConnector]:
        """Test actual connectivity to each exchange. Returns live connectors."""
        live_connectors: Dict[str, ExchangeConnector] = {}

        for name, exch_config in exchanges.items():
            connector = ExchangeConnector(
                name=name,
                api_key=exch_config.get("api_key", ""),
                secret=exch_config.get("api_secret", ""),
                sandbox=False,
                extra_params={"timeout": self._connectivity_timeout_ms},
            )
            try:
                connector.connect()
                latency = connector.ping()
                if latency < 0:
                    report.results.append(ValidationResult(
                        check=f"{name}_connectivity", passed=False,
                        message=f"{name}: Ping failed (exchange unreachable)",
                        details={"exchange": name, "latency_ms": latency},
                    ))
                else:
                    report.results.append(ValidationResult(
                        check=f"{name}_connectivity", passed=True,
                        message=f"{name}: Connected (latency={latency:.0f}ms)",
                        details={"exchange": name, "latency_ms": latency},
                    ))
                    live_connectors[name] = connector
            except Exception as e:
                report.results.append(ValidationResult(
                    check=f"{name}_connectivity", passed=False,
                    message=f"{name}: Connection failed — {e}",
                    details={"exchange": name, "error": str(e)},
                ))

        return live_connectors

    def _validate_balance(
        self,
        report: ValidationReport,
        connectors: Dict[str, ExchangeConnector],
    ) -> None:
        """Verify account has non-zero balance above minimum threshold."""
        for name, connector in connectors.items():
            try:
                balance = connector.get_balance()
                # Sum up free balances in USD-denominated stablecoins and USD
                total_free = 0.0
                free_balances = balance.get("free", {})
                for currency in ("USD", "USDT", "USDC", "BUSD"):
                    val = free_balances.get(currency, 0)
                    if val:
                        total_free += float(val)

                if total_free < self._min_balance_usd:
                    report.results.append(ValidationResult(
                        check=f"{name}_balance", passed=False,
                        message=f"{name}: Available balance ${total_free:.2f} is below "
                                f"minimum ${self._min_balance_usd:.2f}",
                        details={
                            "exchange": name,
                            "available_usd": total_free,
                            "minimum_usd": self._min_balance_usd,
                        },
                    ))
                else:
                    report.results.append(ValidationResult(
                        check=f"{name}_balance", passed=True,
                        message=f"{name}: Available balance ${total_free:.2f}",
                        details={
                            "exchange": name,
                            "available_usd": total_free,
                        },
                    ))
            except Exception as e:
                report.results.append(ValidationResult(
                    check=f"{name}_balance", passed=False,
                    message=f"{name}: Failed to fetch balance — {e}",
                    details={"exchange": name, "error": str(e)},
                ))

    def _validate_permissions(
        self,
        report: ValidationReport,
        connectors: Dict[str, ExchangeConnector],
    ) -> None:
        """Verify trading permissions by loading markets. Best-effort check."""
        configured_assets = []
        assets_cfg = self.config.get("assets", {})
        for asset_list in assets_cfg.values():
            if isinstance(asset_list, list):
                configured_assets.extend(asset_list)

        for name, connector in connectors.items():
            try:
                exchange = connector._ensure_connected()
                exchange.load_markets()
                available_markets = set(exchange.symbols)

                missing = [a for a in configured_assets
                           if "/" in a and a not in available_markets]

                if missing:
                    report.results.append(ValidationResult(
                        check=f"{name}_permissions", passed=True,
                        message=f"{name}: Markets loaded, but {len(missing)} configured "
                                f"pair(s) not found: {', '.join(missing[:5])}",
                        details={
                            "exchange": name,
                            "missing_pairs": missing,
                            "warning": True,
                        },
                    ))
                else:
                    report.results.append(ValidationResult(
                        check=f"{name}_permissions", passed=True,
                        message=f"{name}: All configured trading pairs available",
                        details={"exchange": name},
                    ))
            except Exception as e:
                # Best-effort: don't fail validation if market load fails
                report.results.append(ValidationResult(
                    check=f"{name}_permissions", passed=True,
                    message=f"{name}: Could not verify trading permissions — {e} "
                            f"(non-fatal, continuing)",
                    details={"exchange": name, "error": str(e), "warning": True},
                ))

    def _validate_required_exchanges(self, report: ValidationReport) -> None:
        """Check that all required exchanges have passed connectivity."""
        if not self._required_exchanges:
            # At least one exchange must have passed connectivity
            connectivity_passed = any(
                r.passed for r in report.results
                if r.check.endswith("_connectivity")
            )
            if not connectivity_passed:
                report.results.append(ValidationResult(
                    check="required_exchanges", passed=False,
                    message="No exchange passed connectivity test",
                ))
            return

        for req_name in self._required_exchanges:
            conn_result = next(
                (r for r in report.results if r.check == f"{req_name}_connectivity"),
                None,
            )
            if conn_result is None or not conn_result.passed:
                report.results.append(ValidationResult(
                    check=f"required_{req_name}", passed=False,
                    message=f"Required exchange '{req_name}' did not pass connectivity",
                ))
