# Frontend Engineer Review Report

**Reviewer**: Agent 03 - Frontend Engineer  
**Date**: 2026-04-01  
**Scope**: Next.js frontend — components, hooks, stores, routes, auth, build config  
**Total component files audited**: 47  

---

## 1. Recent Fixes Verification

### 1.1 TradingModeBanner.tsx — PASS

**File**: `components/TradingModeBanner.tsx`

Reads `NEXT_PUBLIC_TRADING_MODE` env var at module scope (line 3), defaults to `"paper"`. Simple and correct.

**Edge cases**:
- WARN: The env var is read at module scope in a `"use client"` component. In Next.js, `NEXT_PUBLIC_*` vars are inlined at build time. If the env var changes post-build, the banner will NOT update until a rebuild. This is expected Next.js behavior but should be documented — operators must rebuild/redeploy to switch modes.
- No runtime reactivity to env changes. Acceptable for a deployment-level toggle.

**Verdict**: PASS

### 1.2 DashboardShell.tsx — PASS (with note)

**File**: `components/trading/DashboardShell.tsx`

Import chain: `DashboardShell` imports `ChartSection` from `@/components/trading/ChartSection` (line 4). `ChartSection` dynamically imports `MarketChart` with `ssr: false` (line 10-14). `MarketChart` is a named export (`export const MarketChart = memo(MarketChartInner)` at line 69 of `MarketChart.tsx`), and the dynamic import correctly extracts it via `.then((mod) => mod.MarketChart)`.

The old `EquityCurve` component still exists at `components/trading/EquityCurve.tsx` (orphaned) but is no longer imported in `DashboardShell`. The comment on line 18 still says "Equity Curve" but the component is `ChartSection` which contains both equity and market tabs.

**Verdict**: PASS — import chain is correct. Minor: stale comment on line 18.

### 1.3 useHyperliquidData.ts — placeholderData — PASS

**File**: `hooks/useHyperliquidData.ts:140`

```ts
placeholderData: (prev) => prev,
```

This is the correct TanStack Query v5 pattern (formerly `keepPreviousData`). With `@tanstack/react-query@^5.95.2`, the `placeholderData` callback receiving `previousData` is the documented approach. Prevents UI flicker on refetch.

**Verdict**: PASS

---

## 2. Component Architecture

### 2.1 Import/Export Audit — PASS

All 47 component files have valid exports. No missing exports detected. Named exports and default exports are consistent with their import sites.

### 2.2 Dynamic Import Chain — PASS

Three dynamic imports found, all correct:

| File | Target | SSR | Named export extraction |
|------|--------|-----|------------------------|
| `ChartSection.tsx:10` | `MarketChart` | `false` | `.then(mod => mod.MarketChart)` |
| `TradingDashboardLoader.tsx:5` | `TradingDashboard` | `false` | default export (none needed) |
| `TradingSettingsLoader.tsx:5` | `TradingSettings` | `false` | default export (none needed) |

All three disable SSR correctly — `TradingDashboard` uses `localStorage`, `TradingSettings` likely does too, and `MarketChart` injects TradingView scripts into the DOM.

### 2.3 TradingView Widget — PASS (with note)

**File**: `components/trading/MarketChart.tsx`

The widget injects a `<script>` tag with inline JSON config. The `useEffect` cleanup (line 52-55) clears `container.innerHTML` on unmount or when `symbol`/`interval`/`theme` change. This is the standard TradingView embed pattern.

WARN: No error handling if the TradingView CDN script fails to load. Users on restricted networks will see a blank chart with no feedback.

### 2.4 Page Routes — PASS

| Route | Component | Notes |
|-------|-----------|-------|
| `/` | `TradingDashboardLoader` | Wrapped in `ErrorBoundary` |
| `/login` | Login page | Excluded from auth middleware |
| `/trading` | `DashboardShell` + `TradingDashboardLoader` | Renders both shells (see WARN below) |
| `/trading/settings` | `TradingSettingsLoader` | OK |
| `/trading/decisions` | `DecisionsPage` | Client-side with mock fallback |
| `/trading/arena` | `ArenaPanel` | OK |
| `/trading/config` | `ConfigPanel` | OK |
| `/trading/stats` | `TradingStats` | OK |
| `/settings` | Redirect to `/trading/settings` | OK |

