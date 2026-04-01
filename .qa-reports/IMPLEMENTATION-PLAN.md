# AIFred Trading Platform -- UI/UX Overhaul Implementation Plan

**Version:** 1.0
**Date:** 2026-04-01
**Authors:** Backend Architect, Frontend Lead, Quant Engineer, AI/ML Engineer
**Timeline:** 12 weeks (6 sprints x 2 weeks)
**Reference:** nofx-analysis.md, nofx-frontend-patterns.md, COMPETITIVE-ANALYSIS.md

---

## Guiding Principles

1. **LIVE data first.** Every screen defaults to real Hyperliquid data. The $10.80 USDC balance at `0xbec07623d9c8209E7F80dC7350b3aA0ECBdCb510` must render correctly on first load.
2. **Stability over features.** No flickering, no stale cache, no mode inconsistency. If a feature cannot be made stable in its sprint, it ships disabled behind a feature flag.
3. **Incremental delivery.** Each sprint produces a deployable increment. No sprint depends on a future sprint being complete.
4. **Preserve existing strengths.** Wallet-native auth, 7-agent ensemble, kill switch, regime detection, 5-layer risk management -- these stay and get better UI treatment.

---

## Current State Inventory

**Pages:** 3 (`/`, `/trading`, `/trading/settings`)
**Components:** 23 files across `components/`
**API routes:** 18 endpoints under `app/api/trading/`
**Stack:** Next.js 16, React 19, TanStack Query, Tailwind 4, lightweight-charts 5, Recharts 3, Framer Motion, wagmi/viem
**Missing packages:** Zustand, @tanstack/react-table, date-fns, sonner (all needed)
**Deployment:** Vercel (frontend) + Railway (backend agents)

---

## Sprint 1 (Weeks 1-2): Dashboard Overhaul -- "The Money Shot"

### Objective
Replace the current tab-based trading page with a professional multi-section dashboard that shows real Hyperliquid data prominently. This is what investors and users see first. It must be rock-solid.

### 1.1 New Components

| Component | File Path | Props | Data Source |
|-----------|-----------|-------|-------------|
| `AppShell` | `components/layout/AppShell.tsx` | `children` | N/A (layout wrapper) |
| `Sidebar` | `components/layout/Sidebar.tsx` | `activePath` | Next.js `usePathname()` |
| `NavItem` | `components/layout/NavItem.tsx` | `href, icon, label, active` | N/A |
| `HeroMetrics` | `components/dashboard/HeroMetrics.tsx` | `equity, availableBalance, totalPnl, pnlPercent, positionCount, marginPercent` | `useHyperliquidWithWallet()` hook |
| `EquityCurve` | `components/charts/EquityCurve.tsx` | `data[], timeRange, viewMode('usd'\|'pct')` | `GET /api/trading/equity-history` (new) |
| `PositionsTable` | `components/positions/PositionsTable.tsx` | `positions[]` | `useHyperliquidWithWallet()` |
| `PositionRow` | `components/positions/PositionRow.tsx` | `position, onClose, onModify` | Parent props |
| `PositionActions` | `components/positions/PositionActions.tsx` | `positionId, symbol, side` | Parent props |
| `DashboardPage` | `app/dashboard/page.tsx` | N/A (page) | Orchestrates all above |

**Layout architecture:**

```
app/(authenticated)/layout.tsx   -- AppShell with Sidebar
app/(authenticated)/dashboard/page.tsx
app/(authenticated)/config/page.tsx      (shell, Sprint 4)
app/(authenticated)/stats/page.tsx       (shell, Sprint 3)
app/(authenticated)/competition/page.tsx (shell, Sprint 5)
```

The `(authenticated)` route group wraps all logged-in pages with the sidebar layout. The existing `/trading` route redirects to `/dashboard`.

### 1.2 API Endpoints

| Method | Path | Purpose | Backend |
|--------|------|---------|---------|
| `GET` | `/api/trading/equity-history` | Historical equity snapshots for curve | Read from Hyperliquid account value snapshots + local storage of periodic samples |
| `GET` | `/api/trading/positions/close` | Close a position by symbol | Proxy to Hyperliquid SDK `closePosition()` |
| `PATCH` | `/api/trading/positions/modify` | Modify TP/SL on position | Proxy to Hyperliquid SDK `modifyOrder()` |

The equity history endpoint records account value every 5 minutes into a JSON file (later Supabase table). This is critical -- without historical snapshots, there is no equity curve.

**Equity snapshot worker:** Add a `setInterval` in the trading API route (or a Railway cron) that calls Hyperliquid `getAccountState()` every 5 minutes and appends `{ timestamp, equity, availableBalance }` to persistent storage.

### 1.3 State Management Changes

**Install Zustand** (`npm install zustand`):

| Store | File | State | Purpose |
|-------|------|-------|---------|
| `useUIStore` | `lib/stores/useUIStore.ts` | `sidebarCollapsed, activeModal, viewMode('live'\|'demo'), timeRange` | Global UI coordination |
| `useDashboardStore` | `lib/stores/useDashboardStore.ts` | `selectedPosition, chartTimeRange, equityViewMode` | Dashboard-local state |

**Refactor `AccountSummaryBar`:** Extract the `viewMode` toggle logic into `useUIStore` so it is accessible across all pages. The current `useState` in `AccountSummaryBar.tsx` means mode resets on navigation.

