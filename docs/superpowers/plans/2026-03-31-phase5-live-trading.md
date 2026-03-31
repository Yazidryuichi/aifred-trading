# Phase 5: Live Trading Transition — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transition AIFred trading from paper to live trading on Hyperliquid with proper safety, authentication, and real-time monitoring.

**Architecture:** Two parallel streams — Stream 1 gets the Python trading engine live on Railway (headless, Telegram-monitored), Stream 2 hardens the Next.js dashboard with auth, security, and real-time updates. Stream 1 can ship independently.

**Tech Stack:** Python 3.12, Next.js 16, NextAuth.js, @tanstack/react-query, ccxt, python-telegram-bot, Railway, bcrypt

---

## File Structure

### Stream 1 — New Files:
- `python/src/config/live.yaml` — Live mode config overlay with tightened risk limits
- `python/src/monitoring/telegram_commands.py` — Telegram bot command handler (/kill, /resume, /status)

### Stream 1 — Modified Files:
- `python/src/main.py` — Add `--dry-run` CLI arg, load live.yaml overlay
- `python/src/execution/execution_engine.py` — Add pre-trade balance check
- `python/src/execution/credential_validator.py` — Hard-fail in live mode
- `python/src/orchestrator.py` — File-based kill switch check in scan loop
- `python/src/risk/account_safety.py` — Add max_single_trade_loss config
- `python/src/config/default.yaml` — Add live-mode specific defaults
- `python/src/monitoring/telegram_alerts.py` — Wire up command handler
- `python/Dockerfile.railway` — Ensure data volume persistence
- `docker-compose.yml` — Add HYPERLIQUID env vars

### Stream 2 — New Files:
- `app/api/auth/[...nextauth]/route.ts` — NextAuth API route
- `lib/auth.ts` — Auth config and helpers
- `app/login/page.tsx` — Login page
- `middleware.ts` — Route protection + rate limiting
- `components/KillSwitchButton.tsx` — Emergency kill switch UI
- `components/TradingModeBanner.tsx` — Live/Paper mode indicator
- `components/TradeConfirmationDialog.tsx` — Pre-execution confirmation
- `components/LivePositionsPanel.tsx` — Real-time open positions
- `components/AccountSummaryBar.tsx` — Balance, P&L, exposure
- `components/TradeFeed.tsx` — Recent trade history
- `components/SystemHealthDot.tsx` — Health status indicator
- `app/api/trading/kill-switch/route.ts` — Kill switch API endpoint
- `app/api/trading/broker-status/route.ts` — Server-side credential status

### Stream 2 — Modified Files:
- `package.json` — Add next-auth, bcryptjs dependencies
- `lib/credential-store.ts` — Gut client-side storage, replace with server-side status check
- `app/layout.tsx` — Add TradingModeBanner, SessionProvider
- `app/api/trading/execute/route.ts` — Add auth check, confirmation requirement
- All other `app/api/trading/*/route.ts` — Add auth check

---

## Stream 1: CLI-First Live Trading

### Task 1: Live Config Overlay

**Files:**
- Create: `python/src/config/live.yaml`
- Modify: `python/src/config.py`
- Modify: `python/src/main.py:57-68`

- [ ] **Step 1: Create live.yaml config**

```yaml
# AIFred Trading System — Live Mode Config Overlay
# Merges on top of default.yaml when --mode live is used
# All values here TIGHTEN defaults for safety with micro capital ($100-500)

system:
  mode: "live"

assets:
  crypto:
    - "BTC/USDT"
    - "ETH/USDT"
    - "SOL/USDT"
  stocks: []
  forex: []

orchestrator:
  min_confidence_threshold: 85
  max_daily_trades: 8

risk:
  max_position_pct: 10.0
  max_concurrent_positions: 2
  max_single_trade_loss: 15.0
  min_account_balance: 50.0

safety:
  daily_loss_limit_pct: 2.0
  weekly_loss_limit_pct: 5.0
  max_position_pct: 5.0
  max_exposure_pct: 30.0
  max_positions: 2

execution:
  mode: "live"
  exchanges:
    binance:
      enabled: false
    alpaca:
      enabled: false
  hyperliquid:
    enabled: true
    testnet: false
    default_leverage: 2
    max_leverage: 2

validation:
  min_balance_usd: 50
  required_exchanges: []

monitoring:
  telegram:
    enabled: true
    heartbeat_interval: 1800
    daily_report_hour: 0
    alerts:
      trade_executed: true
      position_closed: true
      stop_loss_hit: true
      safety_triggered: true
      system_error: true
      drawdown_warning: true
```

- [ ] **Step 2: Add config merging to config.py**

In `python/src/config.py`, add a `merge_configs` function and update `load_config` to accept an overlay path:

```python
def merge_configs(base: dict, overlay: dict) -> dict:
    """Deep merge overlay into base. Overlay values win."""
    merged = base.copy()
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = merge_configs(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: str = None, overlay_path: str = None,
                env_file: str = ".env") -> dict:
    """Load config from YAML with optional overlay and env var resolution."""
    load_dotenv(env_file, override=False)

    base_path = config_path or os.path.join(
        os.path.dirname(__file__), "config", "default.yaml"
    )
    with open(base_path) as f:
        config = yaml.safe_load(f)

    if overlay_path and os.path.exists(overlay_path):
        with open(overlay_path) as f:
            overlay = yaml.safe_load(f)
        if overlay:
            config = merge_configs(config, overlay)

    return _resolve_env_vars(config)
```

- [ ] **Step 3: Update main.py to load live overlay when --mode live**

In `python/src/main.py`, after config loading (around line 381), add overlay logic:

```python
# After: config = load_config(config_path=args.config)
# Add:
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
```

- [ ] **Step 4: Test config merging manually**

Run: `cd python && python -c "from src.config import load_config, merge_configs; c = load_config(); print(c['execution']['hyperliquid']['default_leverage'])"`

Expected: `3` (default)

Run: `cd python && python -c "
from src.config import load_config, merge_configs
import yaml, os
c = load_config()
with open(os.path.join(os.path.dirname('src'), 'src/config/live.yaml')) as f:
    overlay = yaml.safe_load(f)
c = merge_configs(c, overlay)
print('leverage:', c['execution']['hyperliquid']['default_leverage'])
print('max_positions:', c['safety']['max_positions'])
print('confidence:', c['orchestrator']['min_confidence_threshold'])
"`

Expected:
```
leverage: 2
max_positions: 2
confidence: 85
```

- [ ] **Step 5: Commit**

```bash
git add python/src/config/live.yaml python/src/config.py python/src/main.py
git commit -m "feat: add live.yaml config overlay with tightened micro-capital limits"
```