WARN: `/trading/page.tsx` renders BOTH `DashboardShell` and `TradingDashboardLoader`. This means the `/trading` route shows the `DashboardShell` (with `ChartSection`, `HeroMetrics`, `PositionsTable`, `RecentDecisions`, `LiveStatusPanel`) AND below it the full `TradingDashboard` (with Overview tab containing its own `HyperliquidBalance`, `LiveStatusPanel`, equity curve, etc.). This creates duplicate widgets on the page — two `LiveStatusPanel` instances, two sets of hero metrics. Likely an incremental migration artifact.

**Recommendation**: Remove either `DashboardShell` or `TradingDashboardLoader` from `/trading/page.tsx` to avoid duplicate content.

---

## 3. State Management

### 3.1 Zustand Stores — WARN

**File**: `stores/viewMode.ts`

Only ONE Zustand store found (`viewMode`). The board presentation claims 4 stores. This is a discrepancy.

The store uses `persist` middleware with `localStorage` key `"aifred-view-mode"`. Correct implementation, no SSR issues because it's only used in `"use client"` components.

**Verdict**: WARN — Only 1 store exists, not 4 as claimed. Either the other 3 were removed/never built, or the board claim is inaccurate.

### 3.2 TanStack Query Provider — PASS

**File**: `components/Providers.tsx`

`QueryClient` is created inside `useState` (line 8) to avoid re-creation on re-renders. Default `staleTime: 5_000` and `retry: 1`. This is correct.

Provider hierarchy in `app/layout.tsx`:
```
SessionProvider > QueryClientProvider > Web3Provider (WagmiProvider) > children
```

No duplicate providers detected. The `Web3Provider` wraps children separately, which is fine.

### 3.3 Provider Note — WARN

`WagmiProvider` is inside `QueryClientProvider`, but Wagmi v2 typically expects its own internal `QueryClientProvider`. Since Wagmi is being used here (via `@wagmi/core`), there could be a conflict if Wagmi's internal React Query instance clashes with the app-level one. This should be tested but may work fine if Wagmi uses the nearest provider.

---

## 4. Build Health

### 4.1 ignoreBuildErrors — PASS

**File**: `next.config.ts:5`

```ts
typescript: { ignoreBuildErrors: false }
```

Confirmed `false`. TypeScript errors will fail the build. Good.

### 4.2 SSR Compatibility — PASS

All components using browser APIs (`localStorage`, DOM injection) are either:
- Marked `"use client"` AND loaded via `dynamic(() => ..., { ssr: false })`, or
- Guarded with `typeof window === "undefined"` checks (e.g., `TradingDashboard.tsx:79`)

### 4.3 Orphaned Components — INFO

`components/trading/EquityCurve.tsx` is exported but not imported anywhere in the app. Dead code. Should be removed.

---

## 5. Auth & Security

### 5.1 Middleware — PASS

**File**: `middleware.ts`

- Auth coverage: All `/api/trading/*` routes and all dashboard pages (`/`, `/trading/*`, `/settings/*`) are protected.
- Fail-closed: If `NEXTAUTH_SECRET` is missing, returns 500 (line 35-39). Good.
- JWT-based auth via `getToken()`.
- Login page and `/api/auth/*` are correctly excluded.

### 5.2 Rate Limiting — PASS (with caveats)

Three rate limit tiers:
- `/api/trading/execute` POST: 1 per 10 seconds
- `/api/trading/autoscan` POST: 1 per 60 seconds
- All other `/api/trading/*`: 10 per 60 seconds

WARN: In-memory `Map` (line 6) resets on serverless cold starts (Vercel). For a single-user app this is acceptable but won't protect against sustained abuse across cold starts.

WARN: The general rate limit of 10 req/min for all `/api/trading/*` may be too aggressive. The dashboard auto-polls `/api/trading/activity` every 10 seconds (ActivityTab.tsx:96) plus `/api/trading/hyperliquid` every 12 seconds (useHyperliquidData.ts:137), plus potentially `/api/trading/system-health`, `/api/trading/paper-status`, etc. A single user with the dashboard open could hit 10 requests/minute easily. This would cause 429 errors during normal usage.

**Recommendation**: Either increase the general limit to 30-60/min or exempt GET requests from the general limit.

### 5.3 NextAuth Config — PASS

**File**: `lib/auth.ts`

- Credentials provider with bcrypt password hashing.
- Fails at import time if `NEXTAUTH_SECRET` is missing (line 5-8).
- JWT session strategy, 24h max age.
- Custom sign-in page at `/login`.

