#!/usr/bin/env python3
"""Lightweight health/status HTTP server for Railway deployment.

Railway requires a listening port to consider a service healthy.
This runs alongside paper_trading.py in the same container and
exposes basic health, status, and price-proxy endpoints.

IMPORTANT: This must start FAST (< 5s). No heavy imports at module level.

Endpoints:
    GET /         -> {"status": "running", "service": "aifred-orchestrator"}
    GET /health   -> lightweight health checks (no heavy imports)
    GET /status   -> current paper trading status (last 100 log lines)
    GET /prices   -> proxy to Hyperliquid for live mid-prices
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web, ClientSession, ClientTimeout

_START_TIME = time.monotonic()
_LOG_FILE = Path(os.path.dirname(os.path.abspath(__file__))) / "paper_trading.log"


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
    """Lightweight health check — no heavy imports, just prove the server is alive."""
    checks = {}

    # 1. Server is responding (obviously true if we're here)
    checks["server"] = "ok"

    # 2. Check log file freshness (paper_trading.py writing to it)
    try:
        if _LOG_FILE.exists():
            age_secs = time.time() - _LOG_FILE.stat().st_mtime
            if age_secs < 300:
                checks["trading_loop"] = f"ok (last write {int(age_secs)}s ago)"
            else:
                checks["trading_loop"] = f"stale ({int(age_secs)}s ago)"
        else:
            checks["trading_loop"] = "starting"
    except Exception as e:
        checks["trading_loop"] = f"error: {e}"

    # 3. Quick network check — can we reach Hyperliquid?
    try:
        async with ClientSession(timeout=ClientTimeout(total=5)) as session:
            async with session.post(
                "https://api.hyperliquid.xyz/info",
                json={"type": "allMids"},
            ) as resp:
                if resp.status == 200:
                    checks["hyperliquid"] = "ok"
                else:
                    checks["hyperliquid"] = f"status {resp.status}"
    except Exception:
        checks["hyperliquid"] = "unreachable"

    return web.json_response({
        "healthy": True,  # Always return healthy if server responds
        "uptime": _uptime_str(),
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, status=200)


async def handle_status(request: web.Request) -> web.Response:
    """Return last N lines of the paper trading log."""
    n = int(request.query.get("lines", "100"))
    n = min(n, 500)

    if not _LOG_FILE.exists():
        return web.json_response({
            "log_available": False,
            "message": "paper_trading.log not found yet - trading may still be starting.",
        })

    try:
        with open(_LOG_FILE, "r") as f:
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


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/status", handle_status)
    app.router.add_get("/prices", handle_prices)
    return app


def main():
    port = int(os.environ.get("PORT", "8080"))
    print(f"[health_server] Starting on 0.0.0.0:{port}")
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=port, print=None)


if __name__ == "__main__":
    main()
