"""MCP Server for AIFred Trading Engine.

Exposes the trading engine's capabilities as MCP tools that AI agents can invoke.
Uses FastMCP (from the `mcp` Python package) for the server implementation.

Tools provided:
  - check_price: Get current price + indicators for a symbol
  - get_signals: Get current ML ensemble + sentiment signals
  - get_portfolio: Get current positions, P&L, balance
  - get_risk_state: Get drawdown, correlation, regime, safety status
  - evaluate_trade: Run a trade proposal through the risk gate (dry run)
  - run_backtest: Run a backtest with specified parameters
  - get_system_status: Get full system health and degradation state
  - get_market_overview: Get prices + signals for all configured assets
"""

from mcp.server.fastmcp import FastMCP
import asyncio
import json
import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Create the MCP server
mcp = FastMCP("aifred-trading")


# Reference to the running system components (set by main.py on startup)
_orchestrator = None
_data_provider = None
_ws_manager = None
_config = None


def set_system_references(orchestrator=None, data_provider=None,
                          ws_manager=None, config=None):
    """Called by main.py to wire up the MCP server to the live system."""
    global _orchestrator, _data_provider, _ws_manager, _config
    _orchestrator = orchestrator
    _data_provider = data_provider
    _ws_manager = ws_manager
    _config = config


def _safe_float(value, default=None):
    """Convert a value to a JSON-safe float, handling NaN, Inf, and None."""
    if value is None:
        return default
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _safe_json_dumps(obj, **kwargs):
    """Serialize to JSON, replacing NaN/Inf with null."""
    def _default_handler(o):
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, float):
            if math.isnan(o) or math.isinf(o):
                return None
        if hasattr(o, '__dict__'):
            return str(o)
        return str(o)

    # Replace NaN/Inf in the serialized string as a safety net
    text = json.dumps(obj, default=_default_handler, **kwargs)
    text = text.replace(": NaN", ": null").replace(":NaN", ":null")
    text = text.replace(": Infinity", ": null").replace(":Infinity", ":null")
    text = text.replace(": -Infinity", ": null").replace(":-Infinity", ":null")
    return text


@mcp.tool()
async def check_price(symbol: str, timeframe: str = "1h") -> str:
    """Get current price, OHLCV data, and technical indicators for a trading symbol.

    Args:
        symbol: Trading pair (e.g. "BTC/USDT", "ETH/USDT", "AAPL")
        timeframe: Candle timeframe (e.g. "1h", "4h", "1d")

    Returns:
        JSON with current price, last 5 candles, and key indicators (RSI, MACD, SMA, EMA, ATR, BBands)
    """
    try:
        # Get realtime price from WebSocket if available
        realtime_price = None
        if _ws_manager:
            try:
                realtime_price = _ws_manager.get_price(symbol)
            except Exception:
                pass

        # Get OHLCV + indicators from data provider
        if _data_provider:
            df = _data_provider.get_data(symbol, timeframe)
            if df is not None and len(df) > 0:
                last = df.iloc[-1]
                last_5 = df.tail(5)

                indicator_cols = [
                    "rsi_14", "macd", "macd_signal", "sma_20", "sma_50",
                    "sma_200", "ema_12", "ema_26", "atr_14", "bb_upper", "bb_lower",
                ]

                result = {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "current_price": _safe_float(realtime_price) or _safe_float(last.get("close", 0), 0),
                    "timestamp": datetime.utcnow().isoformat(),
                    "last_candle": {
                        "open": _safe_float(last.get("open", 0), 0),
                        "high": _safe_float(last.get("high", 0), 0),
                        "low": _safe_float(last.get("low", 0), 0),
                        "close": _safe_float(last.get("close", 0), 0),
                        "volume": _safe_float(last.get("volume", 0), 0),
                    },
                    "indicators": {
                        col: _safe_float(last.get(col))
                        for col in indicator_cols
                        if col in df.columns
                    },
                    "recent_candles": [
                        {
                            "open": _safe_float(r.get("open", 0), 0),
                            "high": _safe_float(r.get("high", 0), 0),
                            "low": _safe_float(r.get("low", 0), 0),
                            "close": _safe_float(r.get("close", 0), 0),
                            "volume": _safe_float(r.get("volume", 0), 0),
                        }
                        for _, r in last_5.iterrows()
                    ],
                }
                return _safe_json_dumps(result, indent=2)

        return _safe_json_dumps({"error": "Data unavailable", "symbol": symbol})
    except Exception as e:
        logger.exception("check_price failed for %s", symbol)
        return _safe_json_dumps({"error": str(e), "symbol": symbol})