**TanStack Query keys:** Standardize all query keys to a `queryKeys` factory:
```typescript
// lib/queryKeys.ts
export const queryKeys = {
  positions: ['positions'] as const,
  equity: (range: string) => ['equity', range] as const,
  performance: ['performance'] as const,
  health: ['system-health'] as const,
  stats: ['stats'] as const,
};
```

### 1.4 Third-Party Integrations

| Package | Purpose | Install |
|---------|---------|---------|
| `zustand` | Global state | `npm install zustand` |
| `sonner` | Toast notifications (replace ad-hoc alerts) | `npm install sonner` |
| `date-fns` | Date formatting for equity curve, trade durations | `npm install date-fns` |

### 1.5 LIVE/PAPER Stability Fix

**Root cause:** The `AccountSummaryBar` flickers because `viewMode` is local state that resets on re-render, and the `useHyperliquidWithWallet` hook returns `connected: false` briefly during hydration.

**Fix:**
1. Move `viewMode` to Zustand store with `persist` middleware (survives page refreshes).
2. Add `isHydrated` gate: do not render metrics until TanStack Query returns its first successful response. Show skeleton loader instead.
3. Wrap the mode toggle with `startTransition` to prevent layout shift.
4. Default to LIVE mode. If Hyperliquid connection fails after 3 retries, show a connection error banner instead of silently falling back to demo data.
5. Remove all `Math.random()` from paper trade PnL calculations (QA-032). Paper mode must use last known prices from `/api/trading/prices`.

### 1.6 Remove Demo Data from Default View

- Delete or gate all references to `trading-data.json` behind `viewMode === 'demo'`.
- The `performance` query (`/api/trading/performance`) currently returns simulated data. Add a `source` field to the response: `{ source: 'live' | 'demo', ... }`. Dashboard ignores responses where `source !== viewMode`.
- `OverviewTab` area chart: replace with `EquityCurve` component reading real equity history.

### 1.7 Dependencies on Other Sprints

None. Sprint 1 is the foundation. All subsequent sprints depend on the AppShell and navigation established here.

### 1.8 Acceptance Criteria

- [ ] Dashboard loads in under 2 seconds on Vercel production.
- [ ] Hero metrics show real Hyperliquid data: Total Equity ($10.80 USDC), Available Balance, Total P&L, Position Count.
- [ ] Equity curve renders with at least 24 hours of data points (5-minute intervals = 288 points).
- [ ] Positions table shows: Symbol, Side (color-coded), Entry Price, Mark Price, QTY, Leverage, Unrealized P&L (color-coded), Liquidation Price.
- [ ] Close button on each position sends close order to Hyperliquid and reflects in table within 5 seconds.
- [ ] No flickering on page load. Skeleton loaders show during data fetch.
- [ ] LIVE/PAPER toggle persists across page navigations and browser refresh.
- [ ] Sidebar navigation with active state highlighting works for all route shells.
- [ ] `/trading` redirects to `/dashboard`.
- [ ] `next build` passes with zero errors.

### 1.9 Risk Factors

| Risk | Mitigation |
|------|------------|
| Hyperliquid rate limits on frequent position queries | Cache with 5s stale time in TanStack Query; do not poll faster than 5s |
| Equity history has no data on first deploy | Seed with current balance as single data point; curve grows over time |
| SSR hydration mismatch with wallet state | Use `dynamic(() => import(...), { ssr: false })` for all wallet-dependent components |
| Close position fails silently | Show sonner toast with error details; add retry button |

### 1.10 Team Assignment

| Agent | Responsibility |
|-------|---------------|
| **Frontend Lead** | AppShell, Sidebar, NavItem, page routing, navigation |
| **Backend Architect** | Equity history endpoint, position close/modify endpoints, equity snapshot worker |
| **Quant Engineer** | HeroMetrics calculations (margin %, exposure), PositionsTable column logic (liquidation price calc) |
| **AI/ML Engineer** | Zustand store setup, TanStack Query refactor, LIVE/PAPER stability fix |

---

## Sprint 2 (Weeks 3-4): AI Decision Transparency

### Objective
Expose the 7-agent system's reasoning process to users. This is AIFred's key differentiator -- no competitor shows chain-of-thought. Users and investors must see WHY trades happen, not just THAT they happen.

### 2.1 New Components

| Component | File Path | Props | Data Source |
|-----------|-----------|-------|-------------|
| `DecisionCard` | `components/decisions/DecisionCard.tsx` | `decision: DecisionRecord` | `/api/trading/decisions` |
| `ActionCard` | `components/decisions/ActionCard.tsx` | `action: DecisionAction, index` | Parent props |
| `ReasoningExpander` | `components/decisions/ReasoningExpander.tsx` | `title, content, accentColor, onCopy, onDownload` | Parent props |
| `DecisionTimeline` | `components/decisions/DecisionTimeline.tsx` | `decisions[], loading` | `/api/trading/decisions` |
| `RecentDecisions` | `components/dashboard/RecentDecisions.tsx` | `limit` | `/api/trading/decisions?limit=5` |

