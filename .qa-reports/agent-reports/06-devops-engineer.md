# DevOps / Infrastructure Engineer Review

**Reviewer**: DevOps Engineer (Agent 06/12)
**Date**: 2026-04-01
**Scope**: Deployment infrastructure, Docker, CI/CD, monitoring, environment variables, scalability

---

## Infrastructure Diagram

```
                          +------------------+
                          |   GitHub Actions  |
                          | (cron: 30m / 12h) |
                          +--------+---------+
                                   |
                          triggers autoscan API
                                   |
                    +--------------+---------------+
                    |                               |
            +-------v--------+             +-------v--------+
            |    Vercel       |             |    Railway      |
            | (Next.js App)  |   REST API   | (Python Engine) |
            |  Dashboard +   +<------------>+ Trading Loop +  |
            |  Auth + API    |   /health    | Health Server   |
            +-------+--------+   /status    +-------+--------+
                    |            /prices             |
                    |                                |
            +-------v--------+             +--------v--------+
            | Env Vars:       |             | Env Vars:        |
            | NEXTAUTH_SECRET |             | TRADING_MODE     |
            | RAILWAY_BACKEND |             | HYPERLIQUID_*    |
            | HYPERLIQUID_*   |             | TELEGRAM_*       |
            +-----------------+             | ANTHROPIC_*      |
                                            +------------------+
                                                     |
                                            +--------v--------+
                                            | External APIs    |
                                            | - Hyperliquid    |
                                            | - Binance/Alpaca |
                                            | - Telegram       |
                                            | - Anthropic LLM  |
                                            +------------------+
```

---

## 1. Railway Deployment

### `python/Dockerfile.railway` -- PASS (with notes)

**Strengths**:
- CPU-only PyTorch install (~180MB vs ~2GB) is the right call for Railway's memory constraints
- `python:3.12-slim` base is appropriately minimal
- `--no-cache-dir` on pip avoids bloating the image
- HEALTHCHECK defined with sensible parameters (30s interval, 60s start-period)
- `chmod 777` on data/logs dirs allows the Railway non-root user to write

**Issues**:
- **WARN**: Single-stage build. The `build-essential`-free base is fine since there are no C-compiled deps in `requirements-railway.txt`, but the `apt-get` layer installs `curl` which is only needed for HEALTHCHECK. Consider multi-stage if image size becomes a concern.
- **WARN**: `EXPOSE 8080` is hardcoded, but the CMD relies on `$PORT` from Railway. Not a bug (Railway sets PORT), but the EXPOSE is misleading.
- **WARN**: No `.dockerignore` found in `python/` directory. All files including `__pycache__`, `paper_trading.log`, `data/` are copied into context.

### `python/requirements-railway.txt` -- WARN

**Missing from railway vs full requirements.txt**:
- `yfinance` -- needed if stock assets are configured (default.yaml lists NVDA, AAPL, SPY)
- `lightgbm`, `catboost` -- full ensemble uses these but Railway version omits them
- `spacy`, `nltk`, `newspaper3k`, `finbert-embedding` -- NLP stack omitted
- `psycopg2-binary`, `redis`, `pyarrow` -- DB/cache backends omitted
- `streamlit`, `plotly` -- dashboard omitted (reasonable for Railway)
- `empyrical`, `quantstats`, `riskfolio-lib` -- risk analytics omitted
- `optuna`, `mlflow` -- optimizer/tracking omitted
- `neuralforecast` -- advanced forecasting omitted
- `mcp` -- MCP server omitted

**Verdict**: The Railway deployment is a deliberately reduced footprint. This is FINE if the Railway service only runs paper trading on crypto assets via Hyperliquid. However, default.yaml configures stocks (NVDA, AAPL, SPY) which would require `yfinance` or `alpaca-trade-api` -- both are missing. This will cause runtime ImportError if stock assets are scanned on Railway.

**Duplicate entry**: `aiohttp>=3.9.0` appears twice (lines 11 and 49). Harmless but sloppy.

### `python/start.sh` -- PASS

- Starts health server first (Railway needs a listening port quickly)
- Uses `wait -n` to detect if either process dies -- good process supervision
- Kills both processes on exit -- correct cleanup
- Respects `TRADING_MODE` and `DRY_RUN` env vars

