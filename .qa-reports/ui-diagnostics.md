# UI/UX Diagnostic Report
## Date: 2026-04-01

---

## Issue-by-Issue Analysis

---

### Issue 1: No Hyperliquid Branding

**Component chain:** `TradingDashboard.tsx` > `LiveStatusPanel()` (line 2072) and `HyperliquidBalance` (line 2366)

**What happens:**
- The Live Prices card (line 2072) shows "Hyperliquid" or "Unavailable" in a tiny `text-[10px] text-zinc-600` label. This is the ONLY place "Hyperliquid" appears, and only when prices load successfully.
- `HyperliquidBalance` component (line 2366) is rendered inside TradingDashboard but requires a wagmi wallet connection (`useAccount()` > `isConnected`). If no wallet is connected via the browser extension, it returns `null` (line 88) and is completely invisible.
- The top-level `page.tsx` header just says "AIFred Trading" with no exchange branding.
- `AccountSummaryBar` has no Hyperliquid branding at all.
- `SystemHealthDot` tooltip shows "Exchange: Connected/Disconnected" but not which exchange.

**Root cause:** There is no dedicated "Connected Exchange" indicator anywhere in the top-level UI. The Hyperliquid name only appears as a tiny source label in the Live Prices card buried in the TradingDashboard, and in the HyperliquidBalance component which is gated behind wagmi wallet connection.

**Fix needed:**
1. **File:** `components/AccountSummaryBar.tsx` (line 29-62) -- Add a "Hyperliquid" exchange badge before/after the Balance field showing connected exchange status. Pull exchange connectivity from `/api/trading/system-health` response (which already checks Hyperliquid mainnet).
2. **File:** `app/trading/page.tsx` (line 15) -- Add exchange badge next to "AIFred Trading" title: e.g., "Connected: Hyperliquid" with green dot when system-health shows mainnet healthy.
3. **File:** `components/SystemHealthDot.tsx` (line 46-49) -- The tooltip already conditionally shows exchange status but the system-health API does not return `exchange_connected` as a boolean. The API returns component-level status. Map the "Hyperliquid Mainnet" component status to this field.

**Priority:** HIGH -- Users need immediate visual confirmation of which exchange they are trading on.

---

### Issue 2: Balance Shows $0

**Component chain:** `AccountSummaryBar` > `GET /api/trading/performance` > `data/trading-data.json`

**What happens:**
- `AccountSummaryBar` (line 18) reads `performance?.totalBalance` and falls back to `0`.
- The `/api/trading/performance` endpoint (route.ts line 35-38) returns `{ ...data, dailyReturns, monthlyReturns, riskMetrics }` where `data` is the raw content of `data/trading-data.json`.
- `trading-data.json` has `summary.currentEquity: 154602.76` and `summary.totalPnl: 54602.76` but **has NO field named `totalBalance`**.
- The API also returns NO `dailyPnl`, `dailyPnlPct`, or `openExposure` fields.

**Root cause:** FIELD NAME MISMATCH. `AccountSummaryBar` expects `totalBalance`, `dailyPnl`, `dailyPnlPct`, `openExposure` -- none of these fields exist in the API response. The actual data has `summary.currentEquity`, `summary.totalPnl`, etc.

**Fix needed:**
- **File:** `components/AccountSummaryBar.tsx` (lines 18-25) -- Change field mappings:
  - `balance` should read from `performance?.summary?.currentEquity ?? 0` (not `performance?.totalBalance`)
  - `dailyPnl` should read from `performance?.summary?.totalPnl ?? 0` (or compute daily from dailyReturns)
  - `openPositions` already has a fallback to `performance?.summary?.openPositions` (line 22-24) which WILL work
  - `openExposure` has no source -- needs to be computed server-side or from open positions data
- **Alternative fix in API:** `app/api/trading/performance/route.ts` (line 35-38) -- Add top-level convenience fields:
  ```ts
  totalBalance: data.summary?.currentEquity ?? 0,
  dailyPnl: dailyReturns.length > 0 ? dailyReturns[dailyReturns.length - 1].return * (data.summary?.currentEquity ?? 0) : 0,
  openPositions: data.summary?.openPositions ?? 0,
  openExposure: computeExposure(data.openPositions ?? []),
  ```

