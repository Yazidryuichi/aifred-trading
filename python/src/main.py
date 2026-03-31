"""Main entry point for the multi-agent trading system.

Usage:
    python -m src.main                          # Paper trading, default config
    python -m src.main --mode paper             # Explicit paper mode
    python -m src.main --mode live              # Live trading (requires credentials)
    python -m src.main --config path/to/config.yaml
    python -m src.main --scan-interval 30       # 30-second scan interval
    python -m src.main --assets BTC/USDT,ETH/USDT  # Specific assets only
    python -m src.main --mcp                    # Start MCP server for AI agents

Features:
    - Parses command-line arguments
    - Loads configuration from YAML (with env var resolution)
    - Initializes all agents
    - Starts the orchestrator scan loop
    - Handles graceful shutdown (SIGINT/SIGTERM)
    - Logs startup/shutdown events
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import load_config, get_config
from src.data.market_data_provider import MarketDataProvider
from src.data.websocket_manager import WebSocketManager
from src.execution.abstract_exchange import create_exchange
from src.execution.credential_validator import CredentialValidator
from src.execution.reconciler import PositionReconciler
from src.orchestrator import Orchestrator

logger = logging.getLogger("aifred")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="AIFred Multi-Agent Trading System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main                           # Paper trading with defaults
  python -m src.main --mode paper --scan-interval 30
  python -m src.main --mode live --config prod.yaml
  python -m src.main --assets BTC/USDT,ETH/USDT --scan-interval 15
  python -m src.main --mcp                     # MCP server for Claude/AI agents
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["paper", "live"],
        default="paper",
        help="Trading mode: 'paper' (simulated) or 'live' (real orders). Default: paper",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to YAML configuration file. Default: src/config/default.yaml",
    )
    parser.add_argument(
        "--scan-interval",
        type=int,
        default=None,
        help="Scan interval in seconds. Overrides config value. Default: 60",
    )
    parser.add_argument(
        "--assets",
        type=str,
        default=None,
        help="Comma-separated list of assets to trade (overrides config). "
             "Example: BTC/USDT,ETH/USDT,SOL/USDT",
    )
    parser.add_argument(
        "--portfolio-value",
        type=float,
        default=10000.0,
        help="Initial portfolio value in USD (for paper mode). Default: 10000",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Logging level. Overrides config value.",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Log file path. Overrides config value.",
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        default=False,
        help="Start the MCP (Model Context Protocol) server instead of the trading loop. "
             "Exposes trading engine capabilities as tools for AI agents.",
    )
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Run walk-forward optimization instead of trading",
    )
    parser.add_argument(
        "--optimize-symbol",
        type=str,
        default="BTC/USDT",
        help="Symbol to optimize (used with --optimize). Default: BTC/USDT",
    )
    parser.add_argument(
        "--optimize-start",
        type=str,
        default=None,
        help="Optimization start date YYYY-MM-DD (used with --optimize). Default: 1 year ago",
    )
    parser.add_argument(
        "--optimize-end",
        type=str,
        default=None,
        help="Optimization end date YYYY-MM-DD (used with --optimize). Default: today",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run full live pipeline but stop before submitting orders. "
             "Logs what would have been traded. Use for 24-48h before going live.",
    )
    return parser.parse_args()


def setup_logging(config: dict, args: argparse.Namespace) -> None:
    """Configure logging based on config and CLI overrides."""
    mon_cfg = config.get("monitoring", {})
    log_cfg = mon_cfg.get("logging", {})

    level_str = args.log_level or log_cfg.get("level", "INFO")
    level = getattr(logging, level_str.upper(), logging.INFO)

    log_file = args.log_file or log_cfg.get("file", "logs/trading.log")

    # Create log directory
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # Formatter
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Root logger
    root = logging.getLogger()
    root.setLevel(level)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(fmt)
    root.addHandler(console)

    # File handler
    try:
        file_handler = logging.FileHandler(log_file, mode="a")
        file_handler.setLevel(level)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except (OSError, PermissionError) as e:
        logger.warning("Could not create log file %s: %s", log_file, e)

    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("xgboost").setLevel(logging.WARNING)


def apply_cli_overrides(config: dict, args: argparse.Namespace) -> dict:
    """Apply command-line overrides to the configuration dict."""
    # Mode override
    if args.mode:
        if "execution" not in config:
            config["execution"] = {}
        config["execution"]["mode"] = args.mode

    # Scan interval override
    if args.scan_interval is not None:
        if "orchestrator" not in config:
            config["orchestrator"] = {}
        config["orchestrator"]["scan_interval_seconds"] = args.scan_interval

    # Assets override
    if args.assets:
        asset_list = [a.strip() for a in args.assets.split(",") if a.strip()]
        if asset_list:
            # Classify assets by type
            crypto_assets = [a for a in asset_list if "/" in a]
            stock_assets = [a for a in asset_list if "/" not in a and len(a) <= 5]
            if "assets" not in config:
                config["assets"] = {}
            if crypto_assets:
                config["assets"]["crypto"] = crypto_assets
            else:
                config["assets"]["crypto"] = []
            if stock_assets:
                config["assets"]["stocks"] = stock_assets
            else:
                config["assets"]["stocks"] = []
            config["assets"]["forex"] = []

    return config


def print_startup_banner(config: dict, args: argparse.Namespace) -> None:
    """Print startup information."""
    mode = config.get("execution", {}).get("mode", "paper")
    scan_interval = config.get("orchestrator", {}).get("scan_interval_seconds", 60)
    confidence = config.get("orchestrator", {}).get("min_confidence_threshold", 70)

    asset_count = sum(
        len(config.get("assets", {}).get(k, []))
        for k in ("crypto", "stocks", "forex")
    )

    banner = f"""