**Minor**: The `sleep 3` between health server start and trading engine is a pragmatic choice. Could be replaced with a health check loop but not worth the complexity.

### `python/railway.toml` -- PASS

- `healthcheckPath = "/health"` matches the health server endpoint
- `healthcheckTimeout = 120` -- generous but appropriate given PyTorch import time
- `restartPolicyType = "ON_FAILURE"` with 5 retries -- correct for a long-running service
- `startCommand` correctly points to `/app/start.sh`

---

## 2. Vercel Deployment

### `next.config.ts` -- PASS

- `ignoreBuildErrors: false` -- good, TypeScript errors will block deploy
- `serverExternalPackages: ["ccxt"]` -- necessary, ccxt has native bindings

### `middleware.ts` -- PASS

**Strengths**:
- Fail-closed: rejects all requests if `NEXTAUTH_SECRET` is not set (line 35-39)
- Rate limiting on trading endpoints (1 trade/10s, 1 autoscan/60s, 10 req/min general)
- Auth on both API routes and dashboard pages
- Redirects unauthenticated dashboard requests to `/login`

**Issues**:
- **WARN**: In-memory rate limiting (line 6) resets on every Vercel cold start and is per-edge-function instance. In a multi-region deployment, rate limits would be per-region and easily circumvented. For a single-user platform this is acceptable but should be documented.
- **WARN**: The rate limit Map will grow unbounded over time (no TTL cleanup). For long-running edge instances, this is a slow memory leak. Low severity given Vercel's short function lifetimes.

### Environment Variables -- WARN

**Vercel-side env vars needed** (based on code analysis):
| Variable | Used In | Required? |
|---|---|---|
| `NEXTAUTH_SECRET` | middleware.ts, lib/auth.ts | **CRITICAL** -- blocks all requests if missing |
| `AUTH_EMAIL` | lib/auth.ts | Required for login |
| `AUTH_PASSWORD_HASH` | lib/auth.ts | Required for login |
| `RAILWAY_BACKEND_URL` | paper-status/route.ts, system-health/route.ts | Required for Railway connectivity |
| `NEXT_PUBLIC_HYPERLIQUID_ADDRESS` | hyperliquid/route.ts | Optional (fallback chain) |
| `HYPERLIQUID_ADDRESS` | hyperliquid/route.ts, broker-status/route.ts | Optional |
| `HYPERLIQUID_PRIVATE_KEY` | broker-status/route.ts | Optional |
| `PYTHON_TRADING_API` | kill-switch/route.ts | Optional (defaults to localhost:8080) |
| `TRADING_MODE` | system-health/route.ts | Optional (defaults to "paper") |
| `BINANCE_API_KEY` / `BINANCE_API_SECRET` | broker-status/route.ts | Optional |
| `ALPACA_API_KEY` / `ALPACA_API_SECRET` | broker-status/route.ts | Optional |
| `NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID` | wagmi-config.ts | Optional (wallet connect) |
| `NEXT_PUBLIC_SUPABASE_URL` | trading-autopilot.yml build step | Optional |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | trading-autopilot.yml build step | Optional |

---

## 3. Docker

### `docker-compose.yml` -- PASS

**Strengths**:
- Resource limits (1 CPU, 2GB RAM) prevent runaway usage
- Log rotation (50MB x 5 files) prevents disk exhaustion
- 30s stop grace period for graceful shutdown
- Volume mounts for persistent data and logs
- Healthcheck via `pgrep`

**Issues**:
- **WARN**: Healthcheck uses `pgrep -f "python -m src.main"` -- this checks process existence but not responsiveness. The Railway Dockerfile uses HTTP health check which is superior. Consider aligning.
- **INFO**: No `redis` or `postgres` service defined. docker-compose only runs the trading engine. This is fine if SQLite is the intended local DB.

### `python/Dockerfile` (local/dev) -- PASS

- Multi-stage build with TA-Lib C compilation -- well done
- venv copy pattern is clean
- Uses Python 3.11 (while Railway uses 3.12) -- **WARN**: version mismatch between local and production

### PyTorch CPU-only Install -- PASS

