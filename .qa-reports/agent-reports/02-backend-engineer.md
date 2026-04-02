# Backend Engineer Review Report

**Reviewer:** Backend Engineer (Agent 02)
**Date:** 2026-04-01
**Scope:** Python backend, Next.js API layer, Railway deployment, security

---

## 1. Orchestrator (`python/src/orchestrator.py`)

### Signal Fusion Logic — WARN

The fusion logic at line 1227 correctly implements 60% tech / 40% sentiment weighting with degradation-adjusted overrides and on-chain re-normalization. Agreement bonus (1.35x) and disagreement penalty (0.50x) are applied correctly. However:

- **BUG — Config key mismatch for `max_daily_trades`:** The YAML config uses `orchestrator.max_daily_trades` (default.yaml:30), but `CircuitBreaker.__init__` at line 75 reads `orch_cfg.get("max_trades_per_day", 20)` and `Orchestrator.__init__` at line 201 also reads `orch_cfg.get("max_trades_per_day", 20)`. This means the config value of 20 (default) or 8 (live) is **never read** — the code always uses the hardcoded fallback of 20. The live.yaml override to 8 trades is silently ignored.
  - **File:** `python/src/orchestrator.py:75` and `:201`
  - **Fix:** Change `"max_trades_per_day"` to `"max_daily_trades"` in both locations to match the YAML key.

- **BUG — Config key mismatch for `max_daily_loss_pct`:** The YAML config uses `orchestrator.max_daily_loss_pct` (default.yaml:31), but `CircuitBreaker.__init__` at line 76 reads from `risk_cfg.get("max_daily_drawdown_pct", 5.0)`. The `risk` section has `drawdown.daily_limit_pct`, not `max_daily_drawdown_pct`. This means the daily loss circuit breaker always uses the fallback of 5.0%, ignoring any config override.
  - **File:** `python/src/orchestrator.py:76`
  - **Fix:** Read from the correct config path or unify the key names across orchestrator and risk config.

- **BUG — Config key mismatch for `scan_interval`:** The YAML config uses `system.scan_interval` (default.yaml:7), but `Orchestrator.__init__` at line 195 reads `orch_cfg.get("scan_interval_seconds", 60)` from the `orchestrator` section. Meanwhile `main.py:198` writes to `config["orchestrator"]["scan_interval_seconds"]` only when CLI args are provided. The YAML default of 60 works by coincidence (same as the fallback) but will break if someone changes only `system.scan_interval` in the YAML.
  - **File:** `python/src/orchestrator.py:195`
  - **Fix:** Decide on one canonical config path and use it consistently.

### Circuit Breaker / Degradation Manager — PASS

- Circuit breaker correctly tracks daily trades, daily P&L, and consecutive failures.
- Cooldown timers auto-reset. Trip reasons are well-logged.
- `DegradationManager` implements a clean 5-level degradation model (FULL -> SAFE_MODE) with per-subsystem health tracking, configurable failure thresholds, and backoff recovery.
- File-based kill switch (line 650-664) is a good Railway-friendly pattern.

### Data Provider Integration — PASS

- Data provider and news provider use callback injection (`set_data_provider`, `set_news_provider`), cleanly decoupled.
- WebSocket manager and reconciler are also injectable via setters.
- Null checks on all providers prevent crashes when data is unavailable.

### Error Handling and Recovery — PASS

- Each agent is initialized independently in `initialize_agents()` (line 287-446). One failure does not block others.
- Every `_process_asset` call is wrapped in try/except with error counting.
- Degradation report_failure/report_success calls are correctly placed in all signal-gathering methods.
- Graceful shutdown: `finally` block stops position monitor and closes on-chain aggregator sessions.

---

## 2. Execution Engine (`python/src/execution/`)

### `execution_engine.py` — PASS