**Priority:** CRITICAL -- This is the most visible number on the dashboard.

---

### Issue 3: Open Positions Shows 0

**Component chain:** `LivePositionsPanel` > `GET /api/trading/activity?type=positions` > activity-log.json

**What happens:**
- `LivePositionsPanel` (line 19) fetches `/api/trading/activity?type=positions` and reads `data?.positions`.
- The `/api/trading/activity` GET handler (route.ts lines 579-603) **completely ignores the `type` query parameter**. It only reads `limit`. It returns `{ activities: [...] }`, never `{ positions: [...] }`.
- Therefore `data?.positions` is always `undefined`, and the fallback `?? []` means positions is always an empty array.
- Meanwhile, `trading-data.json` has 3 real open positions in `data.openPositions` with full data (asset, side, entry_price, etc.), but `LivePositionsPanel` never queries this data.

**Root cause:** TWO PROBLEMS:
1. The activity API does not handle `type=positions` -- it returns activities regardless of the type param.
2. Even if it did, the activity log contains activity entries (trade_executed, signal_generated, etc.), NOT structured position objects with fields like `entryPrice`, `currentPrice`, `unrealizedPnl`, `stopLoss`.

**Fix needed:**
- **Option A (recommended):** Create a new endpoint or modify `/api/trading/activity` to handle `type=positions`:
  - **File:** `app/api/trading/activity/route.ts` -- Add handling for `type=positions` that reads from `data/trading-data.json` > `openPositions` array, mapping fields to match the `Position` interface in `LivePositionsPanel` (asset, side, entryPrice, currentPrice, size, unrealizedPnl, stopLoss, openedAt).
- **Option B:** Change `LivePositionsPanel` to fetch from `/api/trading/performance` and read `data.openPositions`.
  - **File:** `components/LivePositionsPanel.tsx` (line 19) -- Change fetch URL to `/api/trading/performance`, then read `data?.openPositions` and map the field names (e.g., `entry_price` -> `entryPrice`).

**Priority:** CRITICAL -- Users cannot see their live positions at all.

---

### Issue 4: Bot Shows OFFLINE/UNKNOWN

**Component chain:** `AccountSummaryBar` > `GET /api/trading/system-health` > Railway backend `/health`

**What happens:**
- `AccountSummaryBar` (line 27) reads `health?.status` and displays it, falling back to "unknown".
- `/api/trading/system-health` (route.ts line 143) sets `status` based on `orchestrator.status === "healthy" ? "running" : "offline"`.
- The orchestrator check (line 20-68) calls `${RAILWAY_URL}/health`.
- **`RAILWAY_BACKEND_URL` is NOT set in any local env file.** It is not in `.env.local`, `.env`, or `.vercel/.env.development.local`. It is only referenced in code.
- When `RAILWAY_URL` is undefined, the check returns `status: "down"` with message "Backend not configured: RAILWAY_BACKEND_URL environment variable is missing".
- This means `orchestrator.status === "down"`, so the API returns `status: "offline"`.

**Root cause:** `RAILWAY_BACKEND_URL` environment variable is NOT configured locally or on Vercel. Even if the Railway backend is running, the Vercel frontend cannot reach it because it does not know the URL.

**Additional issue:** Even when properly configured, `kill_switch_active` is hardcoded to `false` (line 136) with a comment "Will be true when kill switch API is connected" -- meaning the kill switch state is never read from the backend.

**Fix needed:**
1. **Environment:** Set `RAILWAY_BACKEND_URL` in Vercel environment variables (and `.env.local` for dev). The value should be the Railway deployment URL (e.g., `https://aifred-trading-production.up.railway.app`).
2. **Environment:** Set `TRADING_MODE=live` in Vercel env if live trading is active.
3. **File:** `app/api/trading/system-health/route.ts` (line 136) -- Fetch actual kill switch state from Railway backend instead of hardcoding `false`.

**Priority:** CRITICAL -- Core operational status is broken.

---

### Issue 5: Live Prices Shows "Unavailable"