**DecisionCard anatomy (matching NOFX pattern):**
```
+--------------------------------------------------+
| Cycle #42  |  2026-04-01 14:30:00  |  SUCCESS    |
+--------------------------------------------------+
| Action: OPEN_LONG ETH-USD                        |
| Entry: $3,245.00  SL: $3,180.00  TP: $3,380.00  |
| Leverage: 3x  R:R: 2.8                           |
| Confidence: 87% [=========>  ]                   |
+--------------------------------------------------+
| > System Prompt  [Copy] [Download]    (purple)   |
| > Market Data Input  [Copy] [Download] (blue)    |
| > AI Reasoning (CoT)  [Copy] [Download] (gold)   |
| > Execution Log                        (gray)    |
+--------------------------------------------------+
```

### 2.2 API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/trading/decisions` | Paginated decision history with full audit trail |
| `GET` | `/api/trading/decisions/[cycleId]` | Single cycle detail with all prompts and reasoning |

**Decision record schema:**
```typescript
interface DecisionRecord {
  id: string;
  cycleNumber: number;
  timestamp: string;
  success: boolean;
  agentContributions: {
    agent: string;           // 'technical-analysis' | 'sentiment' | 'risk' | etc.
    signal: string;          // 'LONG' | 'SHORT' | 'HOLD'
    confidence: number;      // 0-100
    reasoning: string;       // Agent-specific reasoning
  }[];
  fusionResult: {
    direction: string;
    confidence: number;
    reasoning: string;       // Meta-learner's chain-of-thought
  };
  actions: DecisionAction[];
  systemPrompt: string;
  inputPrompt: string;
  cotTrace: string;          // Full chain-of-thought from meta-learner
  executionLog: string[];
  error?: string;
}
```

**Backend requirement:** The Python agent pipeline must be modified to persist `systemPrompt`, `inputPrompt`, and `cotTrace` for every decision cycle. Currently these exist in memory but are not saved. Store them in the trading activity log or a dedicated decisions file/table.

### 2.3 State Management Changes

Add to `useDashboardStore`:
```typescript
expandedDecisionId: string | null;
decisionFilter: 'all' | 'success' | 'error';
```

### 2.4 Third-Party Integrations

None new. Uses existing Framer Motion for expand/collapse animations and Lucide for icons.

### 2.5 Dependencies

- Sprint 1 (AppShell, Sidebar, dashboard page must exist).
- Backend agent pipeline must be updated to persist decision audit trail.

### 2.6 Acceptance Criteria

- [ ] Recent Decisions panel on dashboard shows last 5 decisions with expand/collapse.
- [ ] Each decision card shows: cycle number, timestamp, success/fail badge, action summary.
- [ ] Expanding a decision reveals 3 collapsible sections: System Prompt, Market Data, AI Reasoning.
- [ ] Each section has working Copy and Download buttons.
- [ ] Confidence scores are color-coded: green >= 80%, yellow >= 60%, red < 60%.
- [ ] Multi-agent contributions visible: which agents signaled LONG/SHORT/HOLD and their individual confidence.
- [ ] `/api/trading/decisions` returns paginated results (20 per page) sorted newest-first.
- [ ] Decision data persists across server restarts (not in-memory only).
- [ ] Skeleton loader while decisions fetch.

### 2.7 Risk Factors

| Risk | Mitigation |
|------|------------|
| Agent pipeline does not currently persist prompts/CoT | Add file-based logging immediately; migrate to Supabase later |
| CoT text can be very long (5000+ tokens) | Truncate to 500 chars in list view; full text in expanded view |
| No decisions exist yet (new deployment) | Show empty state: "No decisions yet. Start the trading agent to see AI reasoning here." |

### 2.8 Team Assignment

| Agent | Responsibility |
|-------|---------------|
| **AI/ML Engineer** | Modify Python agent pipeline to persist decision audit trail; design DecisionRecord schema |
| **Frontend Lead** | DecisionCard, ActionCard, ReasoningExpander components |
| **Backend Architect** | `/api/trading/decisions` endpoint with pagination and filtering |
| **Quant Engineer** | Confidence score calculation; agent contribution aggregation logic |

---

## Sprint 3 (Weeks 5-6): Trading Stats & History

### Objective
Build a dedicated statistics page with comprehensive trading metrics. Investors need to see win rate, Sharpe ratio, profit factor, and per-symbol performance to assess the platform.

### 3.1 New Components

| Component | File Path | Props | Data Source |
|-----------|-----------|-------|-------------|
| `StatsPage` | `app/(authenticated)/stats/page.tsx` | N/A | Orchestrator |
| `StatsGrid` | `components/stats/StatsGrid.tsx` | `stats: TradingStats` | `/api/trading/stats/overview` |
| `DirectionBreakdown` | `components/stats/DirectionBreakdown.tsx` | `longStats, shortStats` | `/api/trading/stats/by-direction` |
| `SymbolPerformance` | `components/stats/SymbolPerformance.tsx` | `symbols[]` | `/api/trading/stats/by-symbol` |
| `TradeHistoryTable` | `components/stats/TradeHistoryTable.tsx` | `trades[], filters, sorting` | `/api/trading/stats/trade-history` |
| `StatCard` | `components/stats/StatCard.tsx` | `label, value, change, tooltip` | Parent props |

**StatsGrid layout (3x4 grid):**
```
| Total Trades | Win Rate    | Total P&L    |
| Profit Factor| P/L Ratio   | Sharpe Ratio |
| Max Drawdown | Avg Win     | Avg Loss     |
| Net P&L      | Best Trade  | Worst Trade  |
```