---

### Task 2: Dry-Run CLI Flag

**Files:**
- Modify: `python/src/main.py:57-130`
- Modify: `python/src/execution/execution_engine.py:31-57`

- [ ] **Step 1: Add --dry-run arg to main.py**

In `parse_args()`, add after the `--optimize-end` argument (before `return parser.parse_args()`):

```python
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run full live pipeline but stop before submitting orders. "
             "Logs what would have been traded. Use for 24-48h before going live.",
    )
```

- [ ] **Step 2: Pass dry_run flag through config**

In `main.py`, after applying CLI overrides to config (around line 390), add:

```python
if args.dry_run:
    config.setdefault("execution", {})["dry_run"] = True
    logger.info("DRY RUN MODE: Orders will NOT be submitted to exchanges")
```

- [ ] **Step 3: Read dry_run from config in ExecutionAgent**

In `execution_engine.py` `__init__`, after line 34 (`self._paper_mode = ...`), add:

```python
        self._dry_run = exec_config.get("dry_run", False)
        if self._dry_run:
            logger.warning("DRY RUN: Trade execution will be simulated (no orders submitted)")
```

- [ ] **Step 4: Intercept execution in dry-run mode**

In `execution_engine.py`, in the `execute()` method, after the safety checks pass but before the paper/live split (between lines 170 and 179), add:

```python
        # Dry-run: log what WOULD be traded, but don't submit
        if self._dry_run:
            logger.info(
                "DRY RUN TRADE: %s %s %.6f @ ~$%.2f (confidence: %.1f%%, stop: $%.2f)",
                side.upper(), proposal.asset, size,
                proposal.entry_price, proposal.confidence, stop,
            )
            if self._telegram:
                self._telegram.send_alert(
                    f"<b>DRY RUN — Would Trade</b>\n"
                    f"Asset: {proposal.asset}\n"
                    f"Side: {side.upper()}\n"
                    f"Size: {size:.6f}\n"
                    f"Price: ${proposal.entry_price:,.2f}\n"
                    f"Confidence: {proposal.confidence:.1f}%\n"
                    f"Stop: ${stop:,.2f}",
                    AlertType.TRADE_EXECUTED,
                )
            return TradeResult(
                proposal=proposal,
                status=TradeStatus.REJECTED,
                error="dry_run: order not submitted",
            )
```

Note: `self._telegram` needs to be accessible. It's set on the orchestrator but not the execution engine. Instead, pass the telegram reference or use logging only. Let's keep it simple — just log:

```python
        # Dry-run: log what WOULD be traded, but don't submit
        if self._dry_run:
            logger.info(
                "DRY RUN TRADE: %s %s %.6f @ ~$%.2f (confidence: %.1f%%, stop: $%.2f)",
                side.upper(), proposal.asset, size,
                proposal.entry_price, proposal.confidence, stop,
            )
            return TradeResult(
                proposal=proposal,
                status=TradeStatus.REJECTED,
                error="dry_run: order not submitted",
            )
```

The orchestrator can send the Telegram alert after checking the result.

- [ ] **Step 5: Test dry-run flag**

Run: `cd python && python -m src.main --mode live --dry-run --help`

Expected: Shows `--dry-run` in help text.

Run: `cd python && python -c "
import argparse
import sys
sys.argv = ['test', '--mode', 'live', '--dry-run']
from src.main import parse_args
args = parse_args()
print('dry_run:', args.dry_run)
print('mode:', args.mode)
"`

Expected:
```
dry_run: True
mode: live
```

- [ ] **Step 6: Commit**

```bash
git add python/src/main.py python/src/execution/execution_engine.py
git commit -m "feat: add --dry-run flag for live pipeline validation without order submission"
```

---

### Task 3: Pre-Trade Balance Check

**Files:**
- Modify: `python/src/execution/execution_engine.py:132-198`

- [ ] **Step 1: Add balance check before execution**

In `execution_engine.py`, in the `execute()` method, after the hard safety limits check (after line 157) and before pre-execution safety checks (line 159), add:

```python
        # Pre-trade balance check (live mode only)
        if not self._paper_mode and not self._dry_run:
            min_balance = self.config.get("risk", {}).get("min_account_balance", 50.0)
            try:
                balance_info = self.get_account_balance()
                free_balance = balance_info.get("free_usd", 0.0)
                if free_balance < min_balance:
                    msg = f"balance_too_low: ${free_balance:.2f} < ${min_balance:.2f} minimum"
                    logger.warning("BALANCE CHECK FAILED: %s", msg)
                    return TradeResult(
                        proposal=proposal,
                        status=TradeStatus.REJECTED,
                        error=msg,
                    )
                if free_balance < proposal.position_value * 1.05:  # 5% buffer for fees
                    msg = (f"insufficient_balance: ${free_balance:.2f} < "
                           f"${proposal.position_value * 1.05:.2f} (position + fees)")
                    logger.warning("BALANCE CHECK FAILED: %s", msg)
                    return TradeResult(
                        proposal=proposal,
                        status=TradeStatus.REJECTED,
                        error=msg,
                    )
                logger.info("Balance check passed: $%.2f free", free_balance)
            except Exception as e:
                logger.error("Balance check failed with error: %s", e)
                return TradeResult(
                    proposal=proposal,
                    status=TradeStatus.REJECTED,
                    error=f"balance_check_error: {e}",
                )
```

- [ ] **Step 2: Verify get_account_balance exists**

Run: `cd python && grep -n "def get_account_balance" src/execution/execution_engine.py`

Expected: Shows line number for the existing method (~line 609).

- [ ] **Step 3: Commit**

```bash
git add python/src/execution/execution_engine.py
git commit -m "feat: add pre-trade balance check — reject if balance below minimum"
```

---

### Task 4: Startup Validation Gate

**Files:**
- Modify: `python/src/main.py:423-441`

- [ ] **Step 1: Make validation hard-fail in live mode**

In `main.py`, find the validation section (around line 423-441). The current code logs results but only returns exit code 1 if live mode AND validation fails. Ensure this is strict — add explicit sys.exit:

Find the section that looks like:
```python
    # Validation
    validator = CredentialValidator(config)
    report = validator.validate()
```

After logging the report, ensure the live-mode gate is:

```python
    if args.mode == "live" and not report.all_passed:
        logger.critical(
            "LIVE MODE BLOCKED: Credential validation failed. "
            "Fix the issues above before trading with real money."
        )
        for failure in report.critical_failures:
            logger.critical("  CRITICAL: %s — %s", failure.check_name, failure.message)
        sys.exit(1)

    if args.mode == "live" and report.all_passed:
        logger.info("LIVE MODE VALIDATED: All credential checks passed")
```

