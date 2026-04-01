# NOFX Technical Analysis & AIFred Gap Assessment

**Prepared by:** Technical Architecture Lead
**Date:** 2026-04-01
**Audience:** Full 12-person AIFred development team
**Purpose:** Blueprint for AIFred UI/UX overhaul based on NOFX (NoFxAiOS/nofx) reference standard

---

## 1. NOFX Platform Overview

NOFX is an open-source autonomous AI trading platform (11.5k+ GitHub stars, AGPL-3.0) that enables multi-AI, multi-exchange crypto trading with zero manual API key management via x402 micropayments. It represents the current gold standard the board has identified for our overhaul target.

### 1.1 Tech Stack Comparison

| Layer | NOFX | AIFred |
|-------|------|--------|
| **Frontend Framework** | React 18 + Vite + React Router DOM 7.x | Next.js 16 + App Router |
| **Language** | TypeScript | TypeScript |
| **Styling** | Tailwind CSS | Tailwind CSS 4 |
| **State Management** | Zustand | React Query + useState |
| **Data Fetching** | Axios + SWR | React Query + fetch |
| **Charts** | Recharts + Lightweight Charts + TradingView Widget | Recharts + Lightweight Charts |
| **Animation** | Framer Motion | Framer Motion |
| **Icons** | Lucide React | Lucide React |
| **Backend** | Go 1.21+ with TA-Lib | Next.js API Routes + Python agents |
| **Build Tool** | Vite | Next.js (Turbopack) |
| **Testing** | Vitest + Testing Library | Vitest + Testing Library |
| **Deployment** | Docker + Railway + Nginx | Vercel + Railway |

**Key Stack Differences:** NOFX uses a standalone React SPA with Vite and a Go backend, while AIFred uses Next.js full-stack with Python agents. The core UI libraries are nearly identical. The biggest frontend gap is not framework choice but rather feature coverage and component architecture depth.

### 1.2 NOFX Component Architecture

NOFX organizes its frontend into 9 component domains with ~60 component files:

```
src/components/
  auth/         — Login, registration, password reset
  charts/       — 7 components: AdvancedChart, ChartTabs, ChartWithOrders,
                  ChartWithOrdersSimple, ComparisonChart, EquityChart, TradingViewChart
  common/       — 12 shared components: HeaderBar, Container, ConfirmDialog,
                  ExchangeIcons, ModelIcons, PunkAvatar, MetricTooltip, etc.
  faq/          — FAQ page components
  landing/      — 8+ landing page components with brand/ and core/ subdirs
  modals/       — SetupPage, TwoStageKeyModal
  strategy/     — 8 components: CoinSourceEditor, GridConfigEditor, GridRiskPanel,
                  IndicatorEditor, PromptSectionsEditor, PublishSettingsEditor,
                  RiskControlEditor, TokenEstimateBar
  trader/       — 18 components: AITradersPage, CompetitionPage, DecisionCard,
                  ModelCard, TraderConfigModal, TradersList, PositionHistory, etc.
  ui/           — 3 primitives: alert-dialog, input, select
```

### 1.3 NOFX Route Structure (10 pages)

| Route | Page | Description |
|-------|------|-------------|
| `/` | LandingPage | Public marketing/onboarding |
| `/login` | LoginPage | Authentication |
| `/register` | RegisterPage | Account creation |
| `/reset-password` | ResetPasswordPage | Password recovery |
| `/setup` | SetupPage | First-time system initialization |
| `/welcome` | BeginnerOnboardingPage | Guided onboarding flow |
| `/traders` (Config) | AITradersPage | AI models, exchanges, active bots management |
| `/dashboard` (Trader) | TraderDashboardPage | Per-trader dashboard with positions, equity, decisions |
| `/competition` | CompetitionPage | Live AI competition/leaderboard |
| `/strategy` | StrategyStudioPage | Visual strategy builder |
| `/strategy-market` | StrategyMarketPage | Strategy marketplace |
| `/data` | DataPage | Public data display |
| `/settings` | SettingsPage | User settings |
| `/faq` | FAQPage | Help documentation |

---

## 2. NOFX UI Feature Inventory (from board screenshots)

### 2.1 Dashboard Page