================================================================================
  AIFred Multi-Agent Trading System
================================================================================
  Mode:             {mode.upper()}
  Scan Interval:    {scan_interval}s
  Confidence:       {confidence}%
  Assets:           {asset_count}
  Portfolio Value:  ${args.portfolio_value:,.2f}
  Config:           {args.config or 'default'}
  Started:          {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
================================================================================
"""
    print(banner)
    logger.info("AIFred starting: mode=%s, interval=%ds, assets=%d",
                mode, scan_interval, asset_count)


async def run_system(
    orchestrator: Orchestrator,
    shutdown_event: asyncio.Event,
    ws_manager: Optional[WebSocketManager] = None,
    exchange: Optional[object] = None,
) -> None:
    """Run the orchestrator and supporting services until shutdown is signaled.

    Args:
        orchestrator: Configured Orchestrator instance.
        shutdown_event: Set by signal handlers to trigger graceful shutdown.
        ws_manager: Optional WebSocketManager for real-time data.
        exchange: Optional AbstractExchange to disconnect on shutdown.
    """
    # Start WebSocket manager in background (if available)
    ws_task = None
    if ws_manager is not None:
        ws_task = asyncio.create_task(ws_manager.start())
        logger.info("WebSocket manager started as background task")

    # Run orchestrator in a task
    orch_task = asyncio.create_task(orchestrator.run())

    # Wait for shutdown signal
    await shutdown_event.wait()

    # --- Graceful shutdown sequence ---
    logger.info("Shutdown signal received, stopping orchestrator...")
    orchestrator.stop()

    # Wait for orchestrator to finish current cycle
    try:
        await asyncio.wait_for(orch_task, timeout=30.0)
    except asyncio.TimeoutError:
        logger.warning("Orchestrator did not stop within 30s, cancelling")
        orch_task.cancel()
        try:
            await orch_task
        except asyncio.CancelledError:
            pass

    # Stop WebSocket manager
    if ws_manager is not None:
        logger.info("Stopping WebSocket manager...")
        await ws_manager.stop()
        if ws_task is not None and not ws_task.done():
            ws_task.cancel()
            try:
                await ws_task
            except asyncio.CancelledError:
                pass

    # Disconnect exchange
    if exchange is not None:
        try:
            await exchange.disconnect()
            logger.info("Exchange disconnected")
        except Exception as e:
            logger.warning("Error disconnecting exchange: %s", e)


def _run_walk_forward_optimization(config: dict, args: argparse.Namespace) -> int:
    """Run walk-forward optimization and print results.

    Called when ``--optimize`` flag is passed.  Initializes a data
    provider, creates a ``WalkForwardOptimizer``, and runs the full
    walk-forward loop.

    Args:
        config: Loaded configuration dictionary.
        args: Parsed CLI arguments.

    Returns:
        Exit code (0 on success, 1 on failure).
    """
    from src.optimizer.walk_forward import WalkForwardOptimizer
    from src.data.market_data_provider import MarketDataProvider

    logger.info("Starting walk-forward optimization mode")

    # Parse date range
    start_date = None
    end_date = None
    if args.optimize_start:
        try:
            start_date = datetime.strptime(args.optimize_start, "%Y-%m-%d")
        except ValueError:
            print(f"ERROR: Invalid start date format: {args.optimize_start}", file=sys.stderr)
            return 1
    if args.optimize_end:
        try:
            end_date = datetime.strptime(args.optimize_end, "%Y-%m-%d")
        except ValueError:
            print(f"ERROR: Invalid end date format: {args.optimize_end}", file=sys.stderr)
            return 1

    # Create data provider
    data_cfg = config.get("data", {})
    data_provider = MarketDataProvider(
        default_exchange=data_cfg.get("default_exchange", "binance"),
        cache_ttl=data_cfg.get("cache_ttl_seconds", 60),
        min_candles=data_cfg.get("min_candles", 200),
    )

    # Create and run optimizer
    optimizer = WalkForwardOptimizer(config, data_provider=data_provider)
    symbol = args.optimize_symbol

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(
            optimizer.run(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            )
        )
        print(result.summary())
        print(f"\nBest consensus parameters:\n{result.best_params}")
        return 0
    except ValueError as e:
        logger.error("Walk-forward optimization failed: %s", e)
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        logger.error("Walk-forward optimization error: %s", e, exc_info=True)
        return 1
    finally:
        loop.close()


def main() -> int:
    """Main entry point. Returns exit code."""
    args = parse_args()

    # Load configuration
    try:
        config = load_config(config_path=args.config)
    except FileNotFoundError:
        print(f"ERROR: Config file not found: {args.config}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: Failed to load config: {e}", file=sys.stderr)
        return 1

    # Apply live config overlay when --mode live
    if args.mode == "live":
        live_yaml = os.path.join(os.path.dirname(__file__), "config", "live.yaml")
        if os.path.exists(live_yaml):
            from src.config import merge_configs
            import yaml
            with open(live_yaml) as f:
                live_overlay = yaml.safe_load(f)
            if live_overlay:
                config = merge_configs(config, live_overlay)
            logger.info("Live config overlay applied from %s", live_yaml)

    # Apply CLI overrides
    config = apply_cli_overrides(config, args)

    if args.dry_run:
        config.setdefault("execution", {})["dry_run"] = True
        logger.info("DRY RUN MODE: Orders will NOT be submitted to exchanges")

    # Setup logging
    setup_logging(config, args)

    # --- Walk-forward optimization mode ---
    if getattr(args, "optimize", False):
        return _run_walk_forward_optimization(config, args)

    # Print banner
    print_startup_banner(config, args)

    # Create orchestrator
    orchestrator = Orchestrator(config)

    # Initialize all agents
    logger.info("Initializing agents...")
    agent_status = orchestrator.initialize_agents()
    for agent_name, is_ok in agent_status.items():
        status_str = "OK" if is_ok else "FAILED"
        log_fn = logger.info if is_ok else logger.error
        log_fn("  Agent %-20s: %s", agent_name, status_str)

    # Check critical agents
    critical_agents = ["technical", "risk", "execution"]
    failed_critical = [a for a in critical_agents if not agent_status.get(a, False)]
    if failed_critical:
        logger.error(
            "Critical agents failed to initialize: %s. Aborting.",
            ", ".join(failed_critical),
        )
        return 1

    # Validate exchange credentials and connectivity (for live mode)
    logger.info("Running pre-flight validation...")
    validator = CredentialValidator(config)
    report = validator.validate()

    for result in report.results:
        log_fn = logger.info if result.passed else logger.error
        log_fn("  Validation %-30s: %s — %s", result.check,
               "PASS" if result.passed else "FAIL", result.message)

    if args.mode == "live" and not report.all_passed:
        logger.critical(
            "LIVE MODE BLOCKED: Credential validation failed. "
            "Fix the issues above before trading with real money."
        )
        for failure in report.critical_failures:
            logger.critical("  CRITICAL: %s — %s", failure.check, failure.message)
        sys.exit(1)

    if args.mode == "live" and report.all_passed:
        logger.info("LIVE MODE VALIDATED: All credential checks passed")

    # Wire up components and run in async context
    loop = asyncio.new_event_loop()
    exit_code = 0

    try:
        exit_code = loop.run_until_complete(
            _async_main(config, orchestrator, args)
        )
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down...")
        orchestrator.stop()
    except Exception as e:
        logger.error("Unhandled error in main loop: %s", e, exc_info=True)
        exit_code = 1
    finally:
        loop.close()

    return exit_code


async def _async_main(
    config: dict,
    orchestrator: Orchestrator,
    args: argparse.Namespace,
) -> int:
    """Async entry point: wires up exchange, WebSocket, reconciler, and runs.

    All async component initialization (exchange connect, WS subscribe, etc.)
    happens here. The sync ``main()`` delegates to this after agent init and
    credential validation are complete.
    """
    mode = config.get("execution", {}).get("mode", "paper")
    exchange = None
    ws_manager = None
    reconciler = None

    # --- 1. Create exchange via factory ---
    try:
        exchange = create_exchange(mode, config.get("execution", {}))
        logger.info("Exchange created: mode=%s", mode)
    except Exception as e:
        logger.warning("Could not create AbstractExchange (%s), proceeding without it", e)

    # --- 2. Connect exchange (async lifecycle) ---
    if exchange is not None:
        try:
            await exchange.connect()
            logger.info("Exchange connected")
        except Exception as e:
            logger.warning("Exchange connect failed: %s", e)

    # --- 3. Create WebSocket manager (if enabled) ---
    ws_cfg = config.get("data", {}).get("websocket", {})
    if ws_cfg.get("enabled", False):
        try:
            ws_manager = WebSocketManager(
                exchange_id=ws_cfg.get(
                    "exchange",
                    config.get("data", {}).get("default_exchange", "binance"),
                ),
                config=ws_cfg,
            )
            await ws_manager.connect()

            # Subscribe to all configured assets
            all_assets = []
            for class_name in ("crypto", "stocks", "forex"):
                all_assets.extend(config.get("assets", {}).get(class_name, []))
            if all_assets:
                await ws_manager.subscribe_tickers(all_assets)
            logger.info("WebSocket manager initialized (%d symbols)", len(all_assets))
        except Exception as e:
            logger.warning(
                "WebSocket manager initialization failed (%s), proceeding without it", e,
            )
            ws_manager = None

    # --- 4. Wire up market data provider ---
    data_cfg = config.get("data", {})
    market_data_provider = MarketDataProvider(
        default_exchange=data_cfg.get("default_exchange", "binance"),
        cache_ttl=data_cfg.get("cache_ttl_seconds", 60),
        min_candles=data_cfg.get("min_candles", 200),
    )
    if ws_manager is not None and hasattr(market_data_provider, "set_websocket_manager"):
        market_data_provider.set_websocket_manager(ws_manager)
    orchestrator.set_data_provider(market_data_provider.get_data)
    logger.info(
        "Market data provider initialized (exchange=%s)",
        data_cfg.get("default_exchange", "binance"),
    )

    # --- 5. Set initial portfolio value ---
    orchestrator.set_portfolio_value(
        total_value=args.portfolio_value,
        cash=args.portfolio_value,
    )
    logger.info("Portfolio initialized: $%.2f", args.portfolio_value)

    # --- 6. Attach exchange and WebSocket manager to orchestrator ---
    if exchange is not None:
        orchestrator.set_exchange(exchange)
    if ws_manager is not None:
        orchestrator.set_websocket_manager(ws_manager)

    # --- 7. Create and attach reconciler ---
    recon_cfg = config.get("reconciliation", {})
    if recon_cfg.get("enabled", True):
        try:
            reconciler = PositionReconciler(config)
            orchestrator.set_reconciler(reconciler)
            logger.info("Position reconciler initialized")
        except Exception as e:
            logger.warning("Position reconciler initialization failed: %s", e)

    # --- 8. Reconcile positions on startup ---
    if reconciler is not None and recon_cfg.get("on_startup", True):
        try:
            exec_agent = orchestrator.get_execution_agent()
            if exec_agent is not None:
                local_positions = {
                    p.asset: p for p in exec_agent.get_open_positions()
                }
                exchange_connectors = {}
                if hasattr(exec_agent, "_connectors") and exec_agent._connectors:
                    exchange_connectors = exec_agent._connectors
                elif hasattr(exec_agent, "_connector") and exec_agent._connector:
                    exchange_connectors = {"default": exec_agent._connector}

                recon_result = reconciler.reconcile_on_startup(
                    local_positions=local_positions,
                    exchange_connectors=exchange_connectors,
                    paper_mode=(mode != "live"),
                )
                logger.info(
                    "Startup reconciliation: local=%d, exchange=%d, matched=%d, "
                    "orphaned=%d, missing=%d",
                    recon_result.positions_local,
                    recon_result.positions_exchange,
                    recon_result.matched,
                    len(recon_result.orphaned_on_exchange),
                    len(recon_result.missing_from_exchange),
                )
        except Exception as e:
            logger.warning("Startup reconciliation failed: %s", e)

    # --- 9. Wire up MCP server references (lazy import) ---
    try:
        from src.mcp_server import set_system_references
        set_system_references(
            orchestrator=orchestrator,
            data_provider=market_data_provider,
            ws_manager=ws_manager,
            config=config,
        )
        logger.info("MCP server references wired up")
    except ImportError:
        logger.debug("MCP package not installed, skipping MCP server wiring")

    # --- 10. If --mcp flag, run MCP server instead of trading loop ---
    if args.mcp:
        logger.info("Starting MCP server (trading loop disabled)...")
        try:
            from src.mcp_server import mcp as mcp_server
            mcp_server.run()
        except ImportError:
            logger.error("MCP package not installed. Run: pip install mcp")
            return 1
        except KeyboardInterrupt:
            logger.info("MCP server stopped by user")
        except Exception as e:
            logger.error("MCP server error: %s", e, exc_info=True)
            return 1
        return 0

    # --- 11. Setup shutdown event and signal handlers ---
    shutdown_event = asyncio.Event()
    loop = asyncio.get_event_loop()

    def _signal_handler(sig, frame):
        sig_name = signal.Signals(sig).name
        logger.info("Received %s, initiating graceful shutdown...", sig_name)
        loop.call_soon_threadsafe(shutdown_event.set)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # --- 12. Run orchestrator + services ---
    start_time = time.monotonic()
    exit_code = 0

    try:
        await run_system(orchestrator, shutdown_event, ws_manager, exchange)
    except Exception as e:
        logger.error("Unhandled error in run_system: %s", e, exc_info=True)
        exit_code = 1
    finally:
        elapsed = time.monotonic() - start_time
        status = orchestrator.get_status()
        logger.info(
            "AIFred shutdown complete. Runtime: %.1fs, Scans: %d, Errors: %s",
            elapsed, status["scan_count"], status["error_counts"],
        )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