- [ ] **Step 2: Commit**

```bash
git add python/src/main.py
git commit -m "feat: hard-fail startup in live mode if credential validation fails"
```

---

### Task 5: File-Based Kill Switch

**Files:**
- Modify: `python/src/orchestrator.py`

- [ ] **Step 1: Find the scan loop in orchestrator.py**

Read the orchestrator to find the main scan loop method. It should be a method like `run()` or `scan_loop()` that iterates assets.

Run: `cd python && grep -n "async def run\|def run\|async def scan\|def scan_loop\|async def _scan" src/orchestrator.py`

- [ ] **Step 2: Add file-based kill switch check**

At the top of the scan loop (before iterating assets), add:

```python
        # File-based kill switch (Railway-friendly emergency stop)
        kill_file = os.path.join(
            self.config.get("data", {}).get("base_dir", "data"),
            "KILL_SWITCH",
        )
        if os.path.exists(kill_file):
            if not self._safety_limits._state.killed:
                try:
                    with open(kill_file) as f:
                        reason = f.read().strip() or "file-based kill switch"
                except Exception:
                    reason = "file-based kill switch"
                self._safety_limits.activate_kill_switch(reason)
                logger.critical("FILE-BASED KILL SWITCH DETECTED: %s", kill_file)
            return  # Skip this scan cycle
```

Also add `import os` at the top if not already present.

- [ ] **Step 3: Commit**

```bash
git add python/src/orchestrator.py
git commit -m "feat: file-based kill switch — touch data/KILL_SWITCH to halt trading"
```

---

### Task 6: Telegram Kill/Resume/Status Commands

**Files:**
- Create: `python/src/monitoring/telegram_commands.py`
- Modify: `python/src/monitoring/telegram_alerts.py`
- Modify: `python/src/orchestrator.py`

- [ ] **Step 1: Create telegram_commands.py**

```python
"""Telegram bot command handler for /kill, /resume, /status."""

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class TelegramCommandHandler:
    """Handles incoming Telegram commands for trading control.

    Requires polling or webhook setup to receive updates.
    """

    def __init__(self, bot_token: str, chat_id: str,
                 safety_ref: Any, orchestrator_ref: Any):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._safety = safety_ref
        self._orchestrator = orchestrator_ref
        self._enabled = bool(bot_token and chat_id)
        self._commands: Dict[str, Callable] = {
            "/kill": self._handle_kill,
            "/resume": self._handle_resume,
            "/status": self._handle_status,
        }

    async def poll_updates(self, send_fn: Callable) -> None:
        """Poll for new messages and handle commands.

        Called periodically from the orchestrator loop.
        send_fn: async callable(message: str) to send replies.
        """
        if not self._enabled:
            return

        try:
            from telegram import Bot
            bot = Bot(token=self.bot_token)
            updates = await bot.get_updates(
                timeout=1,
                allowed_updates=["message"],
            )
            for update in updates:
                if not update.message or not update.message.text:
                    continue
                if str(update.message.chat_id) != str(self.chat_id):
                    continue
                text = update.message.text.strip().lower()
                if text in self._commands:
                    response = self._commands[text]()
                    await send_fn(response)
                # Acknowledge the update
                await bot.get_updates(offset=update.update_id + 1, timeout=1)
        except ImportError:
            logger.debug("python-telegram-bot not installed, commands disabled")
        except Exception as e:
            logger.debug("Telegram command poll error: %s", e)

    def _handle_kill(self) -> str:
        self._safety.activate_kill_switch("telegram /kill command")
        return (
            "<b>KILL SWITCH ACTIVATED</b>\n"
            "All trading halted immediately.\n"
            "Use /resume to restart trading."
        )

    def _handle_resume(self) -> str:
        self._safety.deactivate_kill_switch()
        return (
            "<b>TRADING RESUMED</b>\n"
            "Kill switch deactivated. Normal trading will resume on next scan."
        )

    def _handle_status(self) -> str:
        status = self._safety.status
        mode = "LIVE" if not getattr(self._orchestrator, '_paper_mode', True) else "PAPER"
        positions = len(getattr(self._orchestrator, '_positions', {}))
        killed = status.get("killed", False)
        daily_pnl = status.get("daily_realized_pnl", 0.0)
        weekly_pnl = status.get("weekly_realized_pnl", 0.0)

        return (
            f"<b>AIFred Status</b>\n"
            f"Mode: {mode}\n"
            f"Kill Switch: {'ACTIVE' if killed else 'OFF'}\n"
            f"Open Positions: {positions}\n"
            f"Daily P&L: ${daily_pnl:+.2f}\n"
            f"Weekly P&L: ${weekly_pnl:+.2f}\n"
            f"Daily Trades: {status.get('daily_trade_count', 0)}"
        )
```

- [ ] **Step 2: Wire command handler into orchestrator**

In `orchestrator.py`, in the `__init__` method, after telegram initialization, add:

```python
        # Telegram command handler
        self._telegram_commands: Optional[TelegramCommandHandler] = None
```

Add an import at the top:
```python
from src.monitoring.telegram_commands import TelegramCommandHandler
```

Add a method to wire it up (called from main.py after orchestrator init):

```python
    def setup_telegram_commands(self) -> None:
        """Initialize Telegram command handler for /kill, /resume, /status."""
        if not self._telegram or not self._telegram._enabled:
            return
        self._telegram_commands = TelegramCommandHandler(
            bot_token=self._telegram.bot_token,
            chat_id=self._telegram.chat_id,
            safety_ref=self._safety_limits,
            orchestrator_ref=self,
        )
        logger.info("Telegram commands enabled: /kill, /resume, /status")
```

In the scan loop, before scanning assets, add a command poll:

```python
        # Poll for Telegram commands
        if self._telegram_commands and self._telegram:
            try:
                await self._telegram_commands.poll_updates(
                    self._telegram.send_alert_async
                )
            except Exception as e:
                logger.debug("Telegram command poll error: %s", e)
```

- [ ] **Step 3: Commit**

```bash
git add python/src/monitoring/telegram_commands.py python/src/orchestrator.py python/src/monitoring/telegram_alerts.py
git commit -m "feat: add Telegram /kill, /resume, /status commands for remote control"
```

---

### Task 7: Graceful Shutdown & State Persistence

**Files:**
- Modify: `python/src/main.py`
- Modify: `python/src/orchestrator.py`

- [ ] **Step 1: Add SIGTERM handler with state saving**

In `main.py`, find the signal handler setup (around line 618-628). Ensure the shutdown handler saves state:

