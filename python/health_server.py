#!/usr/bin/env python3
"""Lightweight health/status HTTP server for Railway deployment.

Railway requires a listening port to consider a service healthy.
This runs alongside paper_trading.py in the same container and
exposes basic health, status, and price-proxy endpoints.

IMPORTANT: This must start FAST (< 5s). No heavy imports at module level.

Endpoints:
    GET  /            -> {"status": "running", "service": "aifred-orchestrator"}
    GET  /health      -> lightweight health checks (no heavy imports)
    GET  /status      -> current paper trading status (last 100 log lines)
    GET  /prices      -> proxy to Hyperliquid for live mid-prices
    GET  /trades      -> query trade history from trading.db
    GET  /decisions   -> recent orchestrator decisions from audit trail
    GET  /positions   -> current open positions from positions.db
    GET  /performance -> trading performance summary (P&L, win rate, etc.)
    POST /kill        -> activate kill switch
    POST /resume      -> deactivate kill switch
"""

import json
import math
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aiohttp import web, ClientSession, ClientTimeout

_START_TIME = time.monotonic()
# src.main logs to logs/trading.log, NOT paper_trading.log.
# Check both locations so the /status endpoint works regardless of entry point.
_APP_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_LOG_FILE_CANDIDATES = [
    _APP_DIR / "logs" / "trading.log",      # src.main orchestrator (primary)
    _APP_DIR / "paper_trading.log",           # standalone paper_trading.py (legacy)
]

# --- Database and data paths ---
_DATA_DIR = _APP_DIR / "data"
_TRADING_DB = _DATA_DIR / "trading.db"
_POSITIONS_DB = _DATA_DIR / "positions.db"
_PAPER_TRADES_DB = _DATA_DIR / "paper_trades.db"
_AUDIT_DIR = _DATA_DIR / "audit"
_KILL_FLAG = _DATA_DIR / ".kill_switch"

# Reference to orchestrator instance (set externally via set_orchestrator)
_orchestrator_ref: Optional[Any] = None


def set_orchestrator(orch: Any) -> None:
    """Allow the orchestrator to register itself so /decisions can read in-memory log."""
    global _orchestrator_ref
    _orchestrator_ref = orch


def _cors_headers() -> Dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


def _json_response(data: Any, status: int = 200) -> web.Response:
    """Return a JSON response with CORS headers."""
    return web.json_response(data, status=status, headers=_cors_headers())