- Clean separation: paper mode uses `PaperTrader`, live mode initializes `ExchangeConnector` instances.
- Hard safety limits (`AccountSafety`) are checked **first** before any execution (line 143-160).
- Pre-trade balance check in live mode with 5% fee buffer is correct.
- Order state machine registry and Dynamic Kelly calibration are properly initialized.
- Position reconciliation on startup correctly restores paper positions.

### `paper_trader.py` — PASS

- Realistic slippage model: `estimate_slippage_bps` scales by asset type, ATR volatility ratio, and order size vs. daily volume.
- Noise jitter (+/-20%) adds randomness without being excessive.
- Balance tracking correctly handles buy/sell with fee deductions.
- SQLite persistence for trade history with proper schema creation.
- Market context (ATR, volume) is injectable via `set_market_context()`.

### `exchange_connector.py` — PASS

- ccxt wrapper with both sync and async modes.
- Rate limiting enabled via `enableRateLimit: True`.
- Consecutive failure tracking with auto-reconnect after `_max_failures` (5).
- Sandbox mode properly configurable.
- Good error handling pattern: `_handle_failure` increments counter, `_handle_success` resets.

### `hyperliquid_connector.py` — PASS

- Clean REST-only implementation (no SDK dependency).
- EIP-712 action hash implementation for order signing.
- Price rounding to 5 significant figures matches HL requirements.
- Size rounding per asset's `szDecimals` from metadata.
- Private key is stored in-memory only; agent wallet pattern means user's main key never touches the server.
- Session lifecycle properly managed (`connect`/`disconnect`).

**Minor concern:** The `_action_hash` function uses SHA-256 over JSON + nonce, which mirrors the SDK. If Hyperliquid ever changes their hashing scheme, this custom implementation must be updated manually. Consider adding a version assertion against the exchange metadata.

---

## 3. API Routes (`app/api/trading/`)

### Authentication Middleware — PASS

- `middleware.ts` protects all `/api/trading/*` routes with JWT token verification via `next-auth`.
- Fail-closed: if `NEXTAUTH_SECRET` is missing, all protected requests return 500 (line 35-39).
- Auth uses bcrypt password hashing against `AUTH_PASSWORD_HASH` env var.
- 24-hour JWT session expiry is reasonable.
- Dashboard pages redirect to `/login` when unauthenticated.

### Rate Limiting — PASS

- In-memory per-process rate limiting with three tiers:
  - `/execute` POST: 1 per 10 seconds
  - `/autoscan` POST: 1 per 60 seconds
  - General API: 10 per 60 seconds
- Appropriate for single-user deployment. Would need Redis/external store for multi-instance.

### Error Handling — PASS

- All API routes wrap logic in try/catch with meaningful error responses.
- Request body size limits enforced (10KB for execute, 50KB for autoscan, 1KB for controls/kill-switch).
- JSON parse errors caught and returned as 400.

### Data Validation — WARN

- **`execute/route.ts`** (line 17-28): The `ExecuteTradeParams` are assigned from the body without type validation. Invalid types (e.g., `quantity: "abc"`) would pass through to `executeTrade` and only fail at runtime.
  - **Fix:** Add Zod or manual validation for required fields (symbol, side, quantity, orderType).

- **`autoscan/route.ts`** (line 469-485): Similar — `mode` is typed as `"paper" | "live"` but not validated at runtime. A request with `mode: "yolo"` would pass through.
  - **Fix:** Validate `mode` is one of the allowed values before proceeding.

- **`controls/route.ts`** (line 113): `action` is typed but only validated by the switch/default branch, which is acceptable.

### Hardcoded Wallet Address — WARN

- **`hyperliquid/route.ts:8`** contains a hardcoded fallback address: `"0xbec07623d9c8209E7F80dC7350b3aA0ECBdCb510"`. If env vars are not set, the API returns balance/position data for this specific address. This could leak information about a wallet the developer does not control, or worse, expose the developer's own wallet info to any authenticated user.
  - **Fix:** Return an error response when `HYPERLIQUID_ADDRESS` is not configured, instead of falling back to a hardcoded address.

---