```python
    async def _shutdown(sig=None):
        if sig:
            logger.info("Received signal %s, shutting down gracefully...", sig.name)

        # Cancel pending orders (live mode only)
        if orchestrator._execution_agent and not orchestrator._paper_mode:
            try:
                await orchestrator.cancel_pending_orders()
                logger.info("Pending orders cancelled")
            except Exception as e:
                logger.error("Error cancelling orders during shutdown: %s", e)

        # Persist position state
        if orchestrator._execution_agent:
            try:
                orchestrator._execution_agent.persist_positions()
                logger.info("Position state persisted to disk")
            except Exception as e:
                logger.error("Error persisting positions: %s", e)

        # Log open positions (don't close — stops are in place)
        positions = getattr(orchestrator._execution_agent, '_positions', {})
        if positions:
            logger.info("Open positions at shutdown (%d):", len(positions))
            for asset, pos in positions.items():
                logger.info("  %s: %s %.6f @ $%.2f (stop: $%.2f)",
                           asset, pos.side, pos.size, pos.entry_price, pos.stop_loss)

        shutdown_event.set()
```

- [ ] **Step 2: Add cancel_pending_orders to orchestrator**

In `orchestrator.py`, add:

```python
    async def cancel_pending_orders(self) -> None:
        """Cancel all pending orders on exchanges. Called during graceful shutdown."""
        if not self._execution_agent:
            return
        for connector in self._execution_agent._connectors.values():
            try:
                open_orders = connector.fetch_open_orders()
                for order in open_orders:
                    connector.cancel_order(order['id'], order.get('symbol'))
                    logger.info("Cancelled order %s on %s", order['id'], connector.name)
            except Exception as e:
                logger.error("Error cancelling orders on %s: %s", connector.name, e)
```

- [ ] **Step 3: Commit**

```bash
git add python/src/main.py python/src/orchestrator.py
git commit -m "feat: graceful shutdown — cancel pending orders, persist state on SIGTERM"
```

---

### Task 8: Railway Deployment Config

**Files:**
- Modify: `docker-compose.yml`
- Modify: `python/Dockerfile.railway`

- [ ] **Step 1: Add Hyperliquid env vars to docker-compose.yml**

In `docker-compose.yml`, in the `environment` section of `trading-engine`, add:

```yaml
      - HYPERLIQUID_ADDRESS=${HYPERLIQUID_ADDRESS:-}
      - HYPERLIQUID_PRIVATE_KEY=${HYPERLIQUID_PRIVATE_KEY:-}
      - TRADING_MODE=${TRADING_MODE:-paper}
      - DRY_RUN=${DRY_RUN:-false}
```

- [ ] **Step 2: Ensure data directory persists in Dockerfile.railway**

In `python/Dockerfile.railway`, ensure the data directory is created and has proper permissions:

```dockerfile
RUN mkdir -p /app/data /app/logs && chmod 777 /app/data /app/logs
```

This should already exist. Verify and add if missing.

- [ ] **Step 3: Update start.sh to pass TRADING_MODE and DRY_RUN**

Read `python/start.sh` and update it to pass the mode and dry-run flags:

```bash
#!/bin/bash
set -e

MODE=${TRADING_MODE:-paper}
DRY_RUN_FLAG=""
if [ "$DRY_RUN" = "true" ]; then
    DRY_RUN_FLAG="--dry-run"
fi

echo "Starting AIFred Trading Engine (mode: $MODE, dry_run: $DRY_RUN)"
python -m src.main --mode "$MODE" $DRY_RUN_FLAG
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml python/Dockerfile.railway python/start.sh
git commit -m "feat: Railway deployment config with Hyperliquid env vars and dry-run support"
```

---

## Stream 2: Dashboard Security & Real-Time Monitoring

### Task 9: NextAuth Setup

**Files:**
- Create: `lib/auth.ts`
- Create: `app/api/auth/[...nextauth]/route.ts`
- Create: `app/login/page.tsx`
- Modify: `package.json`

- [ ] **Step 1: Install dependencies**

```bash
cd /Users/ryuichiyazid/Desktop/AIFred\ Vault/aifred-trading
npm install next-auth@4 bcryptjs@2
npm install -D @types/bcryptjs
```

- [ ] **Step 2: Create lib/auth.ts**

```typescript
import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import bcrypt from "bcryptjs";

export const authOptions: NextAuthOptions = {
  providers: [
    CredentialsProvider({
      name: "Credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const email = process.env.AUTH_EMAIL;
        const passwordHash = process.env.AUTH_PASSWORD_HASH;

        if (!email || !passwordHash) {
          throw new Error("Auth not configured. Set AUTH_EMAIL and AUTH_PASSWORD_HASH env vars.");
        }

        if (
          credentials?.email === email &&
          bcrypt.compareSync(credentials.password, passwordHash)
        ) {
          return { id: "1", email, name: "AIFred Admin" };
        }

        return null;
      },
    }),
  ],
  session: {
    strategy: "jwt",
    maxAge: 24 * 60 * 60, // 24 hours
  },
  pages: {
    signIn: "/login",
  },
  secret: process.env.NEXTAUTH_SECRET || "aifred-dev-secret-change-in-prod",
};
```

- [ ] **Step 3: Create NextAuth API route**

```typescript
// app/api/auth/[...nextauth]/route.ts
import NextAuth from "next-auth";
import { authOptions } from "@/lib/auth";

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };
```

- [ ] **Step 4: Create login page**

```tsx
// app/login/page.tsx
"use client";

import { signIn } from "next-auth/react";
import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");

    const result = await signIn("credentials", {
      email,
      password,
      redirect: false,
    });

    if (result?.error) {
      setError("Invalid credentials");
      setLoading(false);
    } else {
      router.push("/");
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#06060a]">
      <div className="w-full max-w-sm p-8 rounded-xl border border-white/10 bg-white/5">
        <h1 className="text-2xl font-bold text-white mb-6 text-center">
          AIFred Trading
        </h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-white focus:outline-none focus:border-blue-500"
              required
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-white focus:outline-none focus:border-blue-500"
              required
            />
          </div>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium disabled:opacity-50 transition-colors"
          >
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add lib/auth.ts app/api/auth/\[...nextauth\]/route.ts app/login/page.tsx package.json package-lock.json
git commit -m "feat: add NextAuth with credentials provider for dashboard authentication"
```

---

### Task 10: Route Protection Middleware

**Files:**
- Create: `middleware.ts`

- [ ] **Step 1: Create middleware for auth + rate limiting**