### 3.2 API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/trading/stats/overview` | Aggregate stats: win rate, Sharpe, profit factor, max DD, etc. |
| `GET` | `/api/trading/stats/by-direction` | LONG vs SHORT breakdown |
| `GET` | `/api/trading/stats/by-symbol` | Per-symbol P&L, win rate, trade count |
| `GET` | `/api/trading/stats/trade-history` | Paginated, filterable closed trade history |

**Query params for trade-history:**
```
?page=1&limit=20&symbol=ETH-USD&side=long&sortBy=pnl&sortOrder=desc&from=2026-01-01&to=2026-04-01
```

**Stats calculation (Quant Engineer):**

All stats computed server-side from closed trade records:
- **Win Rate:** `wins / totalTrades * 100`
- **Profit Factor:** `grossProfit / grossLoss` (infinity if no losses)
- **Sharpe Ratio:** `mean(dailyReturns) / std(dailyReturns) * sqrt(252)` (annualized)
- **Max Drawdown:** peak-to-trough from equity history
- **P/L Ratio:** `avgWin / avgLoss`

### 3.3 State Management Changes

No new stores. Use TanStack Query for all stats data. Add query keys:
```typescript
stats: {
  overview: ['stats', 'overview'],
  byDirection: ['stats', 'by-direction'],
  bySymbol: ['stats', 'by-symbol'],
  tradeHistory: (filters) => ['stats', 'trade-history', filters],
}
```

### 3.4 Third-Party Integrations

| Package | Purpose |
|---------|---------|
| `@tanstack/react-table` | Sortable, filterable trade history table | 

Install: `npm install @tanstack/react-table`

### 3.5 Dependencies

- Sprint 1 (AppShell, navigation, `/stats` route shell).
- Requires closed trade data. If no trades have been executed yet, show empty states with explanatory text.

### 3.6 Acceptance Criteria

- [ ] Stats page accessible from sidebar navigation.
- [ ] 12-metric grid renders with real data from closed trades.
- [ ] LONG vs SHORT breakdown shows separate win rate, P&L, and trade count per direction.
- [ ] Symbol performance table shows per-symbol P&L with sorting.
- [ ] Trade history table supports: pagination (20/page), symbol filter, side filter, date range, column sorting.
- [ ] Each trade row shows: Symbol, Side, Entry Price, Exit Price, QTY, P&L (color-coded), Fee, Duration, Closed At.
- [ ] Stats update within 30 seconds of a trade closing.
- [ ] Empty state when no trades exist: "No closed trades yet."
- [ ] All monetary values formatted with proper decimal places and currency symbol.

### 3.7 Risk Factors

| Risk | Mitigation |
|------|------------|
| Insufficient trade data for meaningful Sharpe ratio | Show "Insufficient data" when fewer than 30 trades; require 30+ for Sharpe display |
| Stats computation slow with large trade history | Pre-compute and cache stats; invalidate on new trade close |
| Fee data not tracked per trade | Add fee field to trade recording; backfill as zero for existing trades |

### 3.8 Team Assignment

| Agent | Responsibility |
|-------|---------------|
| **Quant Engineer** | All stats calculation formulas, Sharpe/PF/DD algorithms, stats API logic |
| **Frontend Lead** | StatsGrid, StatCard, DirectionBreakdown, TradeHistoryTable |
| **Backend Architect** | Trade history endpoint with pagination/filtering, data persistence |
| **AI/ML Engineer** | SymbolPerformance aggregation, trade duration calculation |

---

## Sprint 4 (Weeks 7-8): Config & Multi-Model

### Objective
Build the configuration page for managing AI models, exchange connections, and trader instances. This transforms AIFred from a single-bot demo into a multi-model platform.

### 4.1 New Components

| Component | File Path | Props | Data Source |
|-----------|-----------|-------|-------------|
| `ConfigPage` | `app/(authenticated)/config/page.tsx` | N/A | Orchestrator |
| `ModelCard` | `components/config/ModelCard.tsx` | `model: AIModelConfig, onEdit, onRemove` | `/api/config/models` |
| `ModelConfigModal` | `components/config/ModelConfigModal.tsx` | `model?, onSave, onClose` | Form state |
| `ExchangeCard` | `components/config/ExchangeCard.tsx` | `exchange: ExchangeConfig, onEdit` | `/api/config/exchanges` |
| `ExchangeConfigModal` | `components/config/ExchangeConfigModal.tsx` | `exchange?, onSave, onClose` | Form state |
| `TraderCard` | `components/config/TraderCard.tsx` | `trader: TraderInstance, onView, onStop, onDelete` | `/api/traders` |
| `TraderConfigModal` | `components/config/TraderConfigModal.tsx` | `trader?, models[], exchanges[], onSave, onClose` | Form state |
| `ConfigSection` | `components/config/ConfigSection.tsx` | `title, description, addLabel, onAdd, children` | Layout wrapper |

**Config page layout (3 sections, vertical):**
```
+-- AI Models ------------------------------------------+
| [Claude 3.5]  [DeepSeek V3]  [Gemini 2.0]  [+ Add]  |
+-------------------------------------------------------+

+-- Exchanges ------------------------------------------+
| [Hyperliquid: Connected]  [Binance: Not Set]  [+ Add] |
+-------------------------------------------------------+

+-- Active Traders -------------------------------------+
| [Claude + Hyperliquid: Running]  [View] [Stop] [Del]  |
| [DeepSeek + Hyperliquid: Stopped] [View] [Start] [Del]|
| [+ Create Trader]                                      |
+-------------------------------------------------------+
```