## 4. Configuration (`python/src/config/`)

### `default.yaml` and `live.yaml` Consistency — WARN

| Issue | Details |
|-------|---------|
| **`max_daily_trades` never read** | Config key is `max_daily_trades`, code reads `max_trades_per_day` (see Section 1) |
| **`max_daily_loss_pct` mismatch** | Config key is `orchestrator.max_daily_loss_pct`, code reads `risk.max_daily_drawdown_pct` (see Section 1) |
| **`scan_interval` vs `scan_interval_seconds`** | `system.scan_interval` in YAML vs `orchestrator.scan_interval_seconds` in code (see Section 1) |
| **`live.yaml` `risk.max_position_pct: 10.0`** | This is 10% per position, but `safety.max_position_pct: 5.0` hard-caps it. The 10% value in `risk` is dead config — `AccountSafety` will block any position over 5%. Not a bug (safety wins), but misleading. |
| **`live.yaml` `execution.mode: "live"`** | This field exists but `default.yaml` does not have an `execution.mode` key; the default is derived from `system.mode`. Code at `execution_engine.py:34` reads `execution.mode`, meaning the live overlay works, but paper mode reads from a key that does not exist in default.yaml (falls back to `"paper"` correctly by coincidence). |

### Config Loading (`config.py`) — PASS

- Environment variable resolution with `${VAR}` syntax is correct.
- Deep merge correctly lets overlay values win.
- `.env` file loading via `python-dotenv`.

---

## 5. Railway Deployment

### `Dockerfile.railway` — PASS

- Python 3.12-slim base, minimal apt deps (only curl for healthcheck).
- PyTorch CPU-only via `--index-url` saves ~1.8GB.
- `PYTHONUNBUFFERED=1` ensures log output is not buffered.
- `chmod 777` on data/logs dirs ensures writability.
- Health check: 30s interval, 60s start period, 5 retries — appropriate for ML model loading.

### `start.sh` — PASS

- Health server starts first (fast startup for Railway), then trading engine.
- `wait -n` correctly waits for either process; if one dies, both are killed.
- DRY_RUN mode supported via env var.
- Good diagnostic logging (directory listing) for debugging deploy issues.

### `requirements-railway.txt` — WARN

- **Duplicate entry:** `aiohttp>=3.9.0` appears twice (lines 28 and 49). Not harmful but untidy.
- **No upper bounds on any dependency.** A breaking release of `ccxt`, `torch`, or `transformers` could break the build silently. Consider pinning major versions (e.g., `ccxt>=4.0.0,<5.0`).
- **Missing:** No `eth-account` or `eth-keys` dependency. The `hyperliquid_connector.py` has EIP-712 signing code but does not import these — it uses a custom hash. If actual order signing is needed (placing orders, not just reading), the connector would need `eth-account` for `Account.sign_message()`. Currently, order placement would fail silently in production if not using the HL SDK.
  - **Fix:** Either add `eth-account>=0.10.0` to requirements, or document that the connector is read-only until the SDK is integrated.

### `railway.toml` — PASS

- Correctly references `Dockerfile.railway`.
- Health check path `/health` matches the health server.
- 120s timeout is generous enough for ML model loading.
- `ON_FAILURE` restart policy with 5 retries is appropriate.

### Health Check Endpoint — WARN

- **`health_server.py:81`** always returns `"healthy": True` and HTTP 200 as long as the server is responding. Even if the trading loop is stale (>300s) and Hyperliquid is unreachable, the health check passes. This means Railway will never restart the container based on health checks alone.
  - **Fix:** Return HTTP 503 when `trading_loop` is stale for more than 600s (indicating the trading engine may have crashed) to trigger a Railway restart.

---

## 6. Security Review

### JWT Handling — PASS

- `NEXTAUTH_SECRET` is required; absence throws at import time (`lib/auth.ts:5-8`).
- Middleware fails closed when secret is missing (returns 500).
- bcrypt-hashed password comparison for login.
- 24-hour session expiry.
- JWT strategy (not database sessions) — appropriate for single-user.