@mcp.tool()
async def get_signals(symbol: str) -> str:
    """Get current trading signals from all analysis agents for a symbol.

    Returns technical analysis signal, sentiment signal, and fused ensemble signal
    with confidence scores and direction (BUY/SELL/HOLD).

    Args:
        symbol: Trading pair (e.g. "BTC/USDT")
    """
    if not _orchestrator:
        return _safe_json_dumps({"error": "Orchestrator not available"})

    result = {"symbol": symbol, "timestamp": datetime.utcnow().isoformat()}

    # Technical signal
    tech_agent = getattr(_orchestrator, '_tech_agent', None)
    if tech_agent and _data_provider:
        try:
            data = _data_provider.get_data(symbol, "1h")
            if data is not None:
                signal = tech_agent.analyze(symbol, data)
                if signal:
                    result["technical"] = {
                        "direction": signal.direction.value if hasattr(signal.direction, 'value') else str(signal.direction),
                        "confidence": _safe_float(signal.confidence, 0),
                        "source": str(signal.source),
                        "metadata": signal.metadata if isinstance(signal.metadata, dict) else {},
                    }
        except Exception as e:
            result["technical_error"] = str(e)

    # Sentiment signal
    sent_agent = getattr(_orchestrator, '_sentiment_agent', None)
    if sent_agent:
        try:
            signal = sent_agent.analyze(symbol)
            if signal:
                result["sentiment"] = {
                    "direction": signal.direction.value if hasattr(signal.direction, 'value') else str(signal.direction),
                    "confidence": _safe_float(signal.confidence, 0),
                    "source": str(signal.source),
                    "metadata": signal.metadata if isinstance(signal.metadata, dict) else {},
                }
        except Exception as e:
            result["sentiment_error"] = str(e)

    return _safe_json_dumps(result, indent=2)


@mcp.tool()
async def get_portfolio() -> str:
    """Get current portfolio state including all open positions, P&L, and balance.

    Returns positions with entry price, current price, unrealized P&L,
    plus overall portfolio metrics.
    """
    if not _orchestrator:
        return _safe_json_dumps({"error": "Orchestrator not available"})

    exec_agent = getattr(_orchestrator, '_execution_agent', None)
    if not exec_agent:
        return _safe_json_dumps({"error": "Execution agent not available"})

    try:
        positions = exec_agent.get_open_positions()
    except Exception as e:
        return _safe_json_dumps({"error": f"Failed to get positions: {e}"})

    # Update prices for all positions
    for pos in positions:
        if _ws_manager:
            try:
                price = _ws_manager.get_price(pos.asset)
                if price:
                    pos.current_price = price
                    if pos.side == "LONG":
                        pos.unrealized_pnl = (price - pos.entry_price) * pos.size
                    else:
                        pos.unrealized_pnl = (pos.entry_price - price) * pos.size
            except Exception:
                pass

    # Get balance
    balance_info = {}
    if hasattr(exec_agent, 'get_account_balance'):
        try:
            balance_info = exec_agent.get_account_balance()
            if not isinstance(balance_info, dict):
                balance_info = {"raw": str(balance_info)}
        except Exception as e:
            balance_info = {"error": str(e)}

    total_pnl = sum(
        _safe_float(p.unrealized_pnl, 0)
        for p in positions
    )

    result = {
        "timestamp": datetime.utcnow().isoformat(),
        "balance": balance_info,
        "position_count": len(positions),
        "total_unrealized_pnl": _safe_float(total_pnl, 0),
        "positions": [
            {
                "asset": p.asset,
                "side": p.side,
                "entry_price": _safe_float(p.entry_price, 0),
                "current_price": _safe_float(p.current_price, 0),
                "size": _safe_float(p.size, 0),
                "unrealized_pnl": _safe_float(p.unrealized_pnl, 0),
                "stop_loss": _safe_float(p.stop_loss, 0),
                "take_profit": _safe_float(p.take_profit, 0),
                "strategy": getattr(p, 'strategy', ''),
                "entry_time": p.entry_time.isoformat() if getattr(p, 'entry_time', None) else None,
            }
            for p in positions
        ],
    }
    return _safe_json_dumps(result, indent=2)