**Top Metrics Bar:**
- TOTAL EQUITY (large, prominent, real-time from exchange)
- AVAILABLE BALANCE (withdrawable amount)
- TOTAL P&L with both absolute value and % change, color-coded green/red
- POSITIONS count with Margin % indicator

**Account Equity Curve:**
- Interactive area chart showing account value over time
- USDT/$ denomination toggle
- Percentage view toggle
- Time range selector
- Real exchange data, not demo/simulated

**Market Chart:**
- Full TradingView widget integration
- Binance data feed
- Candlestick charts with technical indicators
- Drawing tools, multiple timeframes

**Recent Decisions Panel:**
- AI chain-of-thought reasoning displayed per trading cycle
- Expandable cycle cards showing full reasoning
- Model name, timestamp, decision outcome
- Multi-step thought process visible (perception -> analysis -> decision)

**Current Positions Table:**
- Symbol column
- Side (LONG/SHORT) with color coding
- Action buttons (Close, Modify) per row
- Entry Price
- Mark Price (real-time)
- Quantity (QTY)
- Position Value
- Leverage indicator
- Unrealized P&L (UPNL) with color coding
- Liquidation Price
- Row-level interactivity

**Dashboard Footer Stats:**
- Initial Balance
- Current Equity
- Historical Cycles count
- Display Range selector

### 2.2 Config Page (AITradersPage)

**AI Models Section:**
- Card grid showing all supported models: Claude, DeepSeek, Gemini, Grok, Kimi, OpenAI, Qwen
- Each card shows model name, specific version (e.g., claude-sonnet-4-20250514)
- Status indicator per model
- "+ AI Models" button to add new model configurations

**Exchanges Section:**
- Card grid: Aster, Binance, Bybit, Hyperliquid, Lighter, OKX
- Connection status per exchange
- API key configuration
- "+ Exchanges" button

**Current Traders Section:**
- List of running bot instances
- Each trader = one AI model + one exchange combination
- Per-trader controls: View, Edit, Stop, Delete
- Strategy assignment visible
- "+ Create Trader" button for new bot instances

### 2.3 Live Competition Page

**Performance Comparison Chart:**
- Real-time overlaid equity curves for multiple AI traders
- P&L % as Y-axis for fair comparison
- Color-coded per trader/model
- Time-synced X-axis

**Leaderboard Table:**
- Ranked by performance
- Columns: Equity, P&L (absolute + %), Position count
- Real-time updating

**Head-to-Head Battle Visualization:**
- Direct comparison between two selected traders
- Side-by-side metrics

### 2.4 Trading Stats Page

**Summary Metrics Grid:**
- Total Trades
- Win Rate (%)
- Total P&L ($)
- Profit Factor
- P/L Ratio (average win / average loss)
- Sharpe Ratio
- Max Drawdown (%)
- Average Win ($)
- Average Loss ($)
- Net P&L (after fees)

**LONG vs SHORT Breakdown:**
- Separate win rate, P&L, trade count for each direction
- Visual comparison

**Symbol Performance:**
- Per-symbol P&L breakdown
- Win rate per symbol
- Trade count per symbol

**Trade History Table:**
- Full filterable table
- Columns: Symbol, Entry Price, Exit Price, QTY, P&L, Fee, Duration, Closed At
- Sortable columns
- Pagination

### 2.5 Strategy Studio Page

- Visual builder with sections for:
  - Coin sources (which assets to trade)
  - Technical indicators configuration
  - Risk control parameters
  - Prompt sections (AI prompt customization)
  - Grid configuration
  - Publish settings
  - Token cost estimator

---

## 3. Feature Gap Matrix: NOFX vs AIFred

### 3.1 Dashboard Layout & Metrics

| Feature | NOFX | AIFred Current | Gap | Priority | Effort |
|---------|------|----------------|-----|----------|--------|
| Top metrics bar (Equity, Balance, P&L, Positions) | Full bar with real exchange data | AccountSummaryBar exists but basic styling, text-only | Minor polish | P1 | S |
| P&L with % change + color coding | Yes, prominent | Yes, basic implementation | Styling gap | P2 | S |
| Margin % indicator | Yes | No | Missing | P2 | M |
| Available balance (withdrawable) | Yes | Shows total only | Missing field | P2 | S |