### 4.2 API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/config/models` | List configured AI models |
| `POST` | `/api/config/models` | Add AI model (provider, version, API key) |
| `PUT` | `/api/config/models/[id]` | Update model config |
| `DELETE` | `/api/config/models/[id]` | Remove model |
| `GET` | `/api/config/exchanges` | List exchange connections |
| `POST` | `/api/config/exchanges` | Add exchange (type, API key, secret) |
| `PUT` | `/api/config/exchanges/[id]` | Update exchange config |
| `GET` | `/api/traders` | List trader instances |
| `POST` | `/api/traders` | Create trader (modelId + exchangeId + strategyParams) |
| `POST` | `/api/traders/[id]/start` | Start trader |
| `POST` | `/api/traders/[id]/stop` | Stop trader |
| `DELETE` | `/api/traders/[id]` | Delete trader |

**Security:** Exchange API keys must be encrypted client-side before transmission. Use `SubtleCrypto` with a derived key from the user's wallet signature. Store only encrypted blobs server-side. Never log API keys.

### 4.3 State Management Changes

| Store | File | Purpose |
|-------|------|---------|
| `useConfigStore` | `lib/stores/useConfigStore.ts` | Cached models, exchanges, supported providers list; modal open/close state |
| `useTraderStore` | `lib/stores/useTraderStore.ts` | Active traders, selected trader for dashboard view |

### 4.4 Third-Party Integrations

None new beyond what is already installed.

### 4.5 Dependencies

- Sprint 1 (AppShell, navigation).
- Backend multi-trader architecture: the Python agent system needs a `TraderManager` class that can spawn, monitor, and stop independent trader processes. This is the heaviest backend lift in the entire plan.

### 4.6 Acceptance Criteria

- [ ] Config page shows 3 sections: AI Models, Exchanges, Active Traders.
- [ ] Can add a new AI model with provider selection (Claude, DeepSeek, Gemini, GPT, Grok), version, and API key.
- [ ] Model cards show status (active/inactive/error) with visual indicator.
- [ ] Can add a new exchange connection (Hyperliquid pre-configured from wallet).
- [ ] Exchange cards show connection status (connected/disconnected/error).
- [ ] Can create a new trader by selecting a model + exchange combination.
- [ ] Trader cards show: model name, exchange, status (running/stopped), runtime duration.
- [ ] Can start, stop, and delete traders from the card UI.
- [ ] API keys are encrypted before leaving the browser. Server-side logs contain no plaintext keys.
- [ ] Creating a trader with Hyperliquid uses the already-connected wallet -- no re-entry of credentials.

### 4.7 Risk Factors

| Risk | Mitigation |
|------|------------|
| Multi-trader backend is complex and may slip | Phase 1: single trader with the config UI. Phase 2 (Sprint 6): enable multiple simultaneous traders |
| API key encryption adds complexity | Use a well-tested pattern; if timeline is tight, store keys server-side with Railway environment encryption and add client-side encryption in Sprint 6 |
| Users may create traders that conflict (same symbol, opposite directions) | Add a warning modal when conflicting traders are detected; do not block creation |

### 4.8 Team Assignment

| Agent | Responsibility |
|-------|---------------|
| **Backend Architect** | TraderManager class, all config/trader API endpoints, persistence layer |
| **Frontend Lead** | ConfigPage layout, ModelCard, ExchangeCard, TraderCard |
| **AI/ML Engineer** | ModelConfigModal (provider-specific fields), TraderConfigModal (strategy params) |
| **Quant Engineer** | Trader conflict detection, strategy parameter validation |

---

## Sprint 5 (Weeks 9-10): Competition Arena

### Objective
Build the AI competition page where multiple trader instances compete head-to-head. This is the viral growth hook -- shareable leaderboards and AI battles create social proof and engagement.

### 5.1 New Components

| Component | File Path | Props | Data Source |
|-----------|-----------|-------|-------------|
| `CompetitionPage` | `app/(authenticated)/competition/page.tsx` | N/A | Orchestrator |
| `ComparisonChart` | `components/charts/ComparisonChart.tsx` | `traders[], timeRange` | `/api/competition/equity-curves` |
| `Leaderboard` | `components/competition/Leaderboard.tsx` | `rankings[]` | `/api/competition` |
| `HeadToHead` | `components/competition/HeadToHead.tsx` | `traderA, traderB` | `/api/competition` |
| `CompetitionHeader` | `components/competition/CompetitionHeader.tsx` | `traderCount, leader, duration` | `/api/competition` |
| `RankBadge` | `components/competition/RankBadge.tsx` | `rank: 1\|2\|3` | Parent props |

**ComparisonChart implementation:**
- Use Recharts `<LineChart>` with multiple `<Line>` series (one per trader).
- Y-axis: P&L percentage (not absolute) for fair comparison across different starting balances.
- Time period selector: 1D, 3D, 7D, 30D, All.
- Color-coded per trader with legend.
- Top 2 traders get area fill; others are lines only.
- Timestamp normalization: snap all equity points to nearest minute.
- Gap filling: use last known value for missing timestamps.

### 5.2 API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/competition` | Competition state: rankings, leader, trader count |
| `GET` | `/api/competition/equity-curves` | Multi-trader equity history for chart overlay |
| `POST` | `/api/competition/start` | Start a new competition round |

