# Phase 5: Live Trading Transition — Design Spec

**Date:** 2026-03-31
**Broker:** Hyperliquid (crypto futures)
**Capital:** Micro ($100-500)
**Deployment:** Railway (cloud, 24/7)
**Monitoring:** Telegram alerts + real-time dashboard
**Approach:** Parallel tracks — CLI-first live trading + dashboard hardening

---

## Overview

Two parallel streams ship the system from paper to live trading:

- **Stream 1 (fast track):** Python engine runs headless on Railway with Hyperliquid in live mode. Telegram alerts provide monitoring. No UI required to start trading.
- **Stream 2 (parallel):** Next.js dashboard gets authentication, credential security, real-time updates, and UI safeguards. Live UI trades are blocked until auth is in place.

The bot starts earning on Stream 1 while Stream 2 catches up. No insecure UI is ever exposed to real money.

---

## Stream 1: CLI-First Live Trading on Railway

### 1.1 Live Mode Config

New `live.yaml` config overlay (merges on top of `default.yaml`):

```yaml
system:
  mode: live

execution:
  mode: live
  exchanges:
    hyperliquid:
      enabled: true
      testnet: false
      leverage_cap: 2  # Override default 3x
    binance:
      enabled: false
    alpaca:
      enabled: false
    coinbase:
      enabled: false

risk:
  max_position_pct: 10.0        # $50 on $500 account
  max_concurrent_positions: 2
  max_daily_loss_pct: 5.0        # $25 on $500
  max_weekly_loss_pct: 10.0      # $50 on $500
  signal_tier_minimum: "A+"      # Only highest confidence
  min_confidence: 85.0
  max_single_trade_loss: 15.0    # $15 hard cap per trade
  min_account_balance: 50.0      # Halt if balance drops below

monitoring:
  telegram:
    enabled: true
    heartbeat_interval: 1800     # 30 min
    daily_report: true
    alerts:
      - trade_executed
      - position_closed
      - stop_loss_hit
      - safety_triggered
      - system_error
      - drawdown_warning
```

### 1.2 Pre-Trade Balance Check

Add balance verification in `execution_engine.py` before every trade:

- Query Hyperliquid account balance via API
- If balance < $50, halt trading and send Telegram alert
- If balance < required position size + fees, reject the trade
- Log balance on every check for audit trail

### 1.3 Startup Validation Gate

Modify `credential_validator.py` behavior in live mode:

- **Paper mode:** Log warnings, continue (current behavior)
- **Live mode:** Hard-fail. If Hyperliquid credentials fail validation (bad key, no balance, no permissions), the bot exits with error code 1. Railway will show it as a failed deploy.

Validation checks:
- API key format is valid
- Can authenticate with Hyperliquid
- Account has minimum balance ($50)
- Trading permissions are enabled on the key

### 1.4 Dry-Run Mode

Expose the existing `dry_run` flag in `execution_engine` as a CLI argument:

```
python -m src.main --mode live --dry-run
```

Behavior:
- Runs the full live pipeline: real Hyperliquid data, real signals, real risk checks
- Stops before submitting orders to the exchange
- Logs what would have been traded (asset, direction, size, confidence)
- Sends Telegram alerts for each "would-have-traded" signal
- Use for 24-48 hours before going live with real capital

### 1.5 Railway Deployment

- Hyperliquid credentials set as Railway environment variables (`HYPERLIQUID_ADDRESS`, `HYPERLIQUID_PRIVATE_KEY`)
- Never committed to code
- Use existing `Dockerfile.railway` and `railway.toml`
- Trading engine runs as continuous process via `main.py`
- Health check via existing `health_server.py`

### 1.6 Telegram Alerts

Already configured in codebase. Ensure all of these are active and tested:

| Alert Type | Trigger |
|------------|---------|
| Trade executed | Every fill |
| Position closed | Exit (TP, SL, or manual) |
| Stop-loss hit | Protective stop triggered |
| Kill switch | Emergency halt activated |
| Drawdown warning | Daily/weekly limits approaching |
| Daily report | Midnight UTC summary |
| Heartbeat | Every 30 min (proves bot is alive) |
| System error | Unhandled exceptions, connectivity loss |

---

## Stream 1: Safety & Kill Switch

### 1.7 Telegram Kill Switch Command

Add `/kill` and `/resume` commands to the Telegram bot handler:

- `/kill` — Calls `account_safety.activate_kill_switch()`, closes all open Hyperliquid positions, cancels pending orders, sends confirmation message with summary of closed positions
- `/resume` — Deactivates kill switch, sends confirmation, resumes normal trading loop
- `/status` — Returns current mode, open positions, daily P&L, balance

### 1.8 File-Based Kill Switch

On each orchestrator loop iteration, check for `/app/data/KILL_SWITCH` file:

- If file exists: halt all trading, send Telegram alert, log reason
- Create via Railway shell (`touch /app/data/KILL_SWITCH`) or deploy a commit containing it
- Remove file to resume (`rm /app/data/KILL_SWITCH`)
- Serves as a Railway-friendly emergency stop that doesn't require Telegram

### 1.9 Auto-Kill Triggers

Verify these existing `account_safety.py` hard limits are wired up in live mode:

| Trigger | Action |
|---------|--------|
| Daily loss > $25 (5%) | Pause trading 24h |
| Weekly loss > $50 (10%) | Pause trading 72h |
| 3 consecutive losses | A+ only mode, 0.5x size multiplier |
| Single trade loss > $15 | Flag, alert, review |
| Account balance < $50 | Full halt until manual resume |

### 1.10 Graceful Shutdown

On SIGTERM (Railway redeploy, restart, or scale-down):