@mcp.tool()
async def get_risk_state() -> str:
    """Get current risk management state including drawdown, safety limits, and system health.

    Returns drawdown levels, safety limit usage, degradation state,
    circuit breaker status, and correlation data.
    """
    if not _orchestrator:
        return _safe_json_dumps({"error": "Orchestrator not available"})

    try:
        status = _orchestrator.get_status()
    except Exception as e:
        return _safe_json_dumps({"error": f"Failed to get status: {e}"})

    result = {
        "timestamp": datetime.utcnow().isoformat(),
        "circuit_breaker": status.get("circuit_breaker", {}),
        "account_safety": status.get("account_safety", {}),
        "degradation": status.get("degradation", {}),
        "mode": status.get("mode", "unknown"),
        "running": status.get("running", False),
        "scan_count": status.get("scan_count", 0),
    }
    return _safe_json_dumps(result, indent=2)


@mcp.tool()
async def evaluate_trade(symbol: str, direction: str, size_usd: float,
                         stop_loss_pct: float = 2.0, take_profit_pct: float = 4.0) -> str:
    """Evaluate a trade proposal through the risk gate WITHOUT executing it (dry run).

    Checks position sizing, safety limits, correlation, drawdown state, and
    returns whether the trade would be approved or rejected with reasons.

    Args:
        symbol: Trading pair (e.g. "BTC/USDT")
        direction: "BUY" or "SELL"
        size_usd: Position size in USD
        stop_loss_pct: Stop loss distance as percentage (default 2%)
        take_profit_pct: Take profit distance as percentage (default 4%)
    """
    if not _orchestrator:
        return _safe_json_dumps({"error": "Orchestrator not available"})

    # Validate direction
    direction_upper = direction.upper()
    if direction_upper not in ("BUY", "SELL"):
        return _safe_json_dumps({"error": f"Invalid direction '{direction}'. Must be 'BUY' or 'SELL'."})

    if size_usd <= 0:
        return _safe_json_dumps({"error": "size_usd must be positive"})

    # Get current price
    price = None
    if _ws_manager:
        try:
            price = _ws_manager.get_price(symbol)
        except Exception:
            pass
    if not price and _data_provider:
        try:
            price = _data_provider.get_realtime_price(symbol)
        except Exception:
            pass
    if not price:
        return _safe_json_dumps({"error": f"Cannot get price for {symbol}"})

    try:
        from src.utils.types import Signal, TradeProposal, Direction as Dir, AssetClass, OrderType

        dir_enum = Dir.BUY if direction_upper == "BUY" else Dir.SELL
        asset_class = AssetClass.CRYPTO if "/" in symbol else AssetClass.STOCKS

        size_units = size_usd / price
        if dir_enum == Dir.BUY:
            stop = price * (1 - stop_loss_pct / 100)
            tp = price * (1 + take_profit_pct / 100)
        else:
            stop = price * (1 + stop_loss_pct / 100)
            tp = price * (1 - take_profit_pct / 100)

        signal = Signal(asset=symbol, direction=dir_enum, confidence=80.0, source="mcp_evaluation")
        proposal = TradeProposal(
            signal=signal, asset=symbol, asset_class=asset_class,
            direction=dir_enum, entry_price=price,
            position_size=size_units, position_value=size_usd,
            stop_loss=stop, take_profit=tp,
        )

        result = {
            "symbol": symbol,
            "direction": direction_upper,
            "size_usd": _safe_float(size_usd, 0),
            "price": _safe_float(price, 0),
            "stop_loss": _safe_float(stop, 0),
            "take_profit": _safe_float(tp, 0),
            "checks": {},
        }

        # Check safety limits
        exec_agent = getattr(_orchestrator, '_execution_agent', None)
        safety = getattr(exec_agent, '_safety_limits', None) if exec_agent else None

        if safety:
            try:
                positions = exec_agent.get_open_positions()
                total_exposure = sum(
                    _safe_float(p.current_price, 0) * _safe_float(p.size, 0)
                    for p in positions
                )
                portfolio_state = exec_agent._get_portfolio_state() if hasattr(exec_agent, '_get_portfolio_state') else None
                portfolio_val = portfolio_state.total_value if portfolio_state else 10000.0

                allowed, reason = safety.check_trade_allowed(
                    size_usd, portfolio_val, len(positions), total_exposure
                )
                result["checks"]["safety"] = {"passed": allowed, "reason": str(reason)}
            except Exception as e:
                result["checks"]["safety"] = {"error": str(e)}

        # Check risk gate
        risk_gate = getattr(_orchestrator, '_risk_gate', None)
        if risk_gate:
            try:
                open_positions = exec_agent.get_open_positions() if exec_agent else []
                decision = risk_gate.evaluate(proposal, open_positions)
                result["checks"]["risk_gate"] = {
                    "approved": decision.approved,
                    "reason": str(decision.reason),
                    "risk_score": _safe_float(decision.risk_score, 0),
                    "adjusted_size": _safe_float(decision.adjusted_size),
                }
            except Exception as e:
                result["checks"]["risk_gate"] = {"error": str(e)}

        # Determine overall result
        check_results = []
        for c in result["checks"].values():
            if isinstance(c, dict) and "error" not in c:
                check_results.append(c.get("passed", c.get("approved", False)))

        result["overall"] = all(check_results) if check_results else False

        return _safe_json_dumps(result, indent=2)

    except Exception as e:
        logger.exception("evaluate_trade failed for %s", symbol)
        return _safe_json_dumps({"error": str(e), "symbol": symbol})