The `--index-url https://download.pytorch.org/whl/cpu` approach is optimal for Railway:
- Saves ~1.8GB image size
- Faster builds
- Railway has no GPU anyway
- The trading system uses PyTorch for LSTM/Transformer inference, not GPU training

---

## 4. CI/CD

### `.github/workflows/autotrade.yml` -- WARN

**Purpose**: Runs autonomous trading scans every 30 minutes via cron.

**Issues**:
- **FAIL**: Calls `$APP_URL/api/trading/autoscan` WITHOUT authentication. The middleware requires NextAuth JWT token for `/api/trading/*` routes. This workflow will receive 401 Unauthorized every time unless auth is bypassed for this specific endpoint.
- **WARN**: Hardcoded `APP_URL: https://aifred-trading.vercel.app` -- should be a secret or variable
- **WARN**: No build/test step before running trades -- relies on Vercel already being deployed

### `.github/workflows/trading-autopilot.yml` -- WARN

**Purpose**: Full pipeline -- scan, optimize, report, deploy dashboard.

**Issues**:
- **WARN**: Uses `pip install -r requirements.txt` (the full requirements file) which includes TA-Lib, psycopg2, and other packages requiring C compilation. This will FAIL on `ubuntu-latest` without `apt-get install` of build deps (especially TA-Lib C library).
- **WARN**: Python version set to 3.11 but `runtime.txt` says 3.12 -- inconsistency
- **WARN**: `deploy-dashboard` job runs `npx vercel --prod` which deploys directly from CI without preview. No staged rollout.
- **INFO**: Caching of `trading.db` via GitHub Actions cache is clever but fragile -- cache eviction could lose trading state.

### Automated Tests -- WARN

- `vitest.config.ts` is configured with jsdom environment
- `package.json` has `test` and `test:watch` scripts
- Tests exist in `tests/` directory (api, components, lib, setup.ts)
- **No Python tests** found anywhere in the repo. Zero test coverage for the trading engine, risk management, signal fusion, order execution -- the most critical code in the system.
- **No CI step runs tests** before deployment in either workflow.

**Verdict**: Frontend has basic test infrastructure. Python backend (the part that handles real money) has zero automated tests. This is a **FAIL** for a trading system.

---

## 5. Monitoring & Alerting

### Telegram Bot -- PASS

- `TelegramAlerts` class in `python/src/monitoring/telegram_alerts.py`
- Rate limiting (20 messages/60s window)
- Graceful degradation when token not configured
- Alert types: trade_executed, stop_loss_hit, daily_summary, model_degradation, system_error, drawdown_warning
- Full command interface (`telegram_commands.py`) and bot (`telegram_bot.py`)
- Config-driven enable/disable per alert type

### Health Checks -- PASS

- Railway health server checks: server alive, trading loop log freshness (5-min threshold), Hyperliquid API reachability
- `/status` endpoint returns last 100 log lines with parsed scan info
- `/prices` endpoint proxies Hyperliquid for live prices
- docker-compose healthcheck via process grep (30s interval)

**Issue**:
- **WARN**: Health endpoint always returns `"healthy": True` (line 84 of health_server.py) regardless of check results. A stale trading loop or unreachable Hyperliquid still reports healthy. This means Railway will never restart the container based on health check failures -- the health check is effectively decorative.

### Logging -- WARN

- Python uses stdlib `logging` with format: `%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s`
- `structlog` is in requirements but the code uses stdlib `logging.getLogger()` everywhere -- structlog is unused dead dependency
- Log level configurable via CLI `--log-level` and config file
- File handler + console handler configured
- Third-party log noise suppressed (urllib3, httpx, xgboost)

**Issue**:
- **WARN**: Not using structured logging (JSON). When running on Railway, log parsing/search is harder with plain text format. `structlog` is already a dependency but not actually used.

### Error Alerting Coverage -- WARN

The monitoring directory has good coverage:
- `system_health.py` -- system health monitoring
- `degradation_manager.py` -- subsystem failure detection
- `audit_trail.py` -- audit logging
- `trade_logger.py` -- trade-specific logging
- `model_tracker.py` -- ML model performance tracking
- `report_generator.py` -- performance reports