### 5.4 Hardcoded Wallet Address — FAIL

**File**: `hooks/useHyperliquidData.ts:58, 149`  
**File**: `app/api/trading/hyperliquid/route.ts:8`  
**File**: `app/api/trading/positions/route.ts:7`

The Hyperliquid wallet address `0xbec07623d9c8209E7F80dC7350b3aA0ECBdCb510` is hardcoded in 4 locations. The `_address` parameter in `useHyperliquidData` (line 133) is accepted but completely ignored — the function always uses the hardcoded address (line 58) and returns it (line 149).

**Impact**: The wallet connect feature (`ConnectWallet`, `useHyperliquidWithWallet`) passes the connected address, but it is never used. This is misleading to users who connect their own wallet expecting to see their own balances.

**Recommendation**: Use the `_address` parameter or an env var (`NEXT_PUBLIC_HL_ADDRESS`) instead of hardcoding. The fallback in the direct API call should use the passed address.

---

## 6. Math.random() Audit (QA-032)

### Summary

| Category | Count | Severity |
|----------|-------|----------|
| ID generation (non-cryptographic) | 9 | LOW |
| Fake/seed data generation | 14 | HIGH |
| Algorithm logic (strategy selection, confidence, slippage) | 5 | CRITICAL |
| K-means++ initialization (HMM) | 3 | LOW |

### 6.1 ID Generation — LOW risk

Used for generating activity/decision/order IDs in the format `act_<timestamp>_<random>`. Not security-sensitive (IDs are not used for auth or access control). Files:
- `app/api/trading/activity/route.ts:86`
- `app/api/trading/brokers/route.ts:31`
- `app/api/trading/autoscan/route.ts:129`
- `app/api/trading/decisions/route.ts:67`
- `app/api/trading/controls/route.ts:38`
- `lib/record-decision.ts:88`
- `lib/execute-trade.ts:185, 857`
- `components/trading/TradingDashboard.tsx:91`

### 6.2 Fake Data Generation — HIGH risk (user-facing)

These generate synthetic data that is displayed to users:

| File | Line(s) | What it fakes | User-visible? |
|------|---------|---------------|---------------|
| `app/api/trading/activity/route.ts` | 194, 201, 204, 207, 213-214, 216, 221-222, 225, 271, 274, 278 | Technical signals (RSI, MACD), sentiment scores (FinBERT, Fear & Greed), risk metrics (Kelly, R:R), scan results, timestamps | YES - shown in Activity tab as "Agent Reasoning" |
| `app/api/trading/decisions/route.ts` | 144 | Confidence percentages | YES - shown in decision cards |
| `app/trading/decisions/page.tsx` | 49, 53, 56-57, 60 | Mock decision duration, RSI, FinBERT, Kelly, confidence | YES - fallback mock data on decisions page |
| `app/api/trading/brokers/test/route.ts` | 145 | Mock latency delay | NO - test endpoint only |

**Impact**: The `generateTechnicalSignals()`, `generateSentimentSignals()`, and `generateRiskAssessment()` functions in `activity/route.ts` (lines 193-228) are called via `enrichTradeDetails()` to backfill missing signal data on REAL trade entries (line 631-634 of the POST handler). This means when a trade is logged without explicit technical/sentiment/risk data, the API generates RANDOM fake analysis and stores it alongside the real trade. Users see fabricated RSI values, FinBERT scores, and Kelly sizing that have no basis in reality.

**Recommendation**: Remove the random enrichment functions. If signal data is unavailable, display "N/A" or "Not available" instead of generating fake numbers.

### 6.3 Algorithm Logic — CRITICAL

These affect actual trading decisions:

| File | Line | Usage | Impact |
|------|------|-------|--------|
| `lib/strategy-learning.ts:55` | Strategy selection via weighted random sampling | Determines which strategy is chosen for the next trade. Legitimate use of randomness for exploration. |
| `lib/strategy-learning.ts:66` | Confidence fallback: `70 + Math.random() * 15` | When a strategy has fewer than 5 trades, confidence is randomly assigned 70-85%. This directly affects position sizing and trade execution thresholds. |
| `lib/strategy-learning.ts:71` | Confidence variation: `(Math.random() - 0.5) * 6` | Adds +/-3% noise to computed confidence. Minor but affects threshold decisions. |
| `lib/backtester.ts:231` | Neutral regime confidence: `0.4 + Math.random() * 0.15` | Backtester regime detection uses random confidence for neutral markets. Affects backtest results. |
| `lib/execute-trade.ts:230` | Slippage noise: `1 + (Math.random() - 0.5) * 0.4` | Simulated slippage calculation includes random multiplier (0.8x-1.2x). Used in paper trading mode. Legitimate for simulation realism. |