### 5.3 State Management Changes

| Store | File | Purpose |
|-------|------|---------|
| `useCompetitionStore` | `lib/stores/useCompetitionStore.ts` | Selected time range, selected traders for head-to-head, competition active state |

### 5.4 Third-Party Integrations

None new.

### 5.5 Dependencies

- Sprint 1 (AppShell, navigation).
- Sprint 4 (Multi-trader: need 2+ active traders to have a competition). If multi-trader backend is not ready, display simulated competition data from the 7 existing agents' historical signal data.

### 5.6 Acceptance Criteria

- [ ] Competition page accessible from sidebar.
- [ ] Comparison chart shows equity curves for all active traders overlaid.
- [ ] Time period selector (1D, 3D, 7D, 30D, All) filters chart data.
- [ ] Leaderboard table shows: Rank, Trader Name, Model, Exchange, Equity, P&L%, Position Count.
- [ ] Top 3 ranks have animated gold/silver/bronze badges.
- [ ] Leaderboard sorts by P&L% by default; columns are clickable to re-sort.
- [ ] Head-to-head mode activates when user selects exactly 2 traders.
- [ ] Head-to-head shows side-by-side metrics: Equity, P&L, Win Rate, Sharpe, Trades.
- [ ] Data refreshes every 15 seconds via polling.
- [ ] Graceful empty state when fewer than 2 traders exist.

### 5.7 Risk Factors

| Risk | Mitigation |
|------|------------|
| No multi-trader data available | Use the 7 agents' individual signal accuracy as proxy competition data |
| Equity curve data misaligned across traders | Normalize all timestamps to nearest minute; interpolate gaps |
| Chart performance with many traders | Limit chart to top 10 traders; add "Show All" toggle |

### 5.8 Team Assignment

| Agent | Responsibility |
|-------|---------------|
| **Frontend Lead** | ComparisonChart (Recharts multi-line), CompetitionPage layout |
| **Quant Engineer** | Leaderboard ranking algorithm, P&L% normalization, head-to-head metrics |
| **Backend Architect** | Competition API endpoints, equity curve aggregation |
| **AI/ML Engineer** | Agent-as-trader proxy (map 7 agents to competition entries if multi-trader not ready) |

---

## Sprint 6 (Weeks 11-12): Polish & Launch

### Objective
Responsive design, performance optimization, comprehensive QA, and production hardening. No new features -- only refinement.

### 6.1 Responsive Design

| Breakpoint | Layout Change |
|------------|---------------|
| `< 768px` (mobile) | Sidebar collapses to bottom tab bar; HeroMetrics stack vertically; PositionsTable becomes card list; Charts full-width |
| `768-1024px` (tablet) | Sidebar collapses to icon-only rail; 2-column grid for stats |
| `> 1024px` (desktop) | Full sidebar; 3-4 column grids |

**Key responsive components to update:**
- `AppShell`: swap sidebar for bottom tabs on mobile
- `HeroMetrics`: `grid-cols-4` -> `grid-cols-2` on mobile, `grid-cols-1` below 480px
- `PositionsTable`: horizontal scroll with sticky first column on mobile
- `StatsGrid`: `grid-cols-4` -> `grid-cols-2` on mobile
- `TradeHistoryTable`: hide Duration and Fee columns on mobile
- `ComparisonChart`: reduce padding, smaller legend on mobile

### 6.2 Performance Optimization

| Optimization | Target |
|-------------|--------|
| Route-based code splitting | Each page lazy-loaded; initial bundle < 200KB gzipped |
| Chart lazy loading | lightweight-charts and Recharts loaded only when visible (`dynamic` import with `ssr: false`) |
| Image optimization | All icons via Lucide (SVG); no raster images in core UI |
| Query deduplication | TanStack Query structural sharing prevents unnecessary re-renders |
| Stale-while-revalidate | 5s stale time for positions; 30s for equity; 60s for stats |
| Bundle analysis | Run `next build --analyze` (install `@next/bundle-analyzer`); target no single chunk > 150KB |

### 6.3 Final QA Checklist

**Functional testing:**
- [ ] All 5 pages load without errors (Dashboard, Config, Stats, Competition, Settings)
- [ ] Wallet connection flow works end-to-end (connect -> see balance -> trade)
- [ ] Position close executes on Hyperliquid and reflects in UI within 5s
- [ ] Kill switch immediately halts all trading activity
- [ ] Decision audit trail shows real agent reasoning (not placeholder text)
- [ ] Stats calculations match manual verification against raw trade data
- [ ] Navigation works with browser back/forward buttons

**Stability testing:**
- [ ] Dashboard stable for 1 hour continuous use with no memory leaks (check browser DevTools Memory tab)
- [ ] No flickering, no layout shifts, no stale data visible
- [ ] Graceful degradation when Hyperliquid API is slow (> 5s) or down
- [ ] Error boundaries catch and display friendly messages for all component crashes

**Security testing:**
- [ ] No API keys visible in browser DevTools Network tab
- [ ] No sensitive data in server logs
- [ ] CORS configured to reject unauthorized origins
- [ ] Rate limiting on all mutation endpoints (close position, create trader)

**SSR/Hydration testing (per CLAUDE.md):**
- [ ] All Framer Motion animations use `initial={false}` or start at `opacity: 1`
- [ ] No hydration mismatch warnings in console
- [ ] `next build` passes cleanly

