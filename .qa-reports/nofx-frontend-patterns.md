# NOFX Frontend Implementation Patterns
## For AIFred Team Reference

> Source: https://github.com/NoFxAiOS/nofx/tree/dev
> Analyzed: 2026-04-01

---

## 1. Tech Stack

### Frontend (web/)
| Category | Library | Version | Notes |
|----------|---------|---------|-------|
| **Framework** | React | ^18.3.1 | Standard SPA, no Next.js/SSR |
| **Build** | Vite | (devDep) | Fast HMR, TypeScript compilation |
| **Language** | TypeScript | (devDep) | Strict typing throughout |
| **Routing** | react-router-dom | ^7.9.5 | URL-based navigation with slug state |
| **State Mgmt** | Zustand | ^5.0.2 | Lightweight stores for config |
| **Data Fetching** | SWR | ^2.2.5 | Polling-based real-time updates |
| **HTTP Client** | Axios | ^1.13.2 | Custom wrapper with interceptors |
| **Charts (Equity)** | Recharts | ^2.15.2 | Line/area charts for equity curves |
| **Charts (Kline)** | lightweight-charts | ^5.1.0 | TradingView's open-source lib for candlesticks |
| **Styling** | TailwindCSS | (devDep) | Utility-first, dark theme throughout |
| **CSS Utils** | clsx + tailwind-merge + CVA | various | Conditional className composition |
| **Animation** | Framer Motion | ^12.23.24 | Page transitions, tab animations |
| **Icons** | Lucide React | ^0.552.0 | Consistent icon system |
| **Toasts** | Sonner | ^1.5.0 | Notification system |
| **Dates** | date-fns | ^4.1.0 | Date formatting |
| **UI Primitives** | @radix-ui (alert-dialog, slot) | various | Accessible modals |
| **QR Codes** | qrcode.react | ^4.2.0 | Wallet address QR |
| **Testing** | Vitest + @testing-library/react | (devDep) | Unit/component tests |

### Backend (Go monolith)
| Category | Technology | Notes |
|----------|-----------|-------|
| **Language** | Go | Single binary deployment |
| **API** | REST (Go handlers) | 23+ handler files |
| **Auth** | JWT Bearer tokens | Stored in localStorage |
| **Database** | Embedded (file-based) | SQLite or BoltDB pattern |
| **Deployment** | Docker / Railway | docker-compose + railway.toml |
| **Exchanges** | 10 supported | binance, bybit, okx, bitget, gate, kucoin, hyperliquid, aster, lighter, indodax |
| **AI Providers** | Multi-model | DeepSeek, Qwen, Claude + custom endpoints |

---

## 2. Component Structure