### Credential Storage — PASS

- Python side: All API keys, secrets, and private keys are referenced via `${ENV_VAR}` in YAML config and resolved at runtime from environment variables. No hardcoded secrets in config files.
- Next.js side: Broker secrets stored in `/tmp/.broker-secrets.json` (ephemeral on Vercel). No secrets in git-tracked files.
- `credential_validator.py` uses `_mask_key()` to safely log API keys (first 3 + last 3 chars only).

### API Key Exposure — WARN

- **`NEXT_PUBLIC_HYPERLIQUID_ADDRESS`** uses the `NEXT_PUBLIC_` prefix, which means this value is bundled into the client-side JavaScript. While a wallet address is public on-chain, exposing it in the frontend unnecessarily reveals the operator's identity. Consider using a server-only env var and proxying through the API.
- **`lib/execute-trade.ts:46`** reads broker secrets from a file path (`/tmp/aifred-data/.broker-secrets.json`). The file is created with default permissions. On a shared hosting environment, this could be readable by other processes. On Vercel/Railway this is fine (isolated containers).

### Rate Limiting Effectiveness — PASS

- Three-tier rate limiting covers the most sensitive endpoints.
- Execute endpoint at 1 per 10 seconds prevents rapid-fire trading.
- In-memory implementation is sufficient for single-process Vercel deployment.

### Additional Security Observations

- **No CSRF protection** on trading endpoints. NextAuth JWT tokens are sent via cookies, making CSRF theoretically possible. The `SameSite=Lax` default from NextAuth mitigates most scenarios, but POST requests from cross-origin forms could still succeed in some browsers.
  - **Fix:** Add CSRF token validation for mutating trading endpoints (`execute`, `kill-switch`, `controls`, `autoscan`).

---

## Summary

| Component | Status | Critical Issues |
|-----------|--------|-----------------|
| Orchestrator — Signal Fusion | **WARN** | 3 config key mismatches (trades, loss, interval) |
| Orchestrator — Circuit Breaker | PASS | |
| Orchestrator — Degradation | PASS | |
| Orchestrator — Error Handling | PASS | |
| Execution Engine | PASS | |
| Paper Trader | PASS | |
| Exchange Connector (ccxt) | PASS | |
| Hyperliquid Connector | PASS | |
| API Authentication | PASS | |
| API Rate Limiting | PASS | |
| API Data Validation | **WARN** | No runtime type validation on execute/autoscan |
| API — Hardcoded Address | **WARN** | Fallback wallet address in hyperliquid route |
| Config Consistency | **WARN** | 3 key mismatches, 1 dead config value |
| Dockerfile.railway | PASS | |
| start.sh | PASS | |
| requirements-railway.txt | **WARN** | Missing eth-account, no upper bounds, duplicate |
| railway.toml | PASS | |
| Health Check | **WARN** | Always returns healthy regardless of actual state |
| JWT / Auth | PASS | |
| Credential Storage | PASS | |
| CSRF Protection | **WARN** | No CSRF tokens on mutating endpoints |

### Priority Fixes

1. **[HIGH]** Fix 3 config key mismatches in `orchestrator.py` — `max_trades_per_day` -> `max_daily_trades`, `max_daily_drawdown_pct` path, `scan_interval_seconds` location. Live safety limits are being silently ignored.
2. **[MEDIUM]** Add runtime input validation (Zod) for `execute` and `autoscan` API routes.
3. **[MEDIUM]** Make health check return 503 when trading loop is stale, so Railway auto-restarts.
4. **[MEDIUM]** Remove hardcoded fallback wallet address from `hyperliquid/route.ts`.
5. **[LOW]** Add `eth-account` to requirements if live HL order placement is needed.
6. **[LOW]** Add CSRF token validation on mutating endpoints.
7. **[LOW]** Pin dependency upper bounds in `requirements-railway.txt`.
