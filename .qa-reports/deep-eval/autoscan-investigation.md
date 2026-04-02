# Autoscan Workflow Investigation

**Date:** 2026-04-02
**Status:** SHOULD BE DISABLED

---

## 1. Workflow Inventory

Two workflow files exist in `.github/workflows/`:

| File | Name | Schedule | Purpose |
|------|------|----------|---------|
| `autotrade.yml` | AIFred Autonomous Trading | Every 30 min (`0,30 * * * *`) | Calls Vercel API endpoint via curl |
| `trading-autopilot.yml` | AIFred Trading Autopilot | Every 12 hours (`0 0,12 * * *`) | Checks out repo, runs Python `src.main --single-scan` |

---

## 2. autotrade.yml Deep Dive (the failing one)

### Trigger
- **Cron:** `0,30 * * * *` -- fires every 30 minutes, 24/7, 365 days/year (48 runs/day)
- **Manual:** `workflow_dispatch` with mode (paper/live), auto_execute, and assets inputs

### What It Does
1. Builds a JSON payload with assets (`BTC/USDT, ETH/USDT, SOL/USDT`), mode (`paper`), autoExecute (`true`), and risk limits
2. POSTs it via `curl` to `https://aifred-trading.vercel.app/api/trading/autoscan`
3. Parses the response for signals/executions
4. Optionally sends a Telegram notification if trades executed
5. Generates a GitHub Step Summary report

### Why It Fails Every Time

**Root cause: The `/api/trading/autoscan` endpoint requires JWT authentication, but the workflow sends no auth token.**

The middleware (`middleware.ts`, lines 54-61) protects all `/api/trading/*` routes:

```typescript
if (pathname.startsWith("/api/trading")) {
    const token = await getToken({
      req: request,
      secret: process.env.NEXTAUTH_SECRET,
    });
    if (!token) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
}
```

The workflow's curl command (line 91-95) sends zero authentication headers:

```bash
curl -s -w "\n%{http_code}" -X POST \
  "${{ env.APP_URL }}/api/trading/autoscan" \
  -H "Content-Type: application/json" \
  -d "$BODY"
```

The API returns HTTP 401, the workflow sees `$HTTP_CODE -ne 200`, and exits with `exit 1`.

**This means every run for the past N days has:**
- Spun up an Ubuntu runner (wasting GitHub Actions minutes)
- Sent one unauthenticated curl request
- Failed in ~3 seconds
- Sent a failure email notification

### Frequency of Failure Emails
At 48 runs/day, that is **48 failure emails per day** (unless GitHub batches notifications).

---

## 3. trading-autopilot.yml Analysis

This is a separate, more substantial workflow that:
- Runs every 12 hours (2x/day)
- Checks out the repo, installs Python deps, runs `python -m src.main --single-scan`
- Persists a trading SQLite DB via Actions cache
- Generates performance reports
- Has an optional optimizer job
- Deploys dashboard to Vercel on main branch

This workflow likely also fails (missing secrets, missing `requirements.txt` deps, etc.) but is architecturally different -- it runs the trading logic server-side in the runner, not via HTTP to Vercel.

---

## 4. Git History

Unable to check git history for when these files were added (the working directory is not a git repo or has no log for these files in the current state).

---

## 5. Recommendation

### autotrade.yml: DISABLE IMMEDIATELY

**Option A (recommended): Delete the file entirely**
- It cannot work without solving the auth problem
- Even if auth were added, running an autonomous trader via GitHub Actions cron is fragile (no state persistence, cold starts, race conditions with Vercel serverless)
- The real trading system runs on Railway, making this workflow redundant

**Option B: Disable the cron, keep manual trigger**
- Comment out the `schedule` block so it stops firing automatically
- Keep `workflow_dispatch` for occasional manual testing
- Still requires adding a JWT or API key header to actually work

```yaml
on:
  # schedule:
  #   - cron: '0,30 * * * *'   # DISABLED - no auth token, causes 48 failures/day
  workflow_dispatch:
    ...
```

### trading-autopilot.yml: REVIEW SEPARATELY

This is a more serious workflow (Python-based, with DB caching). If it is also not in active use, disable its cron too (`0 0,12 * * *`) to stop 2 additional daily runs.

---

## 6. Immediate Action Items

| Priority | Action | Effort |
|----------|--------|--------|
| P0 | Delete or disable `autotrade.yml` cron schedule | 1 min |
| P1 | Check if `trading-autopilot.yml` is also failing and disable if so | 5 min |
| P2 | If autoscan-via-cron is actually wanted, add an API key auth bypass for cron callers (e.g., `X-Cron-Secret` header checked in middleware) | 30 min |

---

## 7. Summary

The `autotrade.yml` workflow fires 48 times per day, every day. Each run curls the Vercel-hosted autoscan endpoint without any authentication. The middleware rejects it with HTTP 401. The job fails in ~3 seconds and sends a GitHub notification email. This has been happening continuously since the file was added. The fix is to delete or disable the cron trigger. The trading system already runs on Railway and does not depend on this workflow.