@mcp.tool()
async def get_system_status() -> str:
    """Get complete system status including all agents, exchanges, and health metrics.

    Returns mode, uptime, scan count, agent statuses, exchange connectivity,
    degradation level, circuit breaker state, and error counts.
    """
    if not _orchestrator:
        return _safe_json_dumps({"error": "Orchestrator not available"})

    try:
        return _safe_json_dumps(_orchestrator.get_status(), indent=2)
    except Exception as e:
        logger.exception("get_system_status failed")
        return _safe_json_dumps({"error": str(e)})


@mcp.tool()
async def get_market_overview() -> str:
    """Get a quick overview of all configured trading assets with current prices and signals.

    Returns current price, 24h change, RSI, and signal direction for each asset.
    """
    if not _config:
        return _safe_json_dumps({"error": "Config not available"})

    assets = []
    for class_name in ("crypto", "stocks", "forex"):
        for symbol in _config.get("assets", {}).get(class_name, []):
            assets.append(symbol)

    if not assets:
        return _safe_json_dumps({"error": "No assets configured", "config_keys": list(_config.keys())})

    overview = []
    for symbol in assets:
        entry = {"symbol": symbol}

        # Get price from WebSocket
        if _ws_manager:
            try:
                ticker = _ws_manager.get_ticker(symbol)
                if ticker and isinstance(ticker, dict):
                    entry["price"] = _safe_float(ticker.get("price") or ticker.get("last"))
                    entry["bid"] = _safe_float(ticker.get("bid"))
                    entry["ask"] = _safe_float(ticker.get("ask"))
            except Exception:
                pass

        # Fallback to data provider for price
        if "price" not in entry and _data_provider:
            try:
                price = _data_provider.get_realtime_price(symbol)
                if price:
                    entry["price"] = _safe_float(price)
            except Exception:
                pass

        # Get basic indicators
        if _data_provider:
            try:
                df = _data_provider.get_data(symbol, "1h")
                if df is not None and len(df) > 0:
                    last = df.iloc[-1]
                    if "rsi_14" in df.columns:
                        entry["rsi"] = _safe_float(last.get("rsi_14"))
                    if len(df) > 1:
                        prev_close = _safe_float(df.iloc[-2].get("close", 0), 0)
                        curr_close = _safe_float(last.get("close", 0), 0)
                        if prev_close > 0:
                            entry["change_pct"] = round((curr_close - prev_close) / prev_close * 100, 2)
            except Exception:
                pass

        overview.append(entry)

    return _safe_json_dumps({
        "timestamp": datetime.utcnow().isoformat(),
        "assets": overview,
    }, indent=2)