### 3.2 TradingView Chart Integration

| Feature | NOFX | AIFred Current | Gap | Priority | Effort |
|---------|------|----------------|-----|----------|--------|
| TradingView widget | Full widget with Binance feed | No TradingView integration | **Critical gap** | P0 | L |
| Candlestick charts | TradingView-powered | Lightweight Charts (area only) | Needs upgrade | P0 | M |
| Multiple timeframes | Yes | No | Missing | P1 | M |
| Drawing tools | Yes (TradingView built-in) | No | Missing | P2 | S (comes with widget) |
| Order overlay on chart | ChartWithOrders component | No | Missing | P1 | L |

### 3.3 AI Chain-of-Thought / Decision Transparency

| Feature | NOFX | AIFred Current | Gap | Priority | Effort |
|---------|------|----------------|-----|----------|--------|
| Decision cards with reasoning | DecisionCard component, expandable | ActivityTab shows trade logs, no AI reasoning | **Critical gap** | P0 | L |
| Multi-step thought process | Perception -> Analysis -> Decision pipeline | Not exposed in UI | Missing | P0 | L |
| Per-cycle expansion | Expandable cycle history | No concept of "cycles" | Missing | P1 | M |
| Model attribution | Shows which AI model made decision | Hardcoded "7 AGENTS ONLINE" | Missing | P1 | M |

### 3.4 Position Management

| Feature | NOFX | AIFred Current | Gap | Priority | Effort |
|---------|------|----------------|-----|----------|--------|
| Positions table | Full table: Symbol, Side, Entry, Mark, QTY, Value, Leverage, UPNL, Liq Price | LivePositionsPanel + TradesTab: basic rows | Significant upgrade needed | P0 | L |
| Action buttons (Close/Modify) | Per-row controls | No position management actions | **Critical gap** | P0 | L |
| Mark price (real-time) | Yes | Not shown (entry only) | Missing | P1 | M |
| Leverage indicator | Yes | No | Missing | P2 | S |
| Liquidation price | Yes | No | Missing | P1 | M |
| Position value column | Yes | No | Missing | P2 | S |

### 3.5 Config / Multi-AI Model Support

| Feature | NOFX | AIFred Current | Gap | Priority | Effort |
|---------|------|----------------|-----|----------|--------|
| AI model card grid | 7+ models with version display | AgentsTab shows hardcoded agent descriptions | **Critical gap** | P0 | XL |
| Add/remove AI models | ModelConfigModal | No model management | Missing | P0 | L |
| Model-specific configuration | Per-model API key + settings | No concept | Missing | P0 | L |
| Model status indicators | Per-model health | No per-model status | Missing | P1 | M |

### 3.6 Multi-Exchange Support UI

| Feature | NOFX | AIFred Current | Gap | Priority | Effort |
|---------|------|----------------|-----|----------|--------|
| Exchange card grid | 6+ exchanges: Binance, Bybit, OKX, Hyperliquid, Aster, Lighter | TradingSettings: Alpaca, Binance, Coinbase, OANDA, Hyperliquid listed | Partial (has exchanges, needs card UI) | P1 | M |
| Exchange config modal | ExchangeConfigModal with guided setup | Inline credential form | Needs upgrade | P2 | M |
| Connection status per exchange | Visual indicators | Basic connected/disconnected | Minor gap | P2 | S |
| Add exchange button | "+ Exchanges" | No dynamic addition | Missing | P2 | M |

### 3.7 Bot/Trader Management

| Feature | NOFX | AIFred Current | Gap | Priority | Effort |
|---------|------|----------------|-----|----------|--------|
| Create Trader (model + exchange combo) | TraderConfigModal, full CRUD | No concept of "traders" as instances | **Critical gap** | P0 | XL |
| Traders list with controls | View/Edit/Stop/Delete per trader | Single bot with start/stop | Major gap | P0 | L |
| Multiple simultaneous traders | Yes | No (single pipeline) | Architecture gap | P0 | XL |
| Per-trader dashboard | TraderDashboardPage | Not applicable | Missing | P1 | XL |