Missing:
- No external uptime monitoring (e.g., UptimeRobot, Better Stack)
- No alerting when the Railway service itself goes down (Telegram alerts only work while the service is running)

---

## 6. Environment Variables Audit

### Complete List of Required Env Vars

#### Railway (Python Trading Engine)
| Variable | Source | Required? | Status |
|---|---|---|---|
| `PORT` | Railway auto-injected | Auto | OK |
| `TRADING_MODE` | Manual config | Yes | Set in start.sh default |
| `DRY_RUN` | Manual config | No | Defaults to false |
| `HYPERLIQUID_ADDRESS` | Secret | For live trading | Unknown |
| `HYPERLIQUID_PRIVATE_KEY` | Secret | For live trading | Unknown |
| `BINANCE_API_KEY` | Secret | For Binance | Unknown |
| `BINANCE_API_SECRET` | Secret | For Binance | Unknown |
| `ALPACA_API_KEY` | Secret | For Alpaca | Unknown |
| `ALPACA_API_SECRET` | Secret | For Alpaca | Unknown |
| `ANTHROPIC_API_KEY` | Secret | For LLM meta-reasoning | Unknown |
| `OPENAI_API_KEY` | Secret | Fallback for meta-reasoning | Unknown |
| `TELEGRAM_BOT_TOKEN` | Secret | For alerts | Unknown |
| `TELEGRAM_CHAT_ID` | Secret | For alerts | Unknown |
| `REDDIT_CLIENT_ID` | Secret | For sentiment | Unknown |
| `REDDIT_CLIENT_SECRET` | Secret | For sentiment | Unknown |
| `ETHERSCAN_API_KEY` | Secret | For on-chain analysis | Unknown |

#### Vercel (Next.js Dashboard)
| Variable | Required? | Status |
|---|---|---|
| `NEXTAUTH_SECRET` | **CRITICAL** | Unknown |
| `AUTH_EMAIL` | **CRITICAL** | Unknown |
| `AUTH_PASSWORD_HASH` | **CRITICAL** | Unknown |
| `RAILWAY_BACKEND_URL` | **HIGH** | Unknown |
| `TRADING_MODE` | Medium | Defaults to "paper" |
| `HYPERLIQUID_ADDRESS` | Medium | Optional |
| `NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID` | Low | Optional |

#### GitHub Actions Secrets
| Variable | Required? |
|---|---|
| `TELEGRAM_BOT_TOKEN` | For notifications |
| `TELEGRAM_CHAT_ID` | For notifications |
| `BROKER_ID` | For live trading |
| `BROKER_API_KEY` | For live trading |
| `BROKER_API_SECRET` | For live trading |
| `BINANCE_API_KEY` | For autopilot |
| `BINANCE_API_SECRET` | For autopilot |
| `ALPACA_API_KEY` | For autopilot |
| `ALPACA_API_SECRET` | For autopilot |
| `ANTHROPIC_API_KEY` | For LLM |
| `VERCEL_TOKEN` | For dashboard deploy |
| `VERCEL_ORG_ID` | For dashboard deploy |
| `VERCEL_PROJECT_ID` | For dashboard deploy |
| `NEXT_PUBLIC_SUPABASE_URL` | For build |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | For build |

### Secrets in Code -- PASS

- `.gitignore` correctly excludes `.env`, `.env.local`, and `data/.broker-secrets.json`
- `.env.docker` contains only placeholder values -- safe to commit
- `.env.example` contains only empty values -- safe to commit
- No hardcoded secrets found in source code
- All secrets referenced via `${ENV_VAR}` in YAML config or `os.environ.get()` in Python

### Inconsistency -- WARN

- `.env.example` uses `BINANCE_SECRET` but docker-compose and config use `BINANCE_API_SECRET` -- naming mismatch will cause silent failures
- `.env.example` uses `ALPACA_SECRET` but everywhere else uses `ALPACA_API_SECRET`

---

## 7. Scalability Concerns

### File-Based Storage -- FAIL