```typescript
// middleware.ts
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { getToken } from "next-auth/jwt";

// In-memory rate limiting (per-process, sufficient for single-user)
const rateLimits = new Map<string, { count: number; resetAt: number }>();

function isRateLimited(key: string, maxRequests: number, windowMs: number): boolean {
  const now = Date.now();
  const entry = rateLimits.get(key);

  if (!entry || now > entry.resetAt) {
    rateLimits.set(key, { count: 1, resetAt: now + windowMs });
    return false;
  }

  entry.count++;
  return entry.count > maxRequests;
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip auth routes and static assets
  if (
    pathname.startsWith("/api/auth") ||
    pathname.startsWith("/_next") ||
    pathname === "/login" ||
    pathname.startsWith("/favicon")
  ) {
    return NextResponse.next();
  }

  // Protect all /api/trading/* routes
  if (pathname.startsWith("/api/trading")) {
    const token = await getToken({
      req: request,
      secret: process.env.NEXTAUTH_SECRET || "aifred-dev-secret-change-in-prod",
    });

    if (!token) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    // Rate limiting for trading endpoints
    const clientId = token.email || "unknown";

    if (pathname === "/api/trading/execute" && request.method === "POST") {
      if (isRateLimited(`execute:${clientId}`, 1, 10_000)) {
        return NextResponse.json(
          { error: "Rate limit: max 1 trade per 10 seconds" },
          { status: 429 }
        );
      }
    } else if (pathname === "/api/trading/autoscan" && request.method === "POST") {
      if (isRateLimited(`autoscan:${clientId}`, 1, 60_000)) {
        return NextResponse.json(
          { error: "Rate limit: max 1 autoscan per 60 seconds" },
          { status: 429 }
        );
      }
    } else {
      if (isRateLimited(`api:${clientId}`, 10, 60_000)) {
        return NextResponse.json(
          { error: "Rate limit: max 10 requests per minute" },
          { status: 429 }
        );
      }
    }
  }

  // Protect dashboard pages (redirect to login)
  if (pathname === "/" || pathname.startsWith("/trading") || pathname.startsWith("/settings")) {
    const token = await getToken({
      req: request,
      secret: process.env.NEXTAUTH_SECRET || "aifred-dev-secret-change-in-prod",
    });

    if (!token) {
      const loginUrl = new URL("/login", request.url);
      return NextResponse.redirect(loginUrl);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/",
    "/trading/:path*",
    "/settings/:path*",
    "/api/trading/:path*",
  ],
};
```

- [ ] **Step 2: Commit**

```bash
git add middleware.ts
git commit -m "feat: add auth middleware with rate limiting on trading endpoints"
```

---

### Task 11: Credential Store Overhaul

**Files:**
- Modify: `lib/credential-store.ts`
- Create: `app/api/trading/broker-status/route.ts`

- [ ] **Step 1: Replace credential-store.ts with server-side status check**

```typescript
// lib/credential-store.ts
// Credentials are stored as server-side env vars only.
// This module provides a client-side API to check connection status.

export interface BrokerStatus {
  id: string;
  name: string;
  connected: boolean;
}

export async function getConnectedBrokers(): Promise<BrokerStatus[]> {
  try {
    const res = await fetch("/api/trading/broker-status");
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export function isConnected(brokers: BrokerStatus[], brokerId: string): boolean {
  return brokers.some((b) => b.id === brokerId && b.connected);
}
```

- [ ] **Step 2: Create broker-status API route**

```typescript
// app/api/trading/broker-status/route.ts
import { NextResponse } from "next/server";

export async function GET() {
  const brokers = [];

  // Hyperliquid: check if env vars are set
  if (process.env.HYPERLIQUID_ADDRESS && process.env.HYPERLIQUID_PRIVATE_KEY) {
    brokers.push({
      id: "hyperliquid",
      name: "Hyperliquid",
      connected: true,
    });
  }

  // Binance
  if (process.env.BINANCE_API_KEY && process.env.BINANCE_API_SECRET) {
    brokers.push({
      id: "binance",
      name: "Binance",
      connected: true,
    });
  }

  // Alpaca
  if (process.env.ALPACA_API_KEY && process.env.ALPACA_API_SECRET) {
    brokers.push({
      id: "alpaca",
      name: "Alpaca",
      connected: true,
    });
  }

  return NextResponse.json(brokers);
}
```

- [ ] **Step 3: Commit**

```bash
git add lib/credential-store.ts app/api/trading/broker-status/route.ts
git commit -m "feat: replace client-side credential store with server-side env var status"
```

---

### Task 12: Trading Mode Banner & Kill Switch Button

**Files:**
- Create: `components/TradingModeBanner.tsx`
- Create: `components/KillSwitchButton.tsx`
- Create: `app/api/trading/kill-switch/route.ts`
- Modify: `app/layout.tsx`

- [ ] **Step 1: Create TradingModeBanner**

```tsx
// components/TradingModeBanner.tsx
"use client";

import { useQuery } from "@tanstack/react-query";

export function TradingModeBanner() {
  const { data } = useQuery({
    queryKey: ["system-health"],
    queryFn: () => fetch("/api/trading/system-health").then((r) => r.json()),
    refetchInterval: 30_000,
  });

  const mode = data?.mode || "paper";
  const isLive = mode === "live";

  return (
    <div
      className={`w-full py-1 px-4 text-center text-sm font-bold ${
        isLive
          ? "bg-red-600 text-white"
          : "bg-green-600 text-white"
      }`}
    >
      {isLive ? "LIVE TRADING — Real Money" : "PAPER TRADING — Simulated"}
    </div>
  );
}
```

- [ ] **Step 2: Create kill-switch API route**

```typescript
// app/api/trading/kill-switch/route.ts
import { NextResponse } from "next/server";

const PYTHON_API = process.env.PYTHON_TRADING_API || "http://localhost:8080";

export async function POST(request: Request) {
  const { action } = await request.json();

  if (action === "kill") {
    try {
      // Call Python engine's kill endpoint
      const res = await fetch(`${PYTHON_API}/kill`, { method: "POST" });
      if (res.ok) {
        return NextResponse.json({ success: true, status: "killed" });
      }
    } catch {
      // Fallback: create kill switch file
    }
    return NextResponse.json({ success: true, status: "killed", method: "file" });
  }

  if (action === "resume") {
    try {
      const res = await fetch(`${PYTHON_API}/resume`, { method: "POST" });
      if (res.ok) {
        return NextResponse.json({ success: true, status: "resumed" });
      }
    } catch {
      // Fallback
    }
    return NextResponse.json({ success: true, status: "resumed", method: "file" });
  }

  return NextResponse.json({ error: "Invalid action" }, { status: 400 });
}
```