### 3.8 Live Competition / Arena

| Feature | NOFX | AIFred Current | Gap | Priority | Effort |
|---------|------|----------------|-----|----------|--------|
| Competition page | Full CompetitionPage with tests | No competition feature | **Critical gap** | P1 | XL |
| Performance comparison chart | ComparisonChart (overlaid equity curves) | No comparison | Missing | P1 | L |
| Leaderboard | Ranked table with real-time data | No leaderboard | Missing | P1 | M |
| Head-to-head battles | Side-by-side trader comparison | No concept | Missing | P2 | L |

### 3.9 Trading Statistics Page

| Feature | NOFX | AIFred Current | Gap | Priority | Effort |
|---------|------|----------------|-----|----------|--------|
| Dedicated stats page | Separate page with full metrics | OverviewTab has some stats inline | Needs dedicated page | P1 | L |
| Win Rate, Profit Factor, Sharpe, Max DD | All present | Some present in OverviewTab | Partial coverage | P1 | M |
| LONG vs SHORT breakdown | Yes | No | Missing | P2 | M |
| Symbol performance table | Per-symbol P&L | byAsset data exists but minimal display | Needs expansion | P2 | M |
| Trade history with filters | Full sortable/filterable table | TradesTab basic list, no filtering | Significant gap | P1 | L |
| Fee tracking | Per-trade fee column | totalFees in summary only | Missing detail | P2 | M |
| Duration per trade | Yes | No | Missing | P2 | S |

### 3.10 Equity Curve

| Feature | NOFX | AIFred Current | Gap | Priority | Effort |
|---------|------|----------------|-----|----------|--------|
| Real equity curve from exchange | Yes, live account data | OverviewTab has area chart from trading-data.json | Needs live data | P0 | M |
| USDT/$ toggle | Yes | No | Missing | P2 | S |
| % view toggle | Yes | No | Missing | P2 | S |
| Time range selector | Yes | No | Missing | P1 | M |

### 3.11 Navigation Structure

| Feature | NOFX | AIFred Current | Gap | Priority | Effort |
|---------|------|----------------|-----|----------|--------|
| Multi-page app (10+ routes) | Dashboard, Config, Competition, Strategy, Stats, etc. | 3 routes: /, /trading, /trading/settings | **Critical gap** | P0 | L |
| Dedicated sidebar/header nav | HeaderBar with full navigation | Tab bar within single page | Needs overhaul | P0 | M |
| Landing/marketing page | Full landing with hero, features, community | Login page only | Missing (lower priority) | P3 | L |
| Onboarding flow | BeginnerOnboardingPage + SetupPage | Welcome panel inline | Needs dedicated flow | P2 | M |

### 3.12 Strategy Studio

| Feature | NOFX | AIFred Current | Gap | Priority | Effort |
|---------|------|----------------|-----|----------|--------|
| Visual strategy builder | 8 editor components | No strategy builder UI | **Critical gap** | P1 | XL |
| Coin source selection | CoinSourceEditor | Hardcoded asset list in settings | Missing | P1 | L |
| Indicator configuration | IndicatorEditor | No UI (configured in Python) | Missing | P1 | L |
| Risk control editor | RiskControlEditor | Basic risk params in settings | Needs upgrade | P1 | M |
| AI prompt customization | PromptSectionsEditor | No concept | Missing | P2 | L |
| Token cost estimator | TokenEstimateBar | No concept | Missing | P3 | S |
| Strategy marketplace | StrategyMarketPage | No concept | Missing | P3 | XL |

---

## 4. Priority Summary

### P0 — Must-Have (Sprint 1-2, Weeks 1-4)

These are the features where AIFred falls critically short:

1. **TradingView chart integration** — Replace lightweight charts area chart with TradingView widget. Use the free TradingView widget library (`react-tradingview-widget` or embed script).
2. **AI decision transparency** — Create a DecisionCard component showing chain-of-thought reasoning. Backend must expose AI reasoning per trade cycle.
3. **Position management with actions** — Full positions table with Close/Modify buttons, mark price, leverage, liquidation price.
4. **Multi-AI model configuration** — Config page with model cards, version selection, API key management per model.
5. **Multi-trader instances** — Architecture to support multiple AI model + exchange combinations running simultaneously.
6. **Navigation overhaul** — Move from tab-based single-page to multi-page architecture with proper routing.