**Verdict**: `strategy-learning.ts:66` is the most concerning — it assigns arbitrary confidence to new strategies, which could cause trades to execute (or not) based on a coin flip.

### 6.4 K-means++ Initialization — LOW risk

**File**: `lib/hmm-regime.ts:141, 159, 169`

Standard k-means++ centroid initialization for HMM regime detection. Legitimate and expected use of randomness in machine learning.

### 6.5 Client-side Fallback IDs — LOW risk

| File | Line | Usage |
|------|------|-------|
| `components/trading/tabs/OverviewTab.tsx:273` | Fallback ID for entries missing `id` field |
| `components/trading/tabs/ActivityTab.tsx:43` | Fallback ID for entries missing `id` field |
| `components/trading/TradingDashboard.tsx:91` | Local trade entry ID generation |

These are React key generation fallbacks, not affecting data integrity.

---

## 7. Additional Findings

### 7.1 Duplicate Content on /trading — WARN

As noted in 2.4, the `/trading` page renders both `DashboardShell` and `TradingDashboardLoader`, resulting in duplicate `LiveStatusPanel`, duplicate hero metrics, and potentially confusing UX.

**File**: `app/trading/page.tsx:30-34`

### 7.2 Hardcoded Wallet Address Ignored — FAIL

The `_address` parameter in `useHyperliquidData` is prefixed with underscore (indicating unused) and is indeed never used. The hook always queries the hardcoded address. See section 5.4.

### 7.3 Memory Leak in ActivityTab — WARN

**File**: `components/trading/tabs/ActivityTab.tsx:94-98`

```ts
useEffect(() => {
    fetchActivities();
    const interval = setInterval(fetchActivities, 10_000);
    return () => clearInterval(interval);
}, []);
```

The `fetchActivities` function is not wrapped in `useCallback` and is not in the dependency array. While the empty deps array means this runs once (which is the intent), ESLint's `exhaustive-deps` rule would flag this. The function captures `mergeWithLocal` which captures component state, so this could reference stale closures. In practice, since `setActivities` and `setExpandedId` are stable, this works but is fragile.

### 7.4 Rate Limit vs Polling Conflict — WARN

See section 5.2. The 10 req/min general rate limit will conflict with normal dashboard polling behavior.

### 7.5 TradingView CDN Dependency — INFO

**File**: `components/trading/MarketChart.tsx:29`

The chart depends on `https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js`. No fallback or error state if this CDN is unreachable.

---

## Summary Table

| Area | Status | Critical Issues |
|------|--------|----------------|
| TradingModeBanner env var | PASS | Build-time only (expected) |
| DashboardShell ChartSection swap | PASS | Clean import chain |
| useHyperliquidData placeholderData | PASS | Correct TanStack v5 pattern |
| Component exports/imports | PASS | All 47 files clean |
| Dynamic imports / SSR | PASS | All 3 correct |
| Zustand stores (1, not 4) | WARN | Board presentation discrepancy |
| TanStack Query provider | PASS | Correct setup |
| Build config | PASS | ignoreBuildErrors: false |
| Auth middleware coverage | PASS | All routes protected |
| Rate limiting | WARN | Too aggressive for polling; resets on cold start |
| Hardcoded wallet address | FAIL | _address param ignored, hardcoded in 4 files |
| Math.random fake data (QA-032) | FAIL | Fake signals injected into real trade records |
| Math.random in algo logic | WARN | Arbitrary confidence for new strategies |
| Duplicate content /trading | WARN | Two dashboards rendered on same page |
| Orphaned EquityCurve component | INFO | Dead code |

### Top 3 Action Items

1. **FAIL**: Remove `Math.random()` enrichment in `app/api/trading/activity/route.ts` lines 193-228. Never inject fabricated analysis into real trade records. Display "N/A" for missing data.
2. **FAIL**: Fix `useHyperliquidData` to use the `_address` parameter (or an env var) instead of hardcoding the wallet address in 4 files.
3. **WARN**: Resolve duplicate dashboard rendering in `app/trading/page.tsx` — choose either `DashboardShell` or `TradingDashboardLoader`, not both.