```
web/src/
  App.tsx                          # Root: routing, SWR polling, auth gate
  main.tsx                         # Entry point
  index.css                        # Tailwind base + custom vars
  
  pages/
    LandingPage.tsx                # Marketing/home
    TraderDashboardPage.tsx         # Main dashboard (equity, positions, decisions)
    SettingsPage.tsx                # Tabbed config (account, models, exchanges, telegram)
    StrategyStudioPage.tsx          # Strategy editor (3-column layout)
    StrategyMarketPage.tsx          # Marketplace for shared strategies
    DataPage.tsx                    # Data exploration
    FAQPage.tsx                     # Help content
    BeginnerOnboardingPage.tsx      # New user flow
    PageNotFound.tsx                # 404
  
  components/
    charts/
      EquityChart.tsx              # Recharts line chart, SWR 30s polling
      AdvancedChart.tsx            # lightweight-charts candlesticks, 5s refresh
      ChartTabs.tsx                # Tab switcher (equity vs kline)
      ChartWithOrders.tsx          # Chart with order overlay
      ChartWithOrdersSimple.tsx    # Simplified version
      ComparisonChart.tsx          # Multi-trader equity comparison
      TradingViewChart.tsx         # TradingView widget embed (iframe)
    
    trader/
      CompetitionPage.tsx          # Leaderboard + head-to-head
      AITradersPage.tsx            # Trader management list
      TradersList.tsx              # Trader selector grid
      DecisionCard.tsx             # AI decision display (actions + CoT)
      PositionHistory.tsx          # Closed positions table
      TraderConfigModal.tsx        # Create/edit trader
      TraderConfigViewModal.tsx    # Read-only trader config
      ExchangeConfigModal.tsx      # Exchange API key entry
      ModelConfigModal.tsx         # AI model setup
      TelegramConfigModal.tsx      # Telegram bot config
      ConfigStatusGrid.tsx         # Config completion status
      ModelCard.tsx                # AI model card
      ModelStepIndicator.tsx       # Setup progress
      BeginnerGuideCards.tsx       # Onboarding cards
      Tooltip.tsx                  # Reusable tooltip
      model-constants.ts           # Model metadata
      utils.ts                     # Trader utilities
    
    strategy/
      CoinSourceEditor.tsx         # Select trading pairs
      GridConfigEditor.tsx         # Grid strategy params
      GridRiskPanel.tsx            # Grid risk metrics
      IndicatorEditor.tsx          # Technical indicator config
      PromptSectionsEditor.tsx     # AI prompt customization
      PublishSettingsEditor.tsx     # Strategy sharing settings
      RiskControlEditor.tsx        # Stop-loss, position sizing
      TokenEstimateBar.tsx         # Prompt token counter
    
    common/
      PunkAvatar.tsx               # Generative avatar (punk-style)
      DeepVoidBackground.tsx       # Animated dark background
    
    auth/                          # Login/register components
    faq/                           # FAQ content components
    landing/                       # Landing page sections
    modals/                        # Generic modal components
    ui/                            # Design system primitives (select, etc.)
  
  stores/
    index.ts                       # Barrel export
    tradersConfigStore.ts          # Zustand: models + exchanges config
    tradersModalStore.ts           # Zustand: modal open/close state
  
  contexts/
    AuthContext.tsx                 # React Context: user, token, login/logout
    LanguageContext.tsx             # React Context: i18n language selection
  
  hooks/
    useCounterAnimation.ts         # Animated number transitions
    useGitHubStats.ts              # GitHub star count
    useSystemConfig.ts             # System config fetcher
  
  lib/
    api/                           # API function modules
      index.ts                     # Barrel export
      config.ts                    # Model/exchange config APIs
      data.ts                      # Data/analytics APIs
      helpers.ts                   # API helpers
      strategies.ts                # Strategy CRUD APIs
      telegram.ts                  # Telegram APIs
      traders.ts                   # Trader CRUD + status APIs
    httpClient.ts                  # Axios singleton with interceptors
    cn.ts                          # clsx + tailwind-merge utility
    config.ts                      # App config constants
    crypto.ts                      # Client-side encryption
    clipboard.ts                   # Copy utilities
    notify.tsx                     # Toast wrapper (sonner)
    onboarding.ts                  # Beginner/advanced mode logic
    text.ts                        # Text utilities
  
  i18n/
    translations.ts                # English + Chinese translations
    strategy-translations.ts       # Strategy-specific translations
  
  types/
    index.ts                       # Barrel re-export
    trading.ts                     # Core trading types
    strategy.ts                    # Strategy types
    config.ts                      # Config types
  
  utils/
    format.ts                      # Price/quantity formatting
    indicators.ts                  # SMA, EMA, Bollinger Bands calculation
  
  data/                            # Static data files
  constants/                       # App constants
  test/                            # Test utilities
```

### Naming Conventions
- Pages: `*Page.tsx` (PascalCase)
- Components: PascalCase `.tsx`
- Stores: `camelCaseStore.ts`
- Hooks: `use*.ts`
- Utils/lib: `camelCase.ts`
- Types: exported interfaces in dedicated `types/` directory

---

## 3. Feature Implementation Guide

### 3.1 Real-Time Dashboard

**How NOFX implements it:**
- `App.tsx` is the orchestrator -- it manages ALL SWR polling centrally
- SWR fetches with `refreshInterval` (5s for positions, 15s for competition, 30s for equity)
- Data flows DOWN as props to `TraderDashboardPage`
- No WebSocket -- pure REST polling with SWR deduplication
- Retry logic: stops polling after N consecutive failures to avoid hammering
- `mutate()` from SWR used for optimistic invalidation after actions (close position, etc.)

