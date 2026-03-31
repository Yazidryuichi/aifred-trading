#!/usr/bin/env python3
"""AIFred Trading System — Component Health Validation.

Independently tests each subsystem and reports pass/fail with timing.

Usage:
    python validate_system.py
    python validate_system.py --verbose
"""

import argparse
import asyncio
import importlib
import logging
import os
import sys
import time
from typing import List, Tuple

# Ensure the project root is on sys.path so ``src.*`` imports work.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

_results: List[Tuple[str, bool, str, float]] = []  # (name, passed, detail, elapsed)


def _record(name: str, passed: bool, detail: str, elapsed: float) -> None:
    _results.append((name, passed, detail, elapsed))
    tag = "\033[92m[PASS]\033[0m" if passed else "\033[91m[FAIL]\033[0m"
    print(f"  {tag} {name} - {detail} ({elapsed:.1f}s)")


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_core_imports() -> None:
    """Verify that all core modules can be imported."""
    t0 = time.monotonic()
    modules = [
        ("src.utils.types", "Shared types"),
        ("src.config", "Configuration loader"),
        ("src.orchestrator", "Orchestrator"),
        ("src.execution.execution_engine", "Execution engine"),
        ("src.execution.paper_trader", "Paper trader"),
        ("src.execution.hyperliquid_connector", "Hyperliquid connector"),
        ("src.execution.hyperliquid_exchange", "Hyperliquid exchange wrapper"),
        ("src.risk.risk_gate", "Risk gate"),
        ("src.risk.portfolio_monitor", "Portfolio monitor"),
        ("src.risk.drawdown_manager", "Drawdown manager"),
        ("src.risk.position_sizer", "Position sizer"),
        ("src.risk.correlation_tracker", "Correlation tracker"),
        ("src.analysis.technical.signals", "Technical analysis agent"),
        ("src.analysis.sentiment.sentiment_signals", "Sentiment analysis agent"),
        ("src.analysis.onchain.defi_llama", "DeFiLlama client"),
        ("src.analysis.onchain.onchain_aggregator", "On-chain aggregator"),
        ("src.analysis.meta_reasoning", "Meta-reasoning agent"),
    ]
    for mod_path, label in modules:
        t1 = time.monotonic()
        try:
            importlib.import_module(mod_path)
            _record(f"Import: {label}", True, mod_path, time.monotonic() - t1)
        except Exception as e:
            _record(f"Import: {label}", False, str(e), time.monotonic() - t1)


def check_technical_analysis() -> None:
    """Initialize TechnicalAnalysisAgent."""
    t0 = time.monotonic()
    try:
        from src.analysis.technical.signals import TechnicalAnalysisAgent
        agent = TechnicalAnalysisAgent(config_override={
            "technical": {
                "lstm": {"hidden_size": 64, "num_layers": 2},
                "transformer": {"d_model": 64, "nhead": 4, "num_layers": 2},
                "cnn": {"channels": [16, 32], "kernel_sizes": [3, 5]},
            }
        })
        _record("Technical Analysis", True, "agent initialized", time.monotonic() - t0)
    except Exception as e:
        _record("Technical Analysis", False, str(e), time.monotonic() - t0)


def check_sentiment_analysis() -> None:
    """Initialize SentimentAnalysisAgent and check API key availability."""
    t0 = time.monotonic()
    try:
        from src.analysis.sentiment.sentiment_signals import SentimentAnalysisAgent
        agent = SentimentAnalysisAgent()

        # Check for common API keys
        warnings = []
        if not os.getenv("REDDIT_CLIENT_ID"):
            warnings.append("Reddit API keys missing")
        if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
            warnings.append("No LLM API key found")

        if warnings:
            _record("Sentiment Analysis", True,
                     f"initialized (warnings: {'; '.join(warnings)})",
                     time.monotonic() - t0)
        else:
            _record("Sentiment Analysis", True, "initialized, API keys present",
                     time.monotonic() - t0)
    except Exception as e:
        _record("Sentiment Analysis", False, str(e), time.monotonic() - t0)