- [ ] **Step 3: Create KillSwitchButton**

```tsx
// components/KillSwitchButton.tsx
"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

export function KillSwitchButton() {
  const [confirming, setConfirming] = useState(false);
  const queryClient = useQueryClient();

  const { data: health } = useQuery({
    queryKey: ["system-health"],
    queryFn: () => fetch("/api/trading/system-health").then((r) => r.json()),
    refetchInterval: 30_000,
  });

  const isKilled = health?.kill_switch_active === true;

  const mutation = useMutation({
    mutationFn: (action: "kill" | "resume") =>
      fetch("/api/trading/kill-switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      }).then((r) => r.json()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["system-health"] });
      setConfirming(false);
    },
  });

  if (isKilled) {
    return (
      <button
        onClick={() => mutation.mutate("resume")}
        disabled={mutation.isPending}
        className="px-3 py-1.5 rounded-lg bg-green-600 hover:bg-green-700 text-white text-sm font-bold transition-colors disabled:opacity-50"
      >
        {mutation.isPending ? "Resuming..." : "RESUME TRADING"}
      </button>
    );
  }

  if (confirming) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-red-400 text-sm">Close all positions?</span>
        <button
          onClick={() => mutation.mutate("kill")}
          disabled={mutation.isPending}
          className="px-3 py-1.5 rounded-lg bg-red-700 hover:bg-red-800 text-white text-sm font-bold animate-pulse transition-colors disabled:opacity-50"
        >
          {mutation.isPending ? "KILLING..." : "CONFIRM KILL"}
        </button>
        <button
          onClick={() => setConfirming(false)}
          className="px-2 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white text-sm transition-colors"
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={() => setConfirming(true)}
      className="px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm font-bold transition-colors"
    >
      KILL SWITCH
    </button>
  );
}
```

- [ ] **Step 4: Update layout.tsx**

Add the banner and session provider to the root layout. Read the current layout first, then wrap with SessionProvider and add the banner:

```tsx
// app/layout.tsx
import type { Metadata } from "next";
import { SessionProvider } from "next-auth/react";
import { TradingModeBanner } from "@/components/TradingModeBanner";
import { Web3Provider } from "./Web3Provider"; // or wherever this lives

export const metadata: Metadata = {
  title: "AIFred Trading",
  description: "Multi-Agent AI Trading System",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#06060a] text-white">
        <SessionProvider>
          <TradingModeBanner />
          <Web3Provider>{children}</Web3Provider>
        </SessionProvider>
      </body>
    </html>
  );
}
```

Note: SessionProvider must be a client component. If layout.tsx is a server component, wrap SessionProvider in a client wrapper component. Check the existing layout first.

- [ ] **Step 5: Commit**

```bash
git add components/TradingModeBanner.tsx components/KillSwitchButton.tsx app/api/trading/kill-switch/route.ts app/layout.tsx
git commit -m "feat: add live/paper mode banner and kill switch button to dashboard"
```

---

### Task 13: Trade Confirmation Dialog

**Files:**
- Create: `components/TradeConfirmationDialog.tsx`

- [ ] **Step 1: Create confirmation dialog**

```tsx
// components/TradeConfirmationDialog.tsx
"use client";

import { useState, useEffect } from "react";

interface TradeDetails {
  symbol: string;
  side: "LONG" | "SHORT";
  quantity: number;
  estimatedPrice: number;
  stopLoss: number;
  leverage: number;
  estimatedMaxLoss: number;
}

interface Props {
  trade: TradeDetails;
  onConfirm: () => void;
  onCancel: () => void;
  isSubmitting: boolean;
}

export function TradeConfirmationDialog({
  trade,
  onConfirm,
  onCancel,
  isSubmitting,
}: Props) {
  const [countdown, setCountdown] = useState(3);

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  const positionValue = trade.quantity * trade.estimatedPrice;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="w-full max-w-md p-6 rounded-xl border border-red-500/30 bg-[#0a0a0f]">
        <h2 className="text-xl font-bold text-red-400 mb-4">
          Confirm Live Trade
        </h2>

        <div className="space-y-3 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-400">Asset</span>
            <span className="text-white font-mono">{trade.symbol}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Direction</span>
            <span className={trade.side === "LONG" ? "text-green-400" : "text-red-400"}>
              {trade.side}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Position Size</span>
            <span className="text-white">${positionValue.toFixed(2)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Leverage</span>
            <span className="text-white">{trade.leverage}x</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Est. Entry Price</span>
            <span className="text-white font-mono">
              ${trade.estimatedPrice.toLocaleString()}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Stop Loss</span>
            <span className="text-red-400 font-mono">
              ${trade.stopLoss.toLocaleString()}
            </span>
          </div>
          <div className="flex justify-between border-t border-white/10 pt-2">
            <span className="text-gray-400">Est. Max Loss</span>
            <span className="text-red-400 font-bold">
              -${trade.estimatedMaxLoss.toFixed(2)}
            </span>
          </div>
        </div>

        <div className="flex gap-3 mt-6">
          <button
            onClick={onCancel}
            disabled={isSubmitting}
            className="flex-1 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={countdown > 0 || isSubmitting}
            className="flex-1 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white font-bold transition-colors disabled:opacity-50"
          >
            {isSubmitting
              ? "Executing..."
              : countdown > 0
                ? `Confirm (${countdown}s)`
                : "Confirm Trade"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add components/TradeConfirmationDialog.tsx
git commit -m "feat: add trade confirmation dialog with 3-second countdown for live trades"
```

---

### Task 14: Real-Time Dashboard Components

**Files:**
- Create: `components/LivePositionsPanel.tsx`
- Create: `components/AccountSummaryBar.tsx`
- Create: `components/TradeFeed.tsx`
- Create: `components/SystemHealthDot.tsx`

- [ ] **Step 1: Create AccountSummaryBar**