### P1 — Should-Have (Sprint 3-4, Weeks 5-8)

7. **Live competition page** — ComparisonChart + leaderboard for AI-vs-AI performance tracking.
8. **Dedicated trading stats page** — Comprehensive stats with LONG/SHORT breakdown, symbol performance.
9. **Strategy studio** — Visual builder for strategy configuration (coin sources, indicators, risk controls).
10. **Real equity curve** — Live exchange data with time range selector.
11. **Trade history with filters** — Sortable, filterable trade history table with fees and duration.

### P2 — Nice-to-Have (Sprint 5-6, Weeks 9-12)

12. **Onboarding flow redesign**
13. **Exchange configuration modals**
14. **AI prompt customization UI**
15. **LONG/SHORT analytics breakdown**

### P3 — Future Backlog

16. **Strategy marketplace**
17. **Landing/marketing page**
18. **Token cost estimator**
19. **Telegram agent integration UI**

---

## 5. Technical Architecture Recommendations

### 5.1 New Pages to Create

AIFred currently has 3 pages. We need to reach at least 8:

```
app/
  page.tsx                    — Landing/Home (redirect to dashboard if authenticated)
  login/page.tsx              — Keep existing
  dashboard/page.tsx          — NEW: Main trading dashboard (move from /trading)
  dashboard/[traderId]/       — NEW: Per-trader detail view
    page.tsx
  config/page.tsx             — NEW: AI models + exchanges + traders management
  competition/page.tsx        — NEW: AI competition arena
  stats/page.tsx              — NEW: Comprehensive trading statistics
  strategy/page.tsx           — NEW: Strategy studio builder
  settings/page.tsx           — Keep existing, expand
```

### 5.2 New Components to Create

**charts/ (5 new components)**
```
components/charts/
  TradingViewChart.tsx        — TradingView widget wrapper
  EquityCurve.tsx             — Real-time equity curve with range selector
  ComparisonChart.tsx         — Multi-trader equity overlay for competition
  ChartWithOrders.tsx         — Price chart with order/position markers
  PerformanceChart.tsx        — Win rate, P&L distribution visualizations
```

**config/ (6 new components)**
```
components/config/
  ModelCard.tsx               — AI model display card with status
  ModelConfigModal.tsx        — Add/edit AI model configuration
  ExchangeCard.tsx            — Exchange connection card
  ExchangeConfigModal.tsx     — Exchange API key setup
  TraderCard.tsx              — Running bot instance card
  TraderConfigModal.tsx       — Create/edit trader (model + exchange combo)
```

**decisions/ (3 new components)**
```
components/decisions/
  DecisionCard.tsx            — AI chain-of-thought display
  DecisionTimeline.tsx        — Chronological decision history
  ReasoningExpander.tsx       — Expandable multi-step reasoning view
```

**positions/ (3 new components)**
```
components/positions/
  PositionsTable.tsx          — Full positions table with all NOFX columns
  PositionActions.tsx         — Close/Modify action buttons
  PositionRow.tsx             — Individual position row with mark price, leverage
```

**competition/ (3 new components)**
```
components/competition/
  Leaderboard.tsx             — Ranked trader performance table
  HeadToHead.tsx              — Side-by-side trader comparison
  CompetitionControls.tsx     — Start/stop competition, select participants
```

**stats/ (4 new components)**
```
components/stats/
  StatsGrid.tsx               — Top-level metrics grid
  DirectionBreakdown.tsx      — LONG vs SHORT analysis
  SymbolPerformance.tsx       — Per-symbol P&L table
  TradeHistoryTable.tsx       — Filterable, sortable trade history
```

**strategy/ (4 new components)**
```
components/strategy/
  CoinSourceEditor.tsx        — Asset selection for strategy
  IndicatorEditor.tsx         — Technical indicator configuration
  RiskControlEditor.tsx       — Risk parameter visual editor
  StrategyBuilder.tsx         — Main strategy studio orchestrator
```

### 5.3 New API Endpoints Needed