1. Cancel any pending/unfilled orders on Hyperliquid
2. Log all open positions with current P&L (don't close — stops are in place)
3. Save bot state to `/app/data/state.json` (open positions, daily stats, kill switch status)
4. Exit cleanly

### 1.11 Startup Reconciliation

On boot, `reconciler.py` must:

1. Load saved state from `/app/data/state.json` if it exists
2. Query Hyperliquid for current open positions
3. Compare: detect orphaned positions (exist on exchange but not in state)
4. Re-attach stop-loss orders for any orphaned positions
5. Alert via Telegram with reconciliation summary
6. Log any discrepancies for manual review

---

## Stream 2: Dashboard Security & Auth

### 2.1 NextAuth with Credentials Provider

Single-user authentication (personal trading bot):

- NextAuth.js with credentials provider
- Email and bcrypt-hashed password stored as Railway env vars (`AUTH_EMAIL`, `AUTH_PASSWORD_HASH`)
- JWT session tokens with 24h expiry
- Login page at `/login`, redirect all unauthenticated users there

### 2.2 Protected API Routes

Every `/api/trading/*` endpoint wrapped with session check:

```typescript
// Middleware pattern
const session = await getServerSession(authOptions)
if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
```

No exceptions. All 15 trading endpoints require valid session.

### 2.3 Rate Limiting

Middleware on trading endpoints:

| Endpoint | Limit |
|----------|-------|
| `POST /api/trading/execute` | 1 per 10 seconds |
| `POST /api/trading/autoscan` | 1 per 60 seconds |
| All other trading endpoints | 10 per minute |

Implemented via in-memory rate limiter (sufficient for single-user). Returns 429 when exceeded.

### 2.4 Remove Client-Side Credential Store

- Delete XOR obfuscation logic in `lib/credential-store.ts`
- Replace with a thin client that only knows "connected" or "disconnected" status
- No API keys, secrets, or tokens ever sent to the browser
- The file still exists but only exposes: `isConnected(broker): boolean` and `getConnectedBrokers(): string[]` — backed by a server-side API call

### 2.5 Server-Side Credentials Only

- Hyperliquid keys live exclusively as Railway env vars
- API routes read from `process.env` on the server
- Frontend shows connection status via `/api/trading/brokers` (returns `{ hyperliquid: { connected: true, balance: "..." } }` — no keys exposed)
- Python engine reads credentials from env vars (already supported in `default.yaml` via `${VAR_NAME}` syntax)

### 2.6 Trade Confirmation Dialog

Before any live execution from the dashboard:

- Modal appears showing: asset, direction (long/short), position size ($), leverage, estimated entry price, stop-loss price, estimated max loss
- Two buttons: "Cancel" and "Confirm Trade"
- 3-second delay on "Confirm Trade" button (prevents panic-clicking)
- Only shown in live mode (paper mode executes immediately)

### 2.7 Kill Switch Button

- Red button in the dashboard header, always visible
- First click: "Are you sure? This will close all positions."
- Second click (within 5 seconds): Activates kill switch
- Calls backend endpoint that triggers `account_safety.activate_kill_switch()` + closes all Hyperliquid positions
- Button shows "KILLED — Click to Resume" state after activation

### 2.8 Live/Paper Mode Indicator

- Persistent banner at the very top of the dashboard
- **Live mode:** Red banner — "LIVE TRADING — Real Money"
- **Paper mode:** Green banner — "PAPER TRADING — Simulated"
- Cannot be dismissed. Always visible on every page.

---

## Stream 2: Real-Time Dashboard

### 2.9 Polling Architecture

Short polling via `setInterval` + Next.js API routes. No WebSocket complexity.

| Panel | Endpoint | Interval |
|-------|----------|----------|
| Live positions | `/api/trading/activity` | 5 seconds |
| Account summary | `/api/trading/performance` | 10 seconds |
| Trade feed | `/api/trading/activity` | 5 seconds |
| System health | `/api/trading/system-health` | 30 seconds |

Uses `SWR` or `react-query` with `refreshInterval` for deduplication and error handling.

### 2.10 Live Positions Panel

Table showing all open positions:

| Column | Source |
|--------|--------|
| Asset | Position data |
| Direction | Long/Short |
| Entry price | Fill price |
| Current price | Live price feed |
| Unrealized P&L | Calculated (color-coded green/red) |
| Stop-loss | ATR-based stop price |
| Time held | Duration since entry |

Empty state: "No open positions" with last scan time.

### 2.11 Account Summary Bar

Persistent bar at top of trading page:

- Total balance (from Hyperliquid)
- Daily P&L (amount + percentage, color-coded)
- Open exposure (total $ in positions)
- Number of open positions / max allowed
- Current market regime (from HMM detection)
- Bot status (running/paused/killed)

### 2.12 Trade Feed

Reverse-chronological list of recent trades:

- Asset, direction, entry/exit price, P&L, signal tier, timestamp
- Status badge: Filled, Stopped Out, Take Profit, Manually Closed
- Links to full trade details (signal reasoning, risk score)

### 2.13 System Health Indicator

Small status dot in the dashboard header:

- **Green:** Bot running, exchange connected, data fresh
- **Yellow:** Degraded (stale data >5 min, high latency, approaching limits)
- **Red:** Bot offline, kill switch active, or exchange disconnected

Tooltip on hover shows details.

---

## Out of Scope (YAGNI)

- No charting/candlesticks (use TradingView)
- No order book visualization
- No strategy backtesting in the UI (exists in CLI)
- No multi-user support
- No multi-broker support (Hyperliquid only for now)
- No mobile app
- No external monitoring integration (Datadog, PagerDuty)
- No social media or on-chain data enhancements (Phase 4 items, not Phase 5)

---

## Rollout Sequence

### Stage 1: Dry Run (24-48 hours)

- Deploy Python engine to Railway with `--dry-run --mode live`
- Real Hyperliquid data, real signals, real risk checks
- Orders stop before submission
- Telegram alerts fire for every "would-have-traded" signal
- **Success criteria:** No crashes, signals make sense, risk gates trigger correctly, Telegram alerts working

### Stage 2: Micro Live ($100)

- Remove `--dry-run`, fund Hyperliquid with $100
- Tightened limits: $50 max position, 2x leverage, A+ only
- Monitor via Telegram for 3-5 days
- **Success criteria:** No crashes, no unexpected trades, drawdown within limits, reconciliation works after Railway redeploys

### Stage 3: Dashboard Goes Live

- NextAuth, rate limiting, credential overhaul deployed
- Real-time polling active
- Kill switch button functional
- Trade confirmation dialog working
- **Success criteria:** Can monitor and intervene from UI, auth blocks unauthenticated access

### Stage 4: Scale Up

After 1-2 weeks stable at Stage 2:
- Increase capital to $500
- Allow A-tier signals (not just A+)
- Enable 2-3 concurrent positions

After 1 month stable:
- Evaluate adding Coinbase or Alpaca
- Consider loosening leverage to 3x

### Rollback Plan

At any stage:
- `/kill` via Telegram or file-based kill switch halts everything
- Positions get closed, bot pauses
- Revert to paper mode by setting `TRADING_MODE=paper` on Railway
- One env var change, zero code changes