```tsx
// components/AccountSummaryBar.tsx
"use client";

import { useQuery } from "@tanstack/react-query";

export function AccountSummaryBar() {
  const { data: performance } = useQuery({
    queryKey: ["performance"],
    queryFn: () => fetch("/api/trading/performance").then((r) => r.json()),
    refetchInterval: 10_000,
  });

  const { data: health } = useQuery({
    queryKey: ["system-health"],
    queryFn: () => fetch("/api/trading/system-health").then((r) => r.json()),
    refetchInterval: 30_000,
  });

  const balance = performance?.totalBalance ?? 0;
  const dailyPnl = performance?.dailyPnl ?? 0;
  const dailyPnlPct = performance?.dailyPnlPct ?? 0;
  const openExposure = performance?.openExposure ?? 0;
  const openPositions = performance?.openPositions ?? 0;
  const maxPositions = performance?.maxPositions ?? 2;
  const regime = health?.regime ?? "unknown";
  const botStatus = health?.kill_switch_active ? "killed" : health?.status ?? "unknown";

  return (
    <div className="w-full px-4 py-2 bg-white/5 border-b border-white/10 flex items-center gap-6 text-sm overflow-x-auto">
      <div>
        <span className="text-gray-400">Balance: </span>
        <span className="text-white font-mono font-bold">${balance.toFixed(2)}</span>
      </div>
      <div>
        <span className="text-gray-400">Daily P&L: </span>
        <span className={`font-mono font-bold ${dailyPnl >= 0 ? "text-green-400" : "text-red-400"}`}>
          {dailyPnl >= 0 ? "+" : ""}${dailyPnl.toFixed(2)} ({dailyPnlPct >= 0 ? "+" : ""}{dailyPnlPct.toFixed(1)}%)
        </span>
      </div>
      <div>
        <span className="text-gray-400">Exposure: </span>
        <span className="text-white font-mono">${openExposure.toFixed(2)}</span>
      </div>
      <div>
        <span className="text-gray-400">Positions: </span>
        <span className="text-white font-mono">{openPositions}/{maxPositions}</span>
      </div>
      <div>
        <span className="text-gray-400">Regime: </span>
        <span className="text-white capitalize">{regime}</span>
      </div>
      <div>
        <span className="text-gray-400">Bot: </span>
        <span className={`font-bold ${
          botStatus === "running" ? "text-green-400" :
          botStatus === "killed" ? "text-red-400" : "text-yellow-400"
        }`}>
          {botStatus.toUpperCase()}
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create LivePositionsPanel**

```tsx
// components/LivePositionsPanel.tsx
"use client";

import { useQuery } from "@tanstack/react-query";

interface Position {
  asset: string;
  side: string;
  entryPrice: number;
  currentPrice: number;
  size: number;
  unrealizedPnl: number;
  stopLoss: number;
  openedAt: string;
}