**Component chain:** `TradingDashboard.tsx` > `LiveStatusPanel()` > `GET /api/trading/live-prices` > `https://api.hyperliquid.xyz/info` (allMids)

**What happens:**
- `LiveStatusPanel` (line 2072) shows "Hyperliquid" when `livePrices?.source === "hyperliquid-mainnet"`, otherwise "Unavailable".
- The `/api/trading/live-prices` endpoint calls the Hyperliquid mainnet API directly with `{ type: "allMids" }`.
- If the call succeeds, it returns `source: "hyperliquid-mainnet"` with actual prices.
- If it fails, it returns `source: "unavailable"` with null prices (line 102).

**Root cause:** This is likely a DEPLOYMENT ISSUE, not a code issue. Possible causes:
1. **Vercel edge/serverless cold start timeouts** -- The 8-second timeout may not be enough for cold starts.
2. **Network restrictions** -- Vercel serverless functions may have issues reaching `api.hyperliquid.xyz`.
3. **CORS or rate limiting** -- Hyperliquid may rate-limit requests from Vercel's IP range.

**Additional UI issue:** Even when prices ARE available, the component at line 2076 shows "Unable to fetch prices" when `livePrices && !livePrices.prices?.BTC` -- this means if BTC price is null but other prices work, nothing shows. This is overly strict.

**Fix needed:**
1. **File:** `app/api/trading/live-prices/route.ts` -- Add better error logging, increase timeout, add retry logic.
2. **File:** `components/trading/TradingDashboard.tsx` (line 2076) -- Change the condition from checking only BTC to checking if ANY price is available: `!Object.values(livePrices.prices).some(v => v != null)`.
3. **Consider:** Move price fetching to a client-side call directly to Hyperliquid API (like `HyperliquidBalance` does) to avoid server-side networking issues.

**Priority:** HIGH -- Live prices are a core feature for traders.

---

### Issue 6: Paper Trading Shows "Scan #0" and STOPPED

**Component chain:** `TradingDashboard.tsx` > `LiveStatusPanel()` > `GET /api/trading/paper-status` > Railway backend `/status`

**What happens:**
- `LiveStatusPanel` (line 1858) fetches `/api/trading/paper-status`, then normalizes the response.
- The paper-status API (route.ts lines 7-64) requires `RAILWAY_BACKEND_URL` to be set.
- When `RAILWAY_BACKEND_URL` is missing, it returns `{ running: false, error: "Backend not configured..." }`.
- The `normalizePaperStatus` function (line 1789) receives this and:
  - `running` = false (so UI shows "STOPPED")
  - `scanCount` = 0 (from empty log_tail, so UI shows "Scan #0")
  - `portfolioValue` = 10000 (hardcoded default)
  - Everything else is empty/default.
- Even when Railway IS reachable, the normalize function (line 1793-1821) counts scans from `log_tail` which is a small sample of recent log lines. If the log tail happens to not contain "=== Paper Scan" lines, scanCount will be 0.

**Root cause:** Same as Issue 4 -- `RAILWAY_BACKEND_URL` not configured. Additionally, the normalization logic is fragile (depends on parsing log lines for scan counts and signal counts).

**Fix needed:**
1. **Environment:** Set `RAILWAY_BACKEND_URL` (same as Issue 4).
2. **File:** `components/trading/TradingDashboard.tsx` (lines 1789-1825) -- The `normalizePaperStatus` function should request structured data from Railway instead of parsing log lines. The Railway backend should return structured fields like `scan_count`, `signals_generated`, `portfolio_value`, `positions`, etc.
3. **File:** `app/api/trading/paper-status/route.ts` -- The API calls `/status` which returns `log_available`, `total_lines`, `last_scan`, `last_prices`, `log_tail`. It should also call a dedicated structured status endpoint if available.

**Priority:** HIGH -- Misleading status information.

---

### Issue 7: System Health Shows UNKNOWN

**Component chain:** `SystemHealthDot` > `GET /api/trading/system-health` > Railway `/health` + Hyperliquid APIs