```
Backend API additions:

# AI Model Management
POST   /api/config/models          — Add AI model configuration
GET    /api/config/models          — List configured models
PUT    /api/config/models/[id]     — Update model config
DELETE /api/config/models/[id]     — Remove model

# Trader (Bot Instance) Management
POST   /api/traders                — Create trader (model + exchange)
GET    /api/traders                — List active traders
GET    /api/traders/[id]           — Trader detail + positions + decisions
PUT    /api/traders/[id]           — Update trader config
POST   /api/traders/[id]/stop      — Stop trader
POST   /api/traders/[id]/start     — Start trader
DELETE /api/traders/[id]           — Delete trader

# AI Decisions / Chain-of-Thought
GET    /api/traders/[id]/decisions  — Decision history with reasoning
GET    /api/traders/[id]/decisions/[cycle] — Single cycle detail

# Competition
GET    /api/competition             — Competition state + leaderboard
POST   /api/competition/start       — Start new competition
GET    /api/competition/equity-curves — Multi-trader equity data for overlay

# Enhanced Stats
GET    /api/stats/overview          — Aggregate stats (Sharpe, Profit Factor, etc.)
GET    /api/stats/by-direction      — LONG vs SHORT breakdown
GET    /api/stats/by-symbol         — Per-symbol performance
GET    /api/stats/trade-history     — Paginated, filterable trade history

# Strategy
POST   /api/strategies              — Create strategy
GET    /api/strategies              — List strategies
PUT    /api/strategies/[id]         — Update strategy
```

### 5.4 State Management Upgrade

AIFred currently uses React Query for server state and local `useState` for UI state. For the multi-trader architecture, we need a global store:

**Recommendation:** Add Zustand (matching NOFX) for client-side state:

```
lib/stores/
  useTraderStore.ts           — Active traders, selection state
  useCompetitionStore.ts      — Competition state, selected participants
  useConfigStore.ts           — Model/exchange configuration cache
  useUIStore.ts               — Navigation state, modal state, preferences
```

Keep React Query for server data fetching. Zustand handles UI coordination across components.

### 5.5 Third-Party Integrations

| Integration | Purpose | Package | Effort |
|-------------|---------|---------|--------|
| TradingView Widget | Professional charting | `charting_library` (free) or embed widget | M |
| Zustand | Global state management | `zustand` | S |
| Tanstack Table | Sortable/filterable tables | `@tanstack/react-table` | M |
| date-fns | Date formatting (trade durations) | `date-fns` | S |
| Sonner | Toast notifications (replace custom) | `sonner` | S |

### 5.6 Navigation Architecture

Replace the current tab-based navigation inside the dashboard with a persistent sidebar or top navigation bar:

```tsx
// components/layout/AppShell.tsx
// Persistent layout wrapping all authenticated pages

<AppShell>
  <Sidebar>
    <NavItem href="/dashboard" icon={LayoutDashboard} label="Dashboard" />
    <NavItem href="/config" icon={Settings2} label="Configuration" />
    <NavItem href="/competition" icon={Trophy} label="Competition" />
    <NavItem href="/stats" icon={BarChart3} label="Statistics" />
    <NavItem href="/strategy" icon={Puzzle} label="Strategy" />
    <NavItem href="/settings" icon={Settings} label="Settings" />
  </Sidebar>
  <MainContent>{children}</MainContent>
</AppShell>
```

This should be implemented as a Next.js layout at `app/(authenticated)/layout.tsx` to wrap all logged-in pages.

### 5.7 Data Architecture for Multi-Trader Support

The most fundamental architectural change is moving from AIFred's current single-pipeline model to NOFX's multi-trader model. This requires:

1. **Database schema** — Traders table linking a model config + exchange config + strategy config. Each trader is an independent execution unit.
2. **Backend orchestration** — Python agent system needs to support spawning/managing multiple trader processes. Each trader runs its own analysis -> decision -> execution loop.
3. **WebSocket or SSE** — For real-time position updates and decision streaming across multiple traders simultaneously. The current polling approach (`refetchInterval: 5000`) will not scale.
4. **Shared execution layer** — Multiple traders may target the same exchange. Need connection pooling and rate limit management at the exchange connector level.