### 6.4 Production Hardening

| Item | Action |
|------|--------|
| Error tracking | Add Sentry or LogRocket for client-side error monitoring |
| Uptime monitoring | Railway health check endpoint; Vercel analytics |
| Rate limiting | Add `rateLimit` middleware to mutation API routes (10 req/min for trades) |
| Feature flags | Add `NEXT_PUBLIC_FEATURE_*` env vars for each sprint's features; disable incomplete features in production |
| Database migration | Move from file-based storage to Supabase for equity history, decisions, trade history, config |

### 6.5 Dependencies

All previous sprints must be complete or feature-flagged.

### 6.6 Acceptance Criteria

- [ ] Lighthouse performance score >= 90 on dashboard page.
- [ ] All pages render correctly on iPhone 14 (390px), iPad (768px), and desktop (1440px).
- [ ] Zero console errors or warnings in production build.
- [ ] Full QA checklist above passes.
- [ ] `next build` completes in under 60 seconds.
- [ ] Error boundary displays friendly message (not stack trace) for any component crash.

### 6.7 Risk Factors

| Risk | Mitigation |
|------|------------|
| Previous sprint features have bugs discovered during QA | Reserve 3 days of sprint for bug fixes; defer non-critical bugs to post-launch backlog |
| Bundle size exceeds target | Aggressive code splitting; replace heavy libraries if needed |
| Mobile responsive testing reveals major layout issues | Prioritize dashboard and positions; accept that competition page may be desktop-only for v1 |

### 6.8 Team Assignment

| Agent | Responsibility |
|-------|---------------|
| **Frontend Lead** | Responsive design, Lighthouse optimization, bundle analysis |
| **Backend Architect** | Rate limiting, database migration, production hardening |
| **Quant Engineer** | Stats verification, manual trade data reconciliation |
| **AI/ML Engineer** | Error boundaries, Sentry integration, feature flag system |

---

## Cross-Sprint Architecture Decisions

### Navigation Structure (Final)

```
Sidebar:
  [AIFred Logo]
  ----------------
  Dashboard        /dashboard       (Sprint 1)
  Statistics       /stats           (Sprint 3)
  Configuration    /config          (Sprint 4)
  Competition      /competition     (Sprint 5)
  ----------------
  Settings         /settings        (existing, enhanced)
  ----------------
  [Kill Switch]                     (existing, prominent)
  [LIVE | PAPER]                    (global toggle)
```

### Color System