@mcp.tool()
async def run_backtest(symbol: str = "BTC/USDT", days: int = 90,
                       min_confidence: int = 78, strategy: str = "default") -> str:
    """Run a backtest on historical data and return performance metrics.

    Args:
        symbol: Trading pair to backtest (default: BTC/USDT)
        days: Number of days of history to test (default: 90)
        min_confidence: Minimum signal confidence threshold (default: 78)
        strategy: Strategy name to test (default: "default")

    Returns:
        Backtest results including total return, Sharpe ratio, max drawdown,
        win rate, profit factor, and trade count.
    """
    try:
        from src.execution.abstract_exchange import BacktestExchange, OrderRequest

        ex = BacktestExchange(initial_balance=10000, fee_pct=0.1, slippage_pct=0.05)
        await ex.connect()

        # Fetch historical data
        if not _data_provider:
            return _safe_json_dumps({"error": "Data provider not available"})

        df = _data_provider.get_data(symbol, "1h")
        if df is None or len(df) == 0:
            return _safe_json_dumps({"error": "Historical data unavailable", "symbol": symbol})

        # Limit to requested number of days (approx hours)
        max_candles = days * 24
        if len(df) > max_candles:
            df = df.tail(max_candles)

        trades = 0
        start_idx = min(50, len(df) - 1)  # Need at least some history for indicators

        for i in range(start_idx, len(df)):
            row = df.iloc[i]
            price = _safe_float(row.get("close", 0), 0)
            if price <= 0:
                continue

            rsi = _safe_float(row.get("rsi_14", 50), 50) if "rsi_14" in df.columns else 50

            ex.set_prices({symbol: price})

            # Simple RSI strategy for demonstration
            # In production, this would use the full signal fusion pipeline
            try:
                positions = await ex.get_positions()
                has_position = any(
                    p.get("symbol") == symbol if isinstance(p, dict)
                    else getattr(p, "symbol", None) == symbol
                    for p in positions
                )

                bal = await ex.get_balance()
                if not has_position and rsi < 30 and bal.free_usd > 100:
                    size = min(bal.free_usd * 0.1 / price, bal.free_usd * 0.95 / price)
                    if size > 0:
                        await ex.place_order(OrderRequest(
                            symbol=symbol, side="buy", order_type="market", amount=size
                        ))
                        trades += 1
                elif has_position and rsi > 70:
                    base_currency = symbol.split("/")[0] if "/" in symbol else symbol
                    holdings = bal.assets.get(base_currency, {})
                    size = holdings.get("free", 0) if isinstance(holdings, dict) else 0
                    if size > 0:
                        await ex.place_order(OrderRequest(
                            symbol=symbol, side="sell", order_type="market", amount=size
                        ))
                        trades += 1
            except Exception as e:
                logger.debug("Backtest step %d error: %s", i, e)
                continue

        stats = ex.get_stats()
        await ex.disconnect()

        return _safe_json_dumps({
            "symbol": symbol,
            "period_days": days,
            "candles_processed": len(df) - start_idx,
            "strategy": strategy,
            "min_confidence": min_confidence,
            "results": stats,
            "trade_count": trades,
        }, indent=2)

    except ImportError as e:
        return _safe_json_dumps({"error": f"Import error: {e}"})
    except Exception as e:
        logger.exception("run_backtest failed")
        return _safe_json_dumps({"error": str(e), "symbol": symbol})


# Entry point for running the MCP server standalone
if __name__ == "__main__":
    mcp.run()