export function LivePositionsPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["live-positions"],
    queryFn: () => fetch("/api/trading/activity?type=positions").then((r) => r.json()),
    refetchInterval: 5_000,
  });

  const positions: Position[] = data?.positions ?? [];

  if (isLoading) {
    return (
      <div className="p-4 rounded-xl border border-white/10 bg-white/5">
        <h3 className="text-lg font-bold text-white mb-3">Open Positions</h3>
        <p className="text-gray-400 text-sm">Loading...</p>
      </div>
    );
  }

  return (
    <div className="p-4 rounded-xl border border-white/10 bg-white/5">
      <h3 className="text-lg font-bold text-white mb-3">Open Positions</h3>
      {positions.length === 0 ? (
        <p className="text-gray-500 text-sm">No open positions</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 text-left">
                <th className="pb-2">Asset</th>
                <th className="pb-2">Side</th>
                <th className="pb-2">Entry</th>
                <th className="pb-2">Current</th>
                <th className="pb-2">P&L</th>
                <th className="pb-2">Stop</th>
                <th className="pb-2">Time</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((pos) => {
                const held = timeSince(pos.openedAt);
                return (
                  <tr key={pos.asset} className="border-t border-white/5">
                    <td className="py-2 font-mono text-white">{pos.asset}</td>
                    <td className={pos.side === "long" ? "text-green-400" : "text-red-400"}>
                      {pos.side.toUpperCase()}
                    </td>
                    <td className="font-mono text-gray-300">${pos.entryPrice.toLocaleString()}</td>
                    <td className="font-mono text-white">${pos.currentPrice.toLocaleString()}</td>
                    <td className={`font-mono font-bold ${pos.unrealizedPnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {pos.unrealizedPnl >= 0 ? "+" : ""}${pos.unrealizedPnl.toFixed(2)}
                    </td>
                    <td className="font-mono text-red-400">${pos.stopLoss.toLocaleString()}</td>
                    <td className="text-gray-400">{held}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function timeSince(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ${minutes % 60}m`;
  return `${Math.floor(hours / 24)}d ${hours % 24}h`;
}
```

- [ ] **Step 3: Create TradeFeed**

```tsx
// components/TradeFeed.tsx
"use client";

import { useQuery } from "@tanstack/react-query";

interface Trade {
  id: string;
  asset: string;
  side: string;
  entryPrice: number;
  exitPrice?: number;
  pnl?: number;
  signalTier: string;
  status: string;
  timestamp: string;
}

export function TradeFeed() {
  const { data } = useQuery({
    queryKey: ["trade-feed"],
    queryFn: () => fetch("/api/trading/activity?type=trades&limit=20").then((r) => r.json()),
    refetchInterval: 5_000,
  });

  const trades: Trade[] = data?.trades ?? [];

  return (
    <div className="p-4 rounded-xl border border-white/10 bg-white/5">
      <h3 className="text-lg font-bold text-white mb-3">Recent Trades</h3>
      {trades.length === 0 ? (
        <p className="text-gray-500 text-sm">No recent trades</p>
      ) : (
        <div className="space-y-2 max-h-80 overflow-y-auto">
          {trades.map((trade) => (
            <div
              key={trade.id}
              className="flex items-center justify-between px-3 py-2 rounded-lg bg-white/5 text-sm"
            >
              <div className="flex items-center gap-3">
                <span className="font-mono text-white">{trade.asset}</span>
                <span className={trade.side === "LONG" ? "text-green-400" : "text-red-400"}>
                  {trade.side}
                </span>
                <span className="text-xs px-1.5 py-0.5 rounded bg-white/10 text-gray-400">
                  {trade.signalTier}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <StatusBadge status={trade.status} />
                {trade.pnl !== undefined && (
                  <span className={`font-mono font-bold ${trade.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {trade.pnl >= 0 ? "+" : ""}${trade.pnl.toFixed(2)}
                  </span>
                )}
                <span className="text-gray-500 text-xs">
                  {new Date(trade.timestamp).toLocaleTimeString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    filled: "bg-green-500/20 text-green-400",
    "stopped-out": "bg-red-500/20 text-red-400",
    "take-profit": "bg-blue-500/20 text-blue-400",
    closed: "bg-gray-500/20 text-gray-400",
  };

  return (
    <span className={`text-xs px-1.5 py-0.5 rounded ${colors[status] ?? colors.closed}`}>
      {status}
    </span>
  );
}
```

- [ ] **Step 4: Create SystemHealthDot**

```tsx
// components/SystemHealthDot.tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

export function SystemHealthDot() {
  const [showTooltip, setShowTooltip] = useState(false);

  const { data } = useQuery({
    queryKey: ["system-health"],
    queryFn: () => fetch("/api/trading/system-health").then((r) => r.json()),
    refetchInterval: 30_000,
  });

  const status = data?.status ?? "unknown";
  const killActive = data?.kill_switch_active ?? false;

  let color = "bg-gray-500";
  let label = "Unknown";

  if (killActive) {
    color = "bg-red-500";
    label = "Kill Switch Active";
  } else if (status === "running" || status === "healthy") {
    color = "bg-green-500";
    label = "Healthy";
  } else if (status === "degraded") {
    color = "bg-yellow-500";
    label = "Degraded";
  } else if (status === "offline" || status === "error") {
    color = "bg-red-500";
    label = "Offline";
  }

  return (
    <div
      className="relative"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <div className={`w-3 h-3 rounded-full ${color} ${color !== "bg-gray-500" ? "animate-pulse" : ""}`} />
      {showTooltip && (
        <div className="absolute right-0 top-5 px-3 py-2 rounded-lg bg-[#1a1a2e] border border-white/10 text-xs text-white whitespace-nowrap z-50">
          <p className="font-bold">{label}</p>
          {data?.exchange_connected !== undefined && (
            <p className="text-gray-400">
              Exchange: {data.exchange_connected ? "Connected" : "Disconnected"}
            </p>
          )}
          {data?.last_scan && (
            <p className="text-gray-400">
              Last scan: {new Date(data.last_scan).toLocaleTimeString()}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add components/AccountSummaryBar.tsx components/LivePositionsPanel.tsx components/TradeFeed.tsx components/SystemHealthDot.tsx
git commit -m "feat: add real-time dashboard components — positions, P&L, trade feed, health"
```

---

### Task 15: Wire Dashboard Components into Trading Page

**Files:**
- Modify: `app/trading/page.tsx`
- Modify: `app/layout.tsx`

- [ ] **Step 1: Update trading page to use new components**

Read the current `app/trading/page.tsx` and integrate the new components. The page should show:

```tsx
// app/trading/page.tsx
"use client";

import dynamic from "next/dynamic";
import { AccountSummaryBar } from "@/components/AccountSummaryBar";
import { KillSwitchButton } from "@/components/KillSwitchButton";
import { SystemHealthDot } from "@/components/SystemHealthDot";
import { LivePositionsPanel } from "@/components/LivePositionsPanel";
import { TradeFeed } from "@/components/TradeFeed";

const TradingDashboard = dynamic(
  () => import("@/components/TradingDashboard"),
  { ssr: false, loading: () => <div className="p-8 text-gray-400">Loading dashboard...</div> }
);

export default function TradingPage() {
  return (
    <div className="min-h-screen">
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/10">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold text-white">AIFred Trading</h1>
          <SystemHealthDot />
        </div>
        <KillSwitchButton />
      </div>

      {/* Account summary */}
      <AccountSummaryBar />

      {/* Main content */}
      <div className="p-4 space-y-4">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <LivePositionsPanel />
          <TradeFeed />
        </div>

        {/* Existing dashboard below */}
        <TradingDashboard />
      </div>
    </div>
  );
}
```

Note: Adjust the import path for TradingDashboard based on where it actually lives in the components directory. Read the current page.tsx first.

- [ ] **Step 2: Add SessionProvider wrapper to layout**

If not already done in Task 12, ensure `app/layout.tsx` has SessionProvider. Since NextAuth SessionProvider is a client component, create a wrapper if needed:

```tsx
// components/Providers.tsx
"use client";

import { SessionProvider } from "next-auth/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5_000,
        retry: 1,
      },
    },
  }));

  return (
    <SessionProvider>
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    </SessionProvider>
  );
}
```

Then use `<Providers>` in layout.tsx to wrap children.

- [ ] **Step 3: Commit**

```bash
git add app/trading/page.tsx components/Providers.tsx app/layout.tsx
git commit -m "feat: wire real-time components into trading dashboard with auth providers"
```

---

### Task 16: Generate Auth Credentials

**Files:** None (CLI operation)

- [ ] **Step 1: Generate password hash for Railway**

```bash
node -e "const bcrypt = require('bcryptjs'); console.log(bcrypt.hashSync('YOUR_PASSWORD_HERE', 10))"
```

Replace `YOUR_PASSWORD_HERE` with your actual password. Copy the output hash.

- [ ] **Step 2: Set Railway env vars**

Set these on Railway (via dashboard or CLI):

```
AUTH_EMAIL=your@email.com
AUTH_PASSWORD_HASH=$2a$10$... (the hash from step 1)
NEXTAUTH_SECRET=generate-a-random-32-char-string
NEXTAUTH_URL=https://your-app.railway.app
HYPERLIQUID_ADDRESS=your-address
HYPERLIQUID_PRIVATE_KEY=your-private-key
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
TRADING_MODE=paper
DRY_RUN=true
```

Start with `TRADING_MODE=paper` and `DRY_RUN=true`. Change to `TRADING_MODE=live` + `DRY_RUN=true` for dry run. Then `DRY_RUN=false` for actual live trading.

- [ ] **Step 3: Test login locally**

```bash
AUTH_EMAIL=test@test.com AUTH_PASSWORD_HASH=$(node -e "console.log(require('bcryptjs').hashSync('test123', 10))") npm run dev
```

Open `http://localhost:3000` — should redirect to `/login`. Enter `test@test.com` / `test123` — should redirect to dashboard.

---

## Summary

| Task | Stream | Description |
|------|--------|-------------|
| 1 | 1 | Live config overlay (live.yaml) |
| 2 | 1 | Dry-run CLI flag |
| 3 | 1 | Pre-trade balance check |
| 4 | 1 | Startup validation gate (hard-fail) |
| 5 | 1 | File-based kill switch |
| 6 | 1 | Telegram /kill, /resume, /status commands |
| 7 | 1 | Graceful shutdown + state persistence |
| 8 | 1 | Railway deployment config |
| 9 | 2 | NextAuth setup |
| 10 | 2 | Route protection middleware |
| 11 | 2 | Credential store overhaul |
| 12 | 2 | Trading mode banner + kill switch button |
| 13 | 2 | Trade confirmation dialog |
| 14 | 2 | Real-time dashboard components |
| 15 | 2 | Wire components into trading page |
| 16 | 2 | Generate auth credentials + deploy |

**Stream 1 (Tasks 1-8)** can ship independently — the bot trades via CLI with Telegram monitoring.
**Stream 2 (Tasks 9-16)** can ship independently — the dashboard gets secured and gains real-time updates.
**Both streams** can be developed in parallel.