**Key props flow:**
```
App.tsx (SWR polling)
  -> TraderDashboardPage (receives status, account, positions, decisions, stats)
    -> ChartTabs -> EquityChart / AdvancedChart
    -> DecisionCard (per decision)
    -> PositionHistory
    -> GridRiskPanel (for grid strategies)
```

**How AIFred should implement it:**
- Use SWR or TanStack Query for polling-based data fetching
- Centralize polling in a top-level provider or the page component
- Pass data as props to child components (avoid prop drilling with context for deep trees)
- Polling intervals: 5s for positions/prices, 15-30s for equity curves, 60s for analytics
- Add retry-with-backoff logic to prevent server hammering
- **Key files to create/modify:** `pages/dashboard.tsx`, `hooks/useTraderData.ts`
- **Estimated effort:** 2-3 days

---

### 3.2 Equity Curve Chart

**How NOFX implements it:**
- `EquityChart.tsx` uses **Recharts** (`<ResponsiveContainer>`, `<LineChart>`, `<Area>`)
- SWR fetches equity history with 30s refresh
- Toggle between USD and % display modes
- Filters data: `total_equity > 1` to remove noise
- Limits to 2000 most recent data points for performance
- Shows 4 stats in footer: initial balance, current equity, cycle count, date range
- Gold gradient fill (`#F0B90B`) with dark background
- "NOFX" watermark overlay
- Skeleton loading states while data loads

**How AIFred should implement it:**
- Use Recharts for equity curves (simpler API than lightweight-charts for line data)
- Implement USD/% toggle
- Add data point limiting for large histories
- Include stats summary row below chart
- **Key files:** `components/charts/EquityChart.tsx`
- **Estimated effort:** 1 day

---

### 3.3 Candlestick / Kline Chart