def _query_db(db_path: Path, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Execute a read query and return rows as list of dicts."""
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def _find_log_file() -> Optional[Path]:
    """Return the first existing log file from the candidate list."""
    for candidate in _LOG_FILE_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def _uptime_str() -> str:
    secs = int(time.monotonic() - _START_TIME)
    hours, remainder = divmod(secs, 3600)
    mins, secs = divmod(remainder, 60)
    return f"{hours}h {mins}m {secs}s"


async def handle_root(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "running",
        "service": "aifred-orchestrator",
        "uptime": _uptime_str(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def handle_health(request: web.Request) -> web.Response:
    """Lightweight health check — verifies system is actually functional.

    Returns healthy=false (HTTP 503) if:
      - The heartbeat file is missing or older than 5 minutes (trading loop dead)
      - The trading process (src.main) is no longer running
    """
    checks = {}
    healthy = True
    reasons: list = []

    _HEARTBEAT_MAX_AGE = 300  # 5 minutes
    _STARTUP_GRACE_PERIOD = 300  # 5 minutes grace for initial startup

    # 1. Server is responding (obviously true if we're here)
    checks["server"] = "ok"

    # 2. Heartbeat file check — written by orchestrator after each scan cycle
    heartbeat_path = Path("/app/data/.heartbeat")
    try:
        if heartbeat_path.exists():
            with open(heartbeat_path, "r") as f:
                last_ts = float(f.read().strip())
            age_secs = time.time() - last_ts
            if age_secs < _HEARTBEAT_MAX_AGE:
                checks["heartbeat"] = f"ok (last cycle {int(age_secs)}s ago)"
            else:
                checks["heartbeat"] = f"stale ({int(age_secs)}s ago, limit {_HEARTBEAT_MAX_AGE}s)"
                healthy = False
                reasons.append(f"heartbeat stale ({int(age_secs)}s)")
        else:
            # Grace period: if we just started, the first scan hasn't completed yet
            uptime_secs = time.monotonic() - _START_TIME
            if uptime_secs < _STARTUP_GRACE_PERIOD:
                checks["heartbeat"] = f"waiting (startup grace, {int(uptime_secs)}s elapsed)"
            else:
                checks["heartbeat"] = "missing (no heartbeat file after grace period)"
                healthy = False
                reasons.append("heartbeat file missing")
    except Exception as e:
        checks["heartbeat"] = f"error: {e}"
        healthy = False
        reasons.append(f"heartbeat read error: {e}")

    # 3. Trading process alive check (look for src.main in /proc or via os)
    trading_alive = False
    try:
        import subprocess
        result = subprocess.run(
            ["pgrep", "-f", "src.main"],
            capture_output=True, timeout=3,
        )
        trading_alive = result.returncode == 0
    except FileNotFoundError:
        # pgrep not available (e.g. Alpine without procps) -- fall back to /proc scan
        try:
            for pid_dir in Path("/proc").iterdir():
                if not pid_dir.name.isdigit():
                    continue
                try:
                    cmdline = (pid_dir / "cmdline").read_text()
                    if "src.main" in cmdline:
                        trading_alive = True
                        break
                except (PermissionError, FileNotFoundError, OSError):
                    continue
        except Exception:
            # /proc not available (macOS, etc.) -- skip this check
            trading_alive = True  # assume ok if we can't check
            checks["trading_process"] = "skipped (no /proc or pgrep)"

    if trading_alive:
        checks["trading_process"] = "ok"
    elif "trading_process" not in checks:
        # Only fail if we're past the startup grace period
        uptime_secs = time.monotonic() - _START_TIME
        if uptime_secs < _STARTUP_GRACE_PERIOD:
            checks["trading_process"] = f"waiting (startup grace, {int(uptime_secs)}s elapsed)"
        else:
            checks["trading_process"] = "not found"
            healthy = False
            reasons.append("trading process not running")

    # 4. Log file freshness (secondary signal, non-blocking)
    try:
        log_file = _find_log_file()
        if log_file is not None:
            age_secs = time.time() - log_file.stat().st_mtime
            if age_secs < 300:
                checks["log_file"] = f"ok ({log_file.name}, last write {int(age_secs)}s ago)"
            else:
                checks["log_file"] = f"stale ({log_file.name}, {int(age_secs)}s ago)"
        else:
            checks["log_file"] = f"not yet created (checked: {[str(c) for c in _LOG_FILE_CANDIDATES]})"
    except Exception as e:
        checks["log_file"] = f"error: {e}"

    status_code = 200 if healthy else 503
    response = {
        "healthy": healthy,
        "uptime": _uptime_str(),
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if reasons:
        response["reasons"] = reasons

    return web.json_response(response, status=status_code)


async def handle_status(request: web.Request) -> web.Response:
    """Return last N lines of the paper trading log."""
    n = int(request.query.get("lines", "100"))
    n = min(n, 500)

    log_file = _find_log_file()
    if log_file is None:
        return web.json_response({
            "log_available": False,
            "message": (
                "No log file found yet - trading may still be starting. "
                f"Checked: {[str(c) for c in _LOG_FILE_CANDIDATES]}"
            ),
        })

    try:
        with open(log_file, "r") as f:
            all_lines = f.readlines()
        tail = all_lines[-n:]

        last_scan = None
        last_price_line = None
        open_positions = []
        for line in reversed(tail):
            if "=== Paper Scan" in line and last_scan is None:
                last_scan = line.strip()
            if "Prices:" in line and last_price_line is None:
                last_price_line = line.strip()
            if "PAPER OPEN:" in line:
                open_positions.append(line.strip())

        return web.json_response({
            "log_available": True,
            "total_lines": len(all_lines),
            "returned_lines": len(tail),
            "last_scan": last_scan,
            "last_prices": last_price_line,
            "recent_opens": open_positions[:5],
            "log_tail": [l.rstrip() for l in tail],
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_prices(request: web.Request) -> web.Response:
    """Proxy to Hyperliquid info API for live mid-prices."""
    try:
        async with ClientSession(timeout=ClientTimeout(total=10)) as session:
            async with session.post(
                "https://api.hyperliquid.xyz/info",
                json={"type": "allMids"},
                headers={"Content-Type": "application/json"},
            ) as resp:
                data = await resp.json()
                popular = ["BTC", "ETH", "SOL", "DOGE", "ARB", "OP", "AVAX", "MATIC", "LINK"]
                filtered = {}
                if isinstance(data, dict):
                    for coin in popular:
                        if coin in data:
                            filtered[coin] = data[coin]
                    return web.json_response({
                        "source": "hyperliquid",
                        "highlighted": filtered,
                        "all_count": len(data),
                        "all": data,
                    })
                return web.json_response({"raw": data})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=502)


async def handle_cors_preflight(request: web.Request) -> web.Response:
    """Handle CORS preflight OPTIONS requests."""
    return web.Response(status=204, headers=_cors_headers())


# --- NEW API ENDPOINTS ---


async def handle_trades(request: web.Request) -> web.Response:
    """Query trade history from trading.db.

    Query params:
        limit  - max rows to return (default 50, max 500)
        asset  - filter by asset symbol (e.g. BTC)
        status - filter by trade status (e.g. filled, closed)
    """
    try:
        limit = min(int(request.query.get("limit", "50")), 500)
        asset = request.query.get("asset")
        status = request.query.get("status")

        clauses: List[str] = []
        params: List[Any] = []

        if asset:
            clauses.append("asset = ?")
            params.append(asset.upper())
        if status:
            clauses.append("status = ?")
            params.append(status)

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM trades{where} ORDER BY entry_time DESC LIMIT ?"
        params.append(limit)

        rows = _query_db(_TRADING_DB, sql, tuple(params))
        return _json_response({"count": len(rows), "trades": rows})
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)


async def handle_decisions(request: web.Request) -> web.Response:
    """Return recent orchestrator decisions.

    Tries in-memory decision_log first (if orchestrator is registered),
    then falls back to reading JSONL audit trail files from data/audit/.

    Query params:
        limit - max entries to return (default 100, max 1000)
    """
    try:
        limit = min(int(request.query.get("limit", "100")), 1000)
        decisions: List[Dict[str, Any]] = []

        # 1. Try in-memory decision log from live orchestrator
        if _orchestrator_ref is not None:
            try:
                log = getattr(_orchestrator_ref, "_decision_log", None)
                if log:
                    decisions = list(log[-limit:])
                    return _json_response({
                        "source": "memory",
                        "count": len(decisions),
                        "decisions": decisions,
                    })
            except Exception:
                pass  # fall through to file-based

        # 2. Fall back to audit trail JSONL files
        if _AUDIT_DIR.exists():
            jsonl_files = sorted(_AUDIT_DIR.glob("*.jsonl"), reverse=True)
            for fpath in jsonl_files:
                if len(decisions) >= limit:
                    break
                try:
                    with open(fpath, "r") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                decisions.append(json.loads(line))
                except (json.JSONDecodeError, IOError):
                    continue

            # Most recent entries last in file, so reverse and trim
            decisions = decisions[-limit:]
            return _json_response({
                "source": "audit_files",
                "count": len(decisions),
                "decisions": decisions,
            })

        return _json_response({
            "source": "none",
            "count": 0,
            "decisions": [],
            "message": "No orchestrator connected and no audit files found.",
        })
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)


async def handle_positions(request: web.Request) -> web.Response:
    """Return current open positions from positions.db."""
    try:
        rows = _query_db(
            _POSITIONS_DB,
            "SELECT * FROM positions ORDER BY entry_time DESC",
        )
        return _json_response({"count": len(rows), "positions": rows})
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)


async def handle_performance(request: web.Request) -> web.Response:
    """Compute and return trading performance summary from trading.db.

    Returns: total P&L, win rate, trade count, Sharpe ratio, max drawdown.
    """
    try:
        if not _TRADING_DB.exists():
            return _json_response({
                "error": "trading.db not found",
                "message": "No trade history available yet.",
            }, status=404)

        conn = sqlite3.connect(str(_TRADING_DB))
        conn.row_factory = sqlite3.Row
        try:
            # Fetch all closed trades with P&L
            rows = conn.execute(
                "SELECT pnl, entry_time, exit_time FROM trades "
                "WHERE pnl IS NOT NULL ORDER BY entry_time ASC"
            ).fetchall()

            total_trades = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            open_trades = conn.execute(
                "SELECT COUNT(*) FROM trades WHERE status IN ('open', 'pending', 'filled')"
            ).fetchone()[0]
        finally:
            conn.close()

        pnls = [float(r["pnl"]) for r in rows if r["pnl"] is not None]
        closed_count = len(pnls)

        if closed_count == 0:
            return _json_response({
                "total_trades": total_trades,
                "closed_trades": 0,
                "open_trades": open_trades,
                "total_pnl": 0.0,
                "win_rate": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "avg_pnl": 0.0,
                "best_trade": 0.0,
                "worst_trade": 0.0,
            })

        wins = sum(1 for p in pnls if p > 0)
        total_pnl = sum(pnls)
        avg_pnl = total_pnl / closed_count
        win_rate = (wins / closed_count) * 100.0

        # Sharpe ratio (annualized assuming daily returns, 252 trading days)
        if closed_count > 1:
            mean_ret = sum(pnls) / closed_count
            variance = sum((p - mean_ret) ** 2 for p in pnls) / (closed_count - 1)
            std_ret = math.sqrt(variance) if variance > 0 else 0.0
            sharpe = (mean_ret / std_ret * math.sqrt(252)) if std_ret > 0 else 0.0
        else:
            sharpe = 0.0

        # Max drawdown from cumulative P&L curve
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for p in pnls:
            cumulative += p
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd

        return _json_response({
            "total_trades": total_trades,
            "closed_trades": closed_count,
            "open_trades": open_trades,
            "total_pnl": round(total_pnl, 4),
            "win_rate": round(win_rate, 2),
            "avg_pnl": round(avg_pnl, 4),
            "best_trade": round(max(pnls), 4),
            "worst_trade": round(min(pnls), 4),
            "sharpe_ratio": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4),
        })
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)


async def handle_kill(request: web.Request) -> web.Response:
    """Activate kill switch by writing a flag file.

    The orchestrator should check for this file each cycle and halt trading.
    """
    try:
        reason = "API kill switch activated"
        try:
            body = await request.json()
            reason = body.get("reason", reason)
        except Exception:
            pass

        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "killed": True,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _KILL_FLAG.write_text(json.dumps(payload))

        return _json_response({
            "status": "killed",
            "message": "Kill switch activated. Trading halted.",
            "reason": reason,
            "flag_file": str(_KILL_FLAG),
        })
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)


async def handle_resume(request: web.Request) -> web.Response:
    """Deactivate kill switch by removing the flag file."""
    try:
        if _KILL_FLAG.exists():
            _KILL_FLAG.unlink()
            return _json_response({
                "status": "resumed",
                "message": "Kill switch deactivated. Trading may resume.",
            })
        else:
            return _json_response({
                "status": "already_running",
                "message": "Kill switch was not active.",
            })
    except Exception as e:
        return _json_response({"error": str(e)}, status=500)


def create_app() -> web.Application:
    app = web.Application()

    # Existing endpoints
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/status", handle_status)
    app.router.add_get("/prices", handle_prices)

    # New API endpoints
    app.router.add_get("/trades", handle_trades)
    app.router.add_get("/decisions", handle_decisions)
    app.router.add_get("/positions", handle_positions)
    app.router.add_get("/performance", handle_performance)
    app.router.add_post("/kill", handle_kill)
    app.router.add_post("/resume", handle_resume)

    # CORS preflight for POST endpoints
    app.router.add_route("OPTIONS", "/kill", handle_cors_preflight)
    app.router.add_route("OPTIONS", "/resume", handle_cors_preflight)

    return app


def main():
    port = int(os.environ.get("PORT", "8080"))
    print(f"[health_server] Starting on 0.0.0.0:{port}")
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=port, print=None)


if __name__ == "__main__":
    main()