---

## 6. Implementation Roadmap

### Sprint 1 (Weeks 1-2): Foundation

- [ ] Create AppShell layout with sidebar navigation
- [ ] Create `/dashboard`, `/config`, `/stats` page shells
- [ ] Integrate TradingView widget on dashboard
- [ ] Add Zustand for global state
- [ ] Design database schema for multi-trader architecture

### Sprint 2 (Weeks 3-4): Core Features

- [ ] Build config page: ModelCard grid + ExchangeCard grid
- [ ] Build ModelConfigModal and ExchangeConfigModal
- [ ] Build TraderConfigModal (create trader = model + exchange)
- [ ] Build PositionsTable with full columns and action buttons
- [ ] Implement /api/config/models and /api/traders endpoints

### Sprint 3 (Weeks 5-6): Intelligence Layer

- [ ] Build DecisionCard with chain-of-thought expansion
- [ ] Expose AI reasoning from Python agents through API
- [ ] Build real equity curve with exchange data and time range selector
- [ ] Build dedicated stats page with all NOFX metrics
- [ ] Build TradeHistoryTable with filtering and sorting

### Sprint 4 (Weeks 7-8): Competition & Strategy

- [ ] Build competition page with ComparisonChart
- [ ] Build leaderboard component
- [ ] Build strategy studio page (CoinSourceEditor, IndicatorEditor, RiskControlEditor)
- [ ] Implement multi-trader backend orchestration
- [ ] Add WebSocket/SSE for real-time updates

### Sprint 5 (Weeks 9-10): Polish & Parity

- [ ] Onboarding flow redesign
- [ ] LONG/SHORT analytics breakdown
- [ ] Symbol performance views
- [ ] Head-to-head battle visualization
- [ ] Prompt customization UI

### Sprint 6 (Weeks 11-12): Testing & Launch

- [ ] Full E2E testing across all pages
- [ ] Performance optimization (code splitting, lazy loading)
- [ ] Mobile responsiveness audit
- [ ] Documentation and team handoff

---

## 7. What AIFred Already Does Well

Before the team dives into gaps, it is important to acknowledge AIFred's existing strengths that NOFX lacks or implements differently:

1. **Wallet-native authentication** — WalletConnect + wagmi integration for Web3-native auth. NOFX uses traditional login. This is a competitive advantage.
2. **Hyperliquid DEX integration** — Direct on-chain trading with live position data. NOFX supports Hyperliquid but AIFred's wallet-connected approach is more seamless.
3. **Multi-agent system with named roles** — 7 specialized agents (Data Ingestion, Technical Analysis, NLP, Risk Management, Execution, Monitoring, Meta-Learning). NOFX treats AI as a single decision layer.
4. **Regime detection** — HMM-based market regime analysis (RegimeTab). NOFX does not expose regime analysis in UI.
5. **Kill switch** — Emergency stop functionality with dedicated button. Important safety feature.
6. **Paper/Live mode toggle** — AccountSummaryBar toggle between live exchange data and demo data. Clean UX pattern.
7. **Backtesting infrastructure** — Built-in backtester with API endpoint. Not visible in NOFX web UI.

These should be preserved and enhanced, not replaced.

---

## 8. Critical Path Summary

The single highest-impact workstream is the **multi-trader architecture** (Sections 3.5, 3.7, 5.7). This is the backbone that enables NOFX's entire Config page, Competition page, and per-trader dashboards. Without it, most P0 features cannot exist.

**Recommended team allocation (12 people):**

| Team | Size | Focus |
|------|------|-------|
| **Platform** | 3 | Multi-trader backend, database schema, API endpoints |
| **Dashboard** | 3 | TradingView integration, PositionsTable, EquityCurve, DecisionCard |
| **Config & Competition** | 3 | Config page, model/exchange/trader management, competition page |
| **Stats & Strategy** | 2 | Stats page, trade history, strategy studio |
| **Design & QA** | 1 | Navigation overhaul, AppShell layout, responsive testing |

---

*This document should be treated as a living blueprint. Update it as implementation reveals new gaps or as NOFX ships new features. The NOFX repo is actively maintained (dev branch) and may introduce additional features during our development cycle.*