def check_onchain() -> None:
    """Initialize DeFiLlama client and test connectivity."""
    t0 = time.monotonic()
    try:
        from src.analysis.onchain.defi_llama import DeFiLlamaClient
        client = DeFiLlamaClient()
        _record("On-Chain: DeFiLlama", True, "client initialized", time.monotonic() - t0)
    except Exception as e:
        _record("On-Chain: DeFiLlama", False, str(e), time.monotonic() - t0)


async def check_defillama_api() -> None:
    """Test DeFiLlama API reachability."""
    t0 = time.monotonic()
    try:
        import aiohttp
        headers = {"Accept-Encoding": "gzip, deflate"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10), headers=headers) as s:
            async with s.get("https://api.llama.fi/protocols") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    _record("On-Chain: DeFiLlama API", True,
                             f"reachable, {len(data)} protocols",
                             time.monotonic() - t0)
                else:
                    _record("On-Chain: DeFiLlama API", False,
                             f"HTTP {resp.status}", time.monotonic() - t0)
    except Exception as e:
        _record("On-Chain: DeFiLlama API", False, str(e), time.monotonic() - t0)


def check_risk_manager() -> None:
    """Initialize the full risk management stack."""
    t0 = time.monotonic()
    try:
        from src.risk.portfolio_monitor import PortfolioMonitor
        from src.risk.drawdown_manager import DrawdownManager
        from src.risk.correlation_tracker import CorrelationTracker
        from src.risk.risk_gate import RiskGate

        config = {"risk": {
            "max_position_pct": 3.0,
            "max_concurrent_positions": 10,
            "max_daily_drawdown_pct": 5.0,
        }}
        pm = PortfolioMonitor(config)
        dm = DrawdownManager(config)
        ct = CorrelationTracker(config)
        rg = RiskGate(pm, dm, ct, config)
        pm.set_portfolio_value(100_000.0, 100_000.0)
        dm.initialize(100_000.0)
        _record("Risk Manager", True, "full stack initialized", time.monotonic() - t0)
    except Exception as e:
        _record("Risk Manager", False, str(e), time.monotonic() - t0)


def check_execution_engine() -> None:
    """Initialize the execution engine in paper mode."""
    t0 = time.monotonic()
    try:
        from src.execution.execution_engine import ExecutionAgent
        config = {"execution": {"mode": "paper", "slippage_tolerance_pct": 0.1}}
        agent = ExecutionAgent(config)
        _record("Execution Engine", True,
                 f"paper_mode={agent._paper_mode}", time.monotonic() - t0)
    except Exception as e:
        _record("Execution Engine", False, str(e), time.monotonic() - t0)


async def check_hyperliquid_testnet() -> None:
    """Test Hyperliquid testnet connectivity."""
    t0 = time.monotonic()
    try:
        from src.execution.hyperliquid_connector import HyperliquidConnector
        hl = HyperliquidConnector(testnet=True)
        await hl.connect()
        latency = await hl.ping()
        mids = await hl.get_all_mids()
        await hl.disconnect()

        if latency > 0 and len(mids) > 0:
            btc_price = mids.get("BTC", 0.0)
            _record("Hyperliquid Testnet", True,
                     f"reachable, latency={latency:.0f}ms, "
                     f"{len(mids)} assets, BTC=${btc_price:,.0f}",
                     time.monotonic() - t0)
        else:
            _record("Hyperliquid Testnet", False,
                     f"latency={latency:.0f}ms, assets={len(mids)}",
                     time.monotonic() - t0)
    except Exception as e:
        _record("Hyperliquid Testnet", False, str(e), time.monotonic() - t0)