- SQLite databases in `python/data/`: `trading.db`, `positions.db`, `paper_trades.db`
- JSON files in `data/`: `trading-data.json`, `activity-log.json`
- Railway's ephemeral filesystem means **all data is lost on every deploy/restart**
- No Railway volume mounts configured in `railway.toml`
- `docker-compose.yml` has proper volume mounts for local dev, but this does not apply to Railway
- The `reconciliation.db_path: "data/positions.db"` and `system.db_path: "data/trading.db"` will write to ephemeral `/app/data/` on Railway

**Impact**: Every Railway restart (deploy, crash, or scale event) will lose:
- All trade history
- All open position state
- All audit trails
- All paper trading results

This is the single most critical infrastructure issue.

### Memory Usage -- WARN

- PyTorch CPU-only + transformers + scikit-learn + xgboost on Railway
- docker-compose limits to 2GB RAM
- Railway free tier: 512MB, Pro tier: 8GB per service
- PyTorch model loading (LSTM, Transformer, CNN) will spike memory
- No memory profiling or OOM protection beyond Railway's container limits
- The `transformers` library alone can use 500MB+ for model loading

**Recommendation**: Monitor Railway memory usage. If exceeding limits, consider:
1. Lazy model loading (only load when needed)
2. Model quantization
3. Reducing ensemble size for Railway deployment

### Concurrent Request Handling -- PASS (for current scale)

- Health server uses aiohttp (async) -- handles concurrent requests well
- Trading engine runs as a single-threaded scan loop -- by design, not a bottleneck
- Vercel handles frontend concurrency via serverless functions
- No shared state issues between Vercel instances (auth is JWT-based)

---

## Summary Scorecard

| Area | Rating | Key Issue |
|---|---|---|
| Railway Deployment | **PASS** | Well-configured, appropriate for the use case |
| Vercel Deployment | **PASS** | Fail-closed auth, rate limiting |
| Docker | **PASS** | Good multi-stage build, resource limits |
| CI/CD - Workflows | **WARN** | autotrade.yml will 401; autopilot.yml missing build deps |
| CI/CD - Testing | **FAIL** | Zero Python tests for the trading engine |
| Monitoring - Telegram | **PASS** | Comprehensive alert types, rate limited |
| Monitoring - Health | **WARN** | Always returns healthy regardless of check results |
| Monitoring - Logging | **WARN** | structlog dependency unused; no structured (JSON) logging |
| Env Vars - Security | **PASS** | No leaked secrets |
| Env Vars - Consistency | **WARN** | Naming mismatches between .env.example and actual usage |
| Scalability - Storage | **FAIL** | Ephemeral filesystem on Railway; all data lost on restart |
| Scalability - Memory | **WARN** | PyTorch + transformers could exceed Railway memory limits |
| Python Version | **WARN** | 3.11 in Dockerfile/workflow vs 3.12 in Dockerfile.railway/runtime.txt |

---

## Critical Action Items

1. **[FAIL] Railway Data Persistence**: Add a Railway volume or migrate to an external database (Supabase Postgres, Railway Postgres addon, or Railway volumes). Without this, every deploy loses all trading state.

2. **[FAIL] Python Test Coverage**: Add tests for at minimum: risk management, signal fusion, order execution, position reconciliation. These are financial-loss-critical code paths with zero test coverage.

3. **[FAIL] autotrade.yml Authentication**: The GitHub Actions workflow calls `/api/trading/autoscan` without a JWT token. Middleware will reject it with 401. Either: (a) add a service account token to the workflow, or (b) exempt the autoscan endpoint from auth with a shared secret header.

4. **[WARN] Health Check Honesty**: `health_server.py` line 84 always returns `"healthy": True`. Change to return 503 when the trading loop is stale (>5 min) or Hyperliquid is unreachable, so Railway can trigger a restart.

5. **[WARN] Env Var Naming**: Fix `.env.example` to use `BINANCE_API_SECRET` and `ALPACA_API_SECRET` (matching docker-compose and config.yaml).

6. **[WARN] trading-autopilot.yml Build Deps**: Add `apt-get install` for TA-Lib C library before `pip install -r requirements.txt`, or use `requirements-railway.txt` which omits TA-Lib.

7. **[WARN] Python Version Alignment**: Standardize on either 3.11 or 3.12 across Dockerfile, Dockerfile.railway, runtime.txt, and GitHub Actions.