**What happens:**
- `SystemHealthDot` (line 15) reads `data?.status` and displays "Unknown" when it is not "running", "healthy", "degraded", "offline", or "error".
- The system-health API returns `status: "offline"` when Railway is down (which it always is due to missing env var).
- The SystemHealthDot code (line 30) checks `status === "offline"` and would show "Offline" with a red dot -- so the issue is more likely that the API call itself fails entirely and returns no data.
- If the API call fails (network error, 500, etc.), `data` is undefined, `status` falls back to `"unknown"`, and the dot shows gray "Unknown".

**Root cause:** TWO POSSIBLE CAUSES:
1. Same env var issue as Issues 4 and 6.
2. The API may be returning a 500 error (line 147-148 catches errors and returns 500), and the `useQuery` in `SystemHealthDot` uses `.then(r => r.json())` which will try to parse the error response. If the response is not valid JSON, the promise rejects and data stays undefined.

**Fix needed:**
1. **Environment:** Set `RAILWAY_BACKEND_URL`.
2. **File:** `components/SystemHealthDot.tsx` (line 11) -- Add error handling for non-200 responses:
   ```ts
   queryFn: () => fetch("/api/trading/system-health").then((r) => {
     if (!r.ok) throw new Error(`HTTP ${r.status}`);
     return r.json();
   }),
   ```
3. **File:** Same for `AccountSummaryBar.tsx` (line 14) and `TradingModeBanner.tsx` (line 8).

**Priority:** HIGH -- Core system status indicator is non-functional.

---

## Architecture Observations

### 1. Dual Dashboard Problem
The `app/trading/page.tsx` renders BOTH a set of standalone components (AccountSummaryBar, LivePositionsPanel, TradeFeed) AND the full `TradingDashboard` component (via TradingDashboardLoader). The TradingDashboard has its OWN LiveStatusPanel with its own system health, prices, and paper trading panels. This creates:
- **Duplicate API calls** -- Both AccountSummaryBar and LiveStatusPanel fetch system-health.
- **Inconsistent data** -- AccountSummaryBar reads from `/api/trading/performance` (local JSON file), while TradingDashboard's OverviewTab also fetches from `/api/trading/activity`.
- **Confusing UX** -- Users see two different representations of the same data.

### 2. Data Source Fragmentation
There are 4 different data sources, none of which talk to each other:
- `data/trading-data.json` -- Static file with backtest/historical data (has balance, positions, trades).
- `/api/trading/activity` -- Activity log (local JSON, seed data on first load).
- Railway backend -- Live trading status (paper-status, health).
- Hyperliquid API -- Live prices and wallet balance (direct from browser via wagmi, or server-side).

The AccountSummaryBar tries to show "live" data but reads from a static JSON file. The LivePositionsPanel tries to get positions from the activity log, which is an event log, not a position tracker.

### 3. wagmi Wallet Dependency
The `HyperliquidBalance` component is the ONLY component that actually talks to Hyperliquid for account-specific data (balance, positions). But it requires a wagmi wallet connection (MetaMask, etc.). Most beta testers may not have connected their wallet through the browser, making this component invisible.

### 4. Environment Variable Gap
`RAILWAY_BACKEND_URL` is the single most critical env var and it is not set anywhere in the local project or documented in `.env.example`. Three separate API routes depend on it (system-health, paper-status, and kill-switch).

### 5. No Real-Time Position Tracking
There is no mechanism to fetch live positions from the Railway backend or from Hyperliquid via the server. The only position data comes from:
- `data/trading-data.json` (static, from export script)
- `HyperliquidBalance` (client-side, requires wagmi wallet)

Neither is connected to the components that display positions (LivePositionsPanel, AccountSummaryBar).

---

## Recommended Fix Plan

### Phase 1: Critical Environment Fix (30 minutes)
1. **Set `RAILWAY_BACKEND_URL` on Vercel** -- Run: `vercel env add RAILWAY_BACKEND_URL` with the Railway deployment URL. This single fix resolves Issues 4, 6, and 7.
2. **Set `TRADING_MODE=live` on Vercel** if live trading is active.
3. **Add to `.env.example`:**
   ```
   RAILWAY_BACKEND_URL=https://your-railway-app.up.railway.app
   TRADING_MODE=paper
   ```

### Phase 2: Fix AccountSummaryBar Data (1 hour)
**File:** `components/AccountSummaryBar.tsx`