async def check_hyperliquid_mainnet() -> None:
    """Test Hyperliquid mainnet connectivity."""
    t0 = time.monotonic()
    try:
        from src.execution.hyperliquid_connector import HyperliquidConnector
        hl = HyperliquidConnector(testnet=False)
        await hl.connect()
        latency = await hl.ping()
        await hl.disconnect()

        if latency > 0:
            _record("Hyperliquid Mainnet", True,
                     f"reachable, latency={latency:.0f}ms",
                     time.monotonic() - t0)
        else:
            _record("Hyperliquid Mainnet", False,
                     f"latency={latency:.0f}ms", time.monotonic() - t0)
    except Exception as e:
        _record("Hyperliquid Mainnet", False, str(e), time.monotonic() - t0)


def check_orchestrator() -> None:
    """Initialize the Orchestrator with paper mode config."""
    t0 = time.monotonic()
    try:
        from src.orchestrator import Orchestrator
        config = {
            "execution": {"mode": "paper", "slippage_tolerance_pct": 0.1},
            "orchestrator": {
                "scan_interval_seconds": 60,
                "min_confidence_threshold": 78,
                "max_trades_per_day": 20,
            },
            "risk": {
                "max_position_pct": 3.0,
                "max_concurrent_positions": 10,
                "max_daily_drawdown_pct": 5.0,
            },
            "assets": {"crypto": ["BTC/USDT", "ETH/USDT"]},
        }
        orch = Orchestrator(config)
        status = orch.initialize_agents()
        passed_agents = sum(1 for v in status.values() if v)
        total_agents = len(status)
        _record("Orchestrator", True,
                 f"initialized, {passed_agents}/{total_agents} agents ready",
                 time.monotonic() - t0)
    except Exception as e:
        _record("Orchestrator", False, str(e), time.monotonic() - t0)


def check_config_loading() -> None:
    """Test that default configuration loads correctly."""
    t0 = time.monotonic()
    try:
        from src.config import load_config
        config = load_config()
        asset_count = sum(
            len(config.get("assets", {}).get(k, []))
            for k in ("crypto", "stocks", "forex")
        )
        _record("Configuration", True,
                 f"default.yaml loaded, {asset_count} assets configured",
                 time.monotonic() - t0)
    except Exception as e:
        _record("Configuration", False, str(e), time.monotonic() - t0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_all_checks(verbose: bool = False) -> int:
    """Run all validation checks and print the report.

    Returns:
        Exit code: 0 if all critical checks pass, 1 otherwise.
    """
    print()
    print("=" * 70)
    print("  AIFred Trading System — Component Validation")
    print("=" * 70)
    print()

    # --- Synchronous checks ---
    print("--- Core Imports ---")
    check_core_imports()

    print("\n--- Configuration ---")
    check_config_loading()

    print("\n--- Analysis Agents ---")
    check_technical_analysis()
    check_sentiment_analysis()
    check_onchain()

    print("\n--- Risk Management ---")
    check_risk_manager()

    print("\n--- Execution ---")
    check_execution_engine()

    print("\n--- Orchestrator ---")
    check_orchestrator()

    # --- Async checks (network) ---
    print("\n--- Network Connectivity ---")
    await check_defillama_api()
    await check_hyperliquid_testnet()
    await check_hyperliquid_mainnet()

    # --- Summary ---
    print()
    print("=" * 70)
    total = len(_results)
    passed = sum(1 for _, ok, _, _ in _results if ok)
    failed = total - passed
    print(f"  Results: {passed}/{total} passed, {failed} failed")
    total_time = sum(t for _, _, _, t in _results)
    print(f"  Total time: {total_time:.1f}s")
    print("=" * 70)

    if verbose and failed > 0:
        print("\n  Failed checks:")
        for name, ok, detail, _ in _results:
            if not ok:
                print(f"    - {name}: {detail}")

    print()
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AIFred Trading System — Component Validation",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed failure information",
    )
    args = parser.parse_args()

    # Suppress noisy loggers during validation
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("src").setLevel(logging.WARNING)
    logging.getLogger("aifred").setLevel(logging.WARNING)

    return asyncio.run(run_all_checks(verbose=args.verbose))


if __name__ == "__main__":
    sys.exit(main())