AIFred brand tokens (distinct from NOFX's Binance yellow):

```css
--aifred-primary: #6366F1;      /* Indigo -- brand primary */
--aifred-accent: #06B6D4;       /* Cyan -- interactive accent */
--aifred-profit: #10B981;       /* Emerald -- profit/long */
--aifred-loss: #EF4444;         /* Red -- loss/short */
--aifred-warning: #F59E0B;      /* Amber -- warnings */
--aifred-bg: #0F1117;           /* Near-black -- page background */
--aifred-card: #1A1D26;         /* Dark gray -- card background */
--aifred-border: #2A2D36;       /* Medium gray -- borders */
--aifred-text: #E5E7EB;         /* Light gray -- primary text */
--aifred-muted: #6B7280;        /* Gray -- secondary text */
```

Glass morphism class for cards:
```css
.aifred-glass {
  background: rgba(26, 29, 38, 0.8);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(99, 102, 241, 0.15);
  border-radius: 12px;
}
```

### Data Polling Intervals

| Data Type | Interval | Justification |
|-----------|----------|---------------|
| Positions & mark prices | 5 seconds | Must feel real-time for active traders |
| Account balance/equity | 10 seconds | Updates less frequently than positions |
| Equity history (curve) | 30 seconds | Historical data; new point every 5 minutes |
| Decisions | 15 seconds | New decisions are infrequent |
| Stats | 60 seconds | Expensive computation; changes only on trade close |
| Competition leaderboard | 15 seconds | Multi-trader ranking updates |
| System health | 30 seconds | Background monitoring |

### File Structure (End State)

```
app/
  (authenticated)/
    layout.tsx                     -- AppShell with Sidebar
    dashboard/
      page.tsx                     -- Main dashboard
    stats/
      page.tsx                     -- Trading statistics
    config/
      page.tsx                     -- Models, exchanges, traders
    competition/
      page.tsx                     -- AI competition arena
    settings/
      page.tsx                     -- User settings (existing, moved)
  api/
    auth/[...nextauth]/route.ts    -- Existing
    trading/
      route.ts                     -- Existing
      equity-history/route.ts      -- NEW (Sprint 1)
      positions/close/route.ts     -- NEW (Sprint 1)
      positions/modify/route.ts    -- NEW (Sprint 1)
      decisions/route.ts           -- NEW (Sprint 2)
      decisions/[cycleId]/route.ts -- NEW (Sprint 2)
      stats/overview/route.ts      -- NEW (Sprint 3)
      stats/by-direction/route.ts  -- NEW (Sprint 3)
      stats/by-symbol/route.ts     -- NEW (Sprint 3)
      stats/trade-history/route.ts -- NEW (Sprint 3)
      config/models/route.ts       -- NEW (Sprint 4)
      config/models/[id]/route.ts  -- NEW (Sprint 4)
      config/exchanges/route.ts    -- NEW (Sprint 4)
      config/exchanges/[id]/route.ts -- NEW (Sprint 4)
      traders/route.ts             -- NEW (Sprint 4)
      traders/[id]/route.ts        -- NEW (Sprint 4)
      traders/[id]/start/route.ts  -- NEW (Sprint 4)
      traders/[id]/stop/route.ts   -- NEW (Sprint 4)
      competition/route.ts         -- NEW (Sprint 5)
      competition/equity-curves/route.ts -- NEW (Sprint 5)
      competition/start/route.ts   -- NEW (Sprint 5)
      ... (existing endpoints preserved)
  login/page.tsx                   -- Existing
  page.tsx                         -- Landing/redirect
  layout.tsx                       -- Root layout
  globals.css                      -- Updated with color tokens

components/
  layout/
    AppShell.tsx                   -- Sprint 1
    Sidebar.tsx                    -- Sprint 1
    NavItem.tsx                    -- Sprint 1
  dashboard/
    HeroMetrics.tsx                -- Sprint 1
    RecentDecisions.tsx            -- Sprint 2
  charts/
    EquityCurve.tsx                -- Sprint 1
    ComparisonChart.tsx            -- Sprint 5
  positions/
    PositionsTable.tsx             -- Sprint 1
    PositionRow.tsx                -- Sprint 1
    PositionActions.tsx            -- Sprint 1
  decisions/
    DecisionCard.tsx               -- Sprint 2
    ActionCard.tsx                 -- Sprint 2
    ReasoningExpander.tsx          -- Sprint 2
    DecisionTimeline.tsx           -- Sprint 2
  stats/
    StatsGrid.tsx                  -- Sprint 3
    StatCard.tsx                   -- Sprint 3
    DirectionBreakdown.tsx         -- Sprint 3
    SymbolPerformance.tsx          -- Sprint 3
    TradeHistoryTable.tsx          -- Sprint 3
  config/
    ModelCard.tsx                  -- Sprint 4
    ModelConfigModal.tsx           -- Sprint 4
    ExchangeCard.tsx               -- Sprint 4
    ExchangeConfigModal.tsx        -- Sprint 4
    TraderCard.tsx                 -- Sprint 4
    TraderConfigModal.tsx          -- Sprint 4
    ConfigSection.tsx              -- Sprint 4
  competition/
    Leaderboard.tsx                -- Sprint 5
    HeadToHead.tsx                 -- Sprint 5
    CompetitionHeader.tsx          -- Sprint 5
    RankBadge.tsx                  -- Sprint 5
  ... (existing components preserved)

lib/
  stores/
    useUIStore.ts                  -- Sprint 1
    useDashboardStore.ts           -- Sprint 1
    useConfigStore.ts              -- Sprint 4
    useTraderStore.ts              -- Sprint 4
    useCompetitionStore.ts         -- Sprint 5
  queryKeys.ts                     -- Sprint 1
```

---

## Package Installation Timeline

| Sprint | Packages | Command |
|--------|----------|---------|
| 1 | zustand, sonner, date-fns | `npm install zustand sonner date-fns` |
| 3 | @tanstack/react-table | `npm install @tanstack/react-table` |
| 6 | @next/bundle-analyzer (dev) | `npm install -D @next/bundle-analyzer` |

---

## Success Metrics

| Metric | Current | Sprint 1 Target | Sprint 6 Target |
|--------|---------|----------------|----------------|
| Pages | 3 | 5 (shells) | 5 (fully functional) |
| Components | 23 | 35 | 55+ |
| API endpoints | 18 | 21 | 35+ |
| Lighthouse perf score | Unknown | 70 | 90+ |
| Time to first meaningful paint | Unknown | < 2s | < 1.5s |
| Real-time data sources | 1 (Hyperliquid) | 1 | 1 (expandable) |
| Demo data shown by default | Yes | No | No |
| Flickering/layout shift | Frequent | None | None |
| Mobile responsive | No | Partial | Full |

---

## Risk Register (Cross-Sprint)

| # | Risk | Probability | Impact | Mitigation | Owner |
|---|------|------------|--------|------------|-------|
| R1 | Multi-trader backend slips past Sprint 4 | High | High | Config UI works with single trader; multi-trader as Sprint 6 stretch goal | Backend Architect |
| R2 | Hyperliquid API changes or rate limits tighten | Medium | High | Abstract exchange calls behind interface; cache aggressively | Backend Architect |
| R3 | Decision audit trail requires significant Python agent refactor | Medium | Medium | Start Sprint 2 backend work in Sprint 1 as parallel task | AI/ML Engineer |
| R4 | Equity history has no data for first 24 hours after deploy | Certain | Low | Seed with current balance; show "Building history..." message | Frontend Lead |
| R5 | Bundle size bloat from charts + tables | Medium | Medium | Aggressive lazy loading; monitor with bundle analyzer from Sprint 1 | Frontend Lead |
| R6 | SSR hydration issues with wallet + charts | High | Medium | Follow CLAUDE.md rules: `initial={false}`, `dynamic` with `ssr: false` | Frontend Lead |

---

*This plan is designed for independent sprint execution. Each sprint's section contains everything an agent needs: component specs, API contracts, state management, acceptance criteria, and risk mitigation. Sprints 1-2 are the critical path. If timeline compresses, Sprints 5-6 features can be deferred without affecting core platform quality.*