Fix field name mismatches (lines 18-25):
```ts
const balance = performance?.summary?.currentEquity ?? performance?.totalBalance ?? 0;
const dailyPnl = performance?.dailyPnl ?? performance?.summary?.totalPnl ?? 0;
const openPositions = performance?.summary?.openPositions ?? 0;
```

OR add a server-side mapping layer in `/api/trading/performance/route.ts` (line 35):
```ts
return NextResponse.json({
  ...data,
  totalBalance: data.summary?.currentEquity ?? 0,
  dailyPnl: /* compute from dailyReturns */,
  dailyPnlPct: /* compute */,
  openExposure: /* compute from openPositions */,
  openPositions: data.summary?.openPositions ?? 0,
  maxPositions: 5,
  dailyReturns,
  monthlyReturns,
  riskMetrics,
});
```

### Phase 3: Fix LivePositionsPanel (1 hour)
**File:** `app/api/trading/activity/route.ts`

Add `type=positions` handling in the GET handler (after line 589):
```ts
const typeParam = url.searchParams.get("type");

if (typeParam === "positions") {
  // Read from trading-data.json for open positions
  const jsonPath = join(process.cwd(), "data", "trading-data.json");
  if (existsSync(jsonPath)) {
    const raw = readFileSync(jsonPath, "utf-8");
    const tradingData = JSON.parse(raw);
    const positions = (tradingData.openPositions || []).map(p => ({
      asset: p.asset,
      side: p.side?.toLowerCase() || "long",
      entryPrice: p.entry_price,
      currentPrice: p.entry_price + (p.pnl / p.size), // approximate
      size: p.size,
      unrealizedPnl: p.pnl,
      stopLoss: p.stop_loss,
      openedAt: p.entry_time,
    }));
    return NextResponse.json({ positions });
  }
  return NextResponse.json({ positions: [] });
}
```

### Phase 4: Add Hyperliquid Branding (30 minutes)
**File:** `app/trading/page.tsx` -- Add exchange indicator in the header:
```tsx
<div className="flex items-center gap-2">
  <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
    Hyperliquid
  </span>
</div>
```

**File:** `components/AccountSummaryBar.tsx` -- Add exchange badge at the start of the bar:
```tsx
<div>
  <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium">
    Hyperliquid {health?.components?.find(c => c.name === "Hyperliquid Mainnet")?.status === "healthy" ? "Connected" : ""}
  </span>
</div>
```

### Phase 5: Add Error Handling to React Query Fetches (30 minutes)
**Files:** All components using `useQuery` with `fetch().then(r => r.json())`:
- `AccountSummaryBar.tsx` (lines 8, 14)
- `SystemHealthDot.tsx` (line 11)
- `TradingModeBanner.tsx` (line 8)
- `LivePositionsPanel.tsx` (line 19)
- `TradeFeed.tsx` (line 20)

Change all fetch patterns to handle HTTP errors:
```ts
queryFn: async () => {
  const r = await fetch("/api/trading/...");
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
},
```

### Phase 6: Live Price Reliability (1 hour)
**File:** `app/api/trading/live-prices/route.ts` -- Add retry logic and increase timeout.
**File:** `components/trading/TradingDashboard.tsx` (line 2076) -- Fix the "BTC must exist" check to "any price must exist".

### Priority Summary

| Priority | Issue | Fix Phase | Effort |
|----------|-------|-----------|--------|
| CRITICAL | #2 Balance $0 | Phase 2 | 1 hour |
| CRITICAL | #3 Positions 0 | Phase 3 | 1 hour |
| CRITICAL | #4 Bot OFFLINE | Phase 1 | 30 min |
| HIGH | #1 No branding | Phase 4 | 30 min |
| HIGH | #5 Prices unavailable | Phase 1 + 6 | 1 hour |
| HIGH | #6 Paper STOPPED | Phase 1 | 30 min (same fix as #4) |
| HIGH | #7 Health UNKNOWN | Phase 1 + 5 | 30 min |

**Total estimated effort: ~5 hours for all fixes.**

The single highest-impact action is setting `RAILWAY_BACKEND_URL` on Vercel, which immediately fixes Issues 4, 6, and 7.