**How NOFX implements it:**
- `AdvancedChart.tsx` uses **lightweight-charts v5** (TradingView's open-source library)
- Creates chart with `createChart()`, adds `CandlestickSeries`, `HistogramSeries` (volume), `LineSeries` (indicators)
- Fetches kline data via REST: `/api/klines?symbol=X&interval=Y&limit=1500&exchange=Z`
- **Real-time refresh every 5 seconds** (not WebSocket -- polls REST endpoint)
- Open order price lines refresh every 60 seconds
- 8 technical indicators: MA5/10/20/60, EMA12/26, Bollinger Bands (calculated client-side in `utils/indicators.ts`)
- Order markers (B/S) overlaid on candles using `createSeriesMarkers()` v5 API
- Binary search to snap order times to kline candle times
- OHLC tooltip on crosshair hover
- Multi-exchange support: Binance, Bybit, OKX, Hyperliquid, etc.
- Multi-market: Crypto, Stocks (Alpaca), Forex, Metals
- ResizeObserver for responsive sizing

**How AIFred should implement it:**
- Use lightweight-charts v5 (same library)
- Our backend already proxies kline data -- connect to that endpoint
- Implement order marker overlay (crucial for seeing where AI enters/exits)
- Start with fewer indicators (MA20, EMA12/26, Bollinger), add more later
- Use ResizeObserver pattern for responsive charts
- **Key files:** `components/charts/AdvancedChart.tsx`, `utils/indicators.ts`
- **Estimated effort:** 3-4 days

---

### 3.4 AI Decision Cards (Chain-of-Thought Display)

**How NOFX implements it:**
- `DecisionCard.tsx` renders each AI trading cycle
- Shows: cycle number, timestamp, success/fail status
- Each decision has multiple `ActionCard` components (open_long, close_short, hold, wait)
- Action cards show: symbol, direction, entry price, stop loss, take profit, leverage, risk/reward ratio
- **Three collapsible sections with copy/download:**
  1. System Prompt (purple accent) -- the instructions given to AI
  2. User Prompt (blue accent) -- market data input
  3. AI Thinking / Chain-of-Thought (gold accent) -- `decision.cot_trace`
- Each section has copy-to-clipboard and download-as-file buttons
- Execution log display at bottom
- Color-coded confidence scores (green >= 80%, yellow >= 60%, red < 60%)

**Data structure:**
```typescript
interface DecisionRecord {
  cycle_number: number
  timestamp: string
  success: boolean
  decisions: DecisionAction[]  // Multiple actions per cycle
  system_prompt: string
  input_prompt: string
  cot_trace: string            // Chain-of-thought
  execution_log: string[]
  error_message?: string
}
```

**How AIFred should implement it:**
- This is a killer feature -- implement it closely
- Store system_prompt, user_prompt, and cot_trace for every decision cycle
- Collapsible sections for prompt inspection (essential for debugging AI behavior)
- Copy/download buttons for sharing prompts with team
- Color-coded action types matching our trade direction colors
- **Key files:** `components/decisions/DecisionCard.tsx`, `components/decisions/ActionCard.tsx`
- **Estimated effort:** 2 days

---

### 3.5 Competition / Leaderboard

**How NOFX implements it:**
- `CompetitionPage.tsx` in `components/trader/`
- Fetches competition data via SWR with 15s polling
- Three sections:
  1. **Header:** competition title, trader count, current leader
  2. **ComparisonChart:** top 10 traders' equity curves overlaid (Recharts area + line)
  3. **Leaderboard:** ranked list with equity, P&L%, position count, AI model, exchange
- Head-to-head section appears when exactly 2 traders exist
- Animated rank badges (gold/silver/bronze for top 3)
- Click trader to view config details in modal

**ComparisonChart specifics:**
- Time period selector: 1D, 3D, 7D, 30D, All
- SWR batch fetch of equity histories (30s refresh)
- Timestamp normalization to nearest minute
- Gap-filling with last known values
- Area fill for top 2, lines for rest
- Leader info, gap metrics in footer stats

**How AIFred should implement it:**
- Our "AI Competition Arena" maps directly to this
- Implement the comparison chart with period selector
- Leaderboard with sortable columns
- Head-to-head mode when user selects 2 agents
- **Key files:** `pages/competition.tsx`, `components/competition/Leaderboard.tsx`, `components/charts/ComparisonChart.tsx`
- **Estimated effort:** 2-3 days

---

### 3.6 Settings / Configuration Page

**How NOFX implements it:**
- `SettingsPage.tsx` uses a 4-tab layout: Account, AI Models, Exchanges, Telegram
- Tab bar with icon + label, highlighted active tab in gold
- **Account tab:** email display, password change, beginner/advanced mode toggle
- **AI Models tab:** list of configured models with add/edit modal, status badges
- **Exchanges tab:** list of connected accounts with add/edit modal, multi-exchange per type
- **Telegram tab:** bot configuration
- Each tab lazy-loads data on activation (useEffect watching `activeTab`)
- Modal pattern: full-screen overlay with backdrop blur, dedicated modal components
- Encrypted exchange config submission (`api.updateExchangeConfigsEncrypted`)

**How AIFred should implement it:**
- Match the tabbed layout pattern
- Our tabs: Account, AI Agents, Exchanges, Notifications
- Use modal pattern for add/edit flows
- Lazy-load tab content to keep initial load fast
- Client-side encryption for API keys before sending to server
- **Key files:** `pages/settings.tsx`, `components/settings/AgentConfigModal.tsx`, `components/settings/ExchangeConfigModal.tsx`
- **Estimated effort:** 2-3 days

---

### 3.7 Strategy Studio

**How NOFX implements it:**
- `StrategyStudioPage.tsx` -- 3-column layout
- **Left column:** strategy list (create, duplicate, delete, import/export)
- **Center column:** configuration editors
  - CoinSourceEditor (trading pair selection)
  - IndicatorEditor (technical indicator toggles)
  - RiskControlEditor (stop-loss, position sizing)
  - PromptSectionsEditor (customize AI prompt sections)
  - GridConfigEditor (grid strategy parameters)
- **Right column:** prompt preview + AI testing
  - Generated system prompt display
  - Variant selector (balanced/aggressive/conservative)
  - TokenEstimateBar (prompt token counter)
  - Run test against live AI model
  - Display reasoning, decisions, raw response
- Real-time change tracking with unsaved indicator
- Strategy activation toggle

**How AIFred should implement it:**
- Adapt to our multi-agent architecture
- Per-agent strategy configuration
- Prompt preview essential for tuning AI behavior
- Token estimation helps optimize cost
- AI test-run feature is invaluable for iteration
- **Key files:** `pages/strategy-studio.tsx`, `components/strategy/*`
- **Estimated effort:** 4-5 days

---

### 3.8 State Management Architecture

**How NOFX implements it:**

Three layers:
1. **React Context** (global, rarely changing):
   - `AuthContext`: user object, token, login/logout/register methods
   - `LanguageContext`: current language, setter

2. **Zustand Stores** (shared state, moderate updates):
   - `tradersConfigStore`: all models, all exchanges, supported lists, computed `configuredModels/configuredExchanges`
   - `tradersModalStore`: modal open/close states

3. **SWR** (server state, frequent updates):
   - All API data (traders, accounts, positions, decisions, stats, equity)
   - Automatic polling via `refreshInterval`
   - Cache deduplication
   - `mutate()` for invalidation after mutations

**Pattern summary:**
- Auth + i18n -> Context (wrap whole app)
- UI state + config -> Zustand (minimal stores)
- Server data -> SWR (polling, cache, dedup)
- Component-local state -> useState (forms, toggles, pagination)

**How AIFred should implement it:**
- Same three-layer pattern is ideal
- Replace SWR with TanStack Query if preferred (similar API, more features)
- Zustand for agent config, UI state
- Context for auth (we use Supabase -- already have this)
- **Key insight:** No Redux, no global store for server data -- let SWR/Query handle it
- **Estimated effort:** Already partially implemented, 1 day to align

---

### 3.9 API Layer Architecture

**How NOFX implements it:**

`httpClient.ts` -- Axios singleton with:
- Request interceptor: auto-attaches Bearer token from localStorage
- Response interceptor: handles 401 (redirect to login), 403, 404, 500+ with toast notifications
- Business errors (4xx except 401/403/404) returned to caller for handling
- `ApiResponse<T>` wrapper with success/data/message/errorKey
- Singleton pattern: `export const httpClient = new HttpClient()`
- 30s timeout
- Silent error mode for background requests

`lib/api/` -- Domain-specific API modules:
- `traders.ts`: CRUD for traders, start/stop, status
- `config.ts`: model configs, exchange configs (encrypted)
- `data.ts`: equity history, klines, statistics
- `strategies.ts`: strategy CRUD, activation
- `telegram.ts`: bot configuration
- `helpers.ts`: shared API utilities
- `index.ts`: barrel export as `api` object

**API endpoints pattern (Go backend):**
```
GET    /api/traders              # List traders
POST   /api/traders              # Create trader
GET    /api/traders/:id/status   # Trader status
GET    /api/traders/:id/account  # Account info
GET    /api/traders/:id/positions # Open positions
GET    /api/traders/:id/decisions # Decision history
GET    /api/equity-history       # Equity curve data
GET    /api/klines               # Candlestick data (proxied from exchange)
GET    /api/orders               # Filled order history
GET    /api/open-orders          # Pending orders on exchange
GET    /api/competition          # Competition leaderboard
PUT    /api/model-configs        # Update AI model settings
PUT    /api/exchange-configs     # Update exchange settings (encrypted)
GET    /api/symbols              # Available trading symbols
POST   /api/strategies           # Create strategy
```

**How AIFred should implement it:**
- Match the httpClient singleton pattern (we already use Axios)
- Implement domain-specific API modules under `lib/api/`
- Add 401 handling with redirect to login
- Toast notifications for system errors, let business errors bubble
- Encrypt exchange API keys client-side before sending
- **Key files:** `lib/httpClient.ts`, `lib/api/*.ts`
- **Estimated effort:** 1-2 days (refactor existing)

---

### 3.10 Styling System

**How NOFX implements it:**
- **TailwindCSS** for all layout/spacing/responsive
- **Custom CSS variables** for brand colors:
  - `nofx-gold`: `#F0B90B` (Binance yellow -- primary accent)
  - `nofx-green`: `#0ECB81` (profit/long)
  - `nofx-red`: `#F6465D` (loss/short)
  - `nofx-text-main`: `#EAECEF`
  - `nofx-text-muted`: `#848E9C`
  - `nofx-bg`: `#0B0E11` (deep dark background)
- **Glass morphism** pattern: `nofx-glass` class (backdrop-blur + semi-transparent bg + border)
- **Inline styles** for complex gradients and shadows (not Tailwind)
- **No CSS modules** -- all Tailwind + inline
- **Dark theme only** -- no light mode
- **Responsive:** mobile-first with `md:` breakpoints

**Color palette (Binance-inspired):**
```css
--bg-primary: #0B0E11;
--bg-card: linear-gradient(135deg, #1E2329, #181C21);
--border: #2B3139;
--accent-gold: #F0B90B;
--profit: #0ECB81;
--loss: #F6465D;
--text-primary: #EAECEF;
--text-secondary: #848E9C;
--text-muted: #5E6673;
```

**How AIFred should implement it:**
- Keep TailwindCSS (already using it)
- Define our own color tokens (not Binance yellow -- differentiate our brand)
- Suggested AIFred palette: deep blue/purple primary, cyan accents, same green/red for profit/loss
- Adopt the glass morphism pattern for cards
- Dark-only for v1 (trading UIs are always dark)
- **Key files:** `tailwind.config.ts`, `index.css`
- **Estimated effort:** 0.5 days

---

### 3.11 Backend Trading Architecture (Go)

**How NOFX implements it:**

`trader/` directory -- core trading engine:
- `auto_trader_loop.go`: Main cycle loop
  - Checks `isRunning` flag (mutex-protected)
  - Risk control pause (`stopUntil` timestamp)
  - Safe mode after 3 consecutive AI failures (allows closes, blocks opens)
  - USDC balance monitoring for AI API cost runway
  - Builds trading context (account, positions, candidates, history, market data)
  - Calls AI model for decision
  - Sorts decisions: close positions first, then opens (prevents overflow)
  - Records everything: prompts, CoT, execution logs, equity snapshots

- `auto_trader_decision.go`: Decision execution
  - `saveEquitySnapshot()`: Records account metrics for equity curve
  - `saveDecision()`: Logs AI decision with full audit trail
  - `GetStatus()`: Returns trader metadata (model, exchange, runtime, strategy)
  - `GetAccountInfo()`: Account balance, unrealized P&L, margin usage
  - `GetPositions()`: Open positions with calculated P&L%
  - `recordAndConfirmOrder()`: Submit + confirm order (polls up to 5 times)
  - Exchange-specific order sync for accuracy

- `interface.go`: `Trader` interface + `GridTraderAdapter`
  - Defines contract for exchange integrations
  - Grid trading adapter wraps basic Trader for limit/stop orders

- Per-exchange implementations: `binance/`, `bybit/`, `okx/`, `hyperliquid/`, etc.

**AI decision flow:**
```
1. buildTradingContext()
   -> Gather: account, positions, candidates, history, stats, market data
2. Build system prompt (from strategy config)
3. Build user prompt (from context data)
4. Call AI model API (DeepSeek/Qwen/Claude)
5. Parse structured response (actions array)
6. Sort: closes first, opens second
7. Execute each action
8. Record: prompts, CoT, decisions, execution log, equity snapshot
```

**How AIFred should adapt:**
- Our multi-agent architecture already handles this differently
- Key pattern to adopt: **full audit trail** (save system_prompt, user_prompt, cot_trace per cycle)
- Implement safe mode (pause trading after consecutive failures)
- Sort close-before-open for position management
- Equity snapshot recording independent of decision success
- **Estimated effort:** Backend already exists, 1-2 days to add audit trail fields

---

## 4. Patterns to Adopt

### High Priority
1. **SWR/Query polling pattern** -- No WebSocket needed for MVP; REST polling with smart intervals is simpler and sufficient
2. **Decision audit trail** -- Store and display system_prompt, user_prompt, cot_trace for every AI decision
3. **lightweight-charts for klines** -- Superior to TradingView widget for customization (order markers, price lines)
4. **Tabbed settings with modals** -- Clean UX for config management
5. **Three-layer state** -- Context (auth) + Zustand (config) + SWR (server data)

### Medium Priority
6. **Competition comparison chart** -- Multi-agent equity overlay with time period selector
7. **Strategy studio** -- Prompt preview + token estimation + test-run
8. **Glass morphism cards** -- Professional dark trading UI aesthetic
9. **Safe mode** -- Auto-pause after consecutive AI failures
10. **Close-before-open sorting** -- Prevents position overflow

### Nice to Have
11. **i18n support** -- English + other languages
12. **Beginner/Advanced mode toggle** -- Simplified vs full UI
13. **Client-side encryption** -- For exchange API keys
14. **NOFX watermark pattern** -- Brand watermark on charts (use "AIFred")
15. **Generative avatars** -- Unique per-agent identity

---

## 5. Implementation Priority for AIFred UX Overhaul

| Phase | Feature | NOFX Reference | Effort |
|-------|---------|----------------|--------|
| 1 | Dashboard layout + equity chart | TraderDashboardPage + EquityChart | 2 days |
| 1 | State management alignment (SWR + Zustand) | stores/ + App.tsx | 1 day |
| 1 | API layer refactor | httpClient.ts + lib/api/ | 1 day |
| 2 | Candlestick chart with order markers | AdvancedChart.tsx | 3 days |
| 2 | Decision cards with CoT display | DecisionCard.tsx | 2 days |
| 2 | Settings page (tabbed) | SettingsPage.tsx | 2 days |
| 3 | Competition leaderboard + comparison | CompetitionPage + ComparisonChart | 2 days |
| 3 | Strategy studio | StrategyStudioPage.tsx | 4 days |
| 4 | Beginner onboarding | BeginnerOnboardingPage | 1 day |
| 4 | i18n + polish | i18n/ + animations | 2 days |

**Total estimated effort: ~20 days for complete feature parity**

---

## 6. Key Architectural Differences

| Aspect | NOFX | AIFred |
|--------|------|--------|
| Backend | Go monolith | Node.js/Python micro-services |
| Database | Embedded file-based | Supabase (Postgres) |
| Auth | Custom JWT | Supabase Auth |
| AI Models | Single model per trader | Multi-agent ensemble |
| Hosting | Docker/Railway (self-host) | Railway + Vercel (managed) |
| Exchange | 10 exchanges | Hyperliquid primary |
| Strategy | Per-trader config | Per-agent + fusion layer |

These differences mean we should adopt NOFX's **frontend patterns** closely while keeping our own **backend architecture**. The UI patterns are production-proven and well-structured.

---

## 7. Files to Reference During Implementation

When building each feature, reference these NOFX source files directly:

```
Dashboard:     web/src/pages/TraderDashboardPage.tsx
Equity Chart:  web/src/components/charts/EquityChart.tsx
Kline Chart:   web/src/components/charts/AdvancedChart.tsx
Chart Tabs:    web/src/components/charts/ChartTabs.tsx
Decisions:     web/src/components/trader/DecisionCard.tsx
Competition:   web/src/components/trader/CompetitionPage.tsx
Comparison:    web/src/components/charts/ComparisonChart.tsx
Settings:      web/src/pages/SettingsPage.tsx
Strategy:      web/src/pages/StrategyStudioPage.tsx
HTTP Client:   web/src/lib/httpClient.ts
Zustand Store: web/src/stores/tradersConfigStore.ts
Auth Context:  web/src/contexts/AuthContext.tsx
Types:         web/src/types/trading.ts
Indicators:    web/src/utils/indicators.ts
```

All accessible at: `https://github.com/NoFxAiOS/nofx/blob/dev/{path}`
