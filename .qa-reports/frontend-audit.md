# Frontend Audit Report — AIFred Trading Platform
## Date: 2026-04-01
## Auditor: Senior Frontend Developer

---

### Executive Summary

**Overall Health: CONDITIONAL PASS**

The AIFred Trading Platform frontend is functional and demonstrates solid architecture decisions (dynamic imports, error boundaries, react-query for data fetching, middleware-level auth + rate limiting). However, several critical and high-severity issues must be addressed before public launch, including a broken function reference, duplicate React Query providers, missing accessibility, CLAUDE.md animation safety violations, and a hardcoded auth secret fallback.

**Files Audited:** 19 source files (13 components, 4 pages, 1 middleware, 1 lib config)
**Total Lines of Code (approx):** ~5,200 (excluding node_modules)

---

### Critical Issues (Must Fix Before Launch)

**1. CRITICAL — `loadCredentials` function does not exist**
- **File:** `components/trading/TradingSettings.tsx:543`
- **Severity:** P0 / Runtime crash
- **Description:** The autonomous trading scan handler calls `loadCredentials(connBrokers[0].id)`, but this function is never defined or imported anywhere in the codebase. When a user enables autonomous live trading, this will throw a `ReferenceError` at runtime, crashing the scan loop.
- **Fix:** Either remove the call (credentials are server-side env vars now) or import/define the function. Since the comment on line 337 of TradingDashboard.tsx says "Credentials are now server-side only (env vars)", the `loadCredentials` call should be removed entirely and `brokerCreds` should always be `undefined`.

**2. CRITICAL — Duplicate `QueryClientProvider` nesting causes silent data issues**
- **File:** `app/layout.tsx`, `components/Providers.tsx`, `components/providers/Web3Provider.tsx`
- **Severity:** P0 / Data integrity
- **Description:** The app tree is: `Providers (QueryClientProvider #1) -> Web3Provider (QueryClientProvider #2) -> children`. This creates two independent QueryClient instances. Components using `useQuery` inside the Web3Provider context will use QueryClient #2, while components outside it use #1. This means:
  - Cache is not shared between the two providers
  - `queryClient.invalidateQueries()` in one context won't affect the other
  - The `staleTime: 5_000` and `retry: 1` defaults from Providers.tsx are NOT applied inside Web3Provider
- **Fix:** Remove the `QueryClientProvider` from `Web3Provider.tsx` and pass the existing queryClient from `Providers.tsx` via context, or restructure so there is only one `QueryClientProvider` in the tree.

**3. CRITICAL — Hardcoded fallback auth secret in production path**
- **File:** `middleware.ts:39`, `lib/auth.ts:39`
- **Severity:** P0 / Security
- **Description:** Both files use `process.env.NEXTAUTH_SECRET || "aifred-dev-secret-change-in-prod"` as the JWT secret. If the environment variable is not set in production (e.g., misconfigured Railway deploy), the app silently falls back to a known hardcoded secret, allowing anyone to forge valid JWT tokens and bypass authentication entirely.
- **Fix:** Remove the fallback. If `NEXTAUTH_SECRET` is not set, the app should fail to start or refuse requests with a clear error. Add a startup check.

**4. CRITICAL — `ignoreBuildErrors: true` in next.config.ts**
- **File:** `next.config.ts:5`
- **Severity:** P0 / Build safety
- **Description:** TypeScript errors are silently ignored during `next build`. This means broken imports (like `loadCredentials` above), type mismatches, and other compile-time errors will ship to production undetected.
- **Fix:** Set `ignoreBuildErrors: false` (or remove the option) and fix all TypeScript errors before launch.

---

### Warnings (Should Fix)

**5. HIGH — Framer Motion `initial` with `opacity: 0` violates CLAUDE.md SSR rule**
- **Files:** Throughout `TradingDashboard.tsx` (30+ instances), `TradingSettings.tsx` (15+ instances)
- **Severity:** P1 / Hydration & UX
- **Description:** CLAUDE.md explicitly states: "Never use `opacity: 0` as an initial state for interactive elements (buttons, modals, forms) as it breaks click handlers in SSR hydration." Both major components use `initial={{ opacity: 0 }}` extensively on motion.div elements wrapping interactive content (buttons, trade controls, form inputs). While both pages are loaded with `ssr: false`, the CLAUDE.md rule exists because future refactoring could re-enable SSR.
- **Impact:** Currently mitigated by `ssr: false` dynamic imports, but fragile.
- **Fix:** Use `initial={false}` on all motion elements that wrap interactive content, as recommended in CLAUDE.md. For entrance animations, use CSS animations or `initial={false}` with `animate`.

**6. HIGH — All components are "use client" — zero server components**
- **Files:** All 13 component files
- **Severity:** P1 / Performance
- **Description:** Every single component is marked `"use client"`. This means the entire component tree is client-rendered, increasing JavaScript bundle size and time-to-interactive. Server components could handle layout shells, static text, and data fetching.
- **Fix:** Refactor layout-level components (headers, footers, static sections) to be server components where possible. At minimum, `app/layout.tsx` should keep `Providers` as client but wrap static UI in server components.

**7. HIGH — No accessibility (a11y) support whatsoever**
- **Files:** All components
- **Severity:** P1 / Accessibility & Legal
- **Description:** Zero `aria-*` attributes found in the entire codebase. Specific issues:
  - No `aria-label` on icon-only buttons (Settings gear, close X buttons, kill switch)
  - No `role="dialog"` or `aria-modal` on modals (ExecuteTradeModal, TradeConfirmationDialog, broker connection modal)
  - No `aria-live` regions for dynamic content (trade toast, activity feed, system health status)
  - No keyboard navigation support beyond native HTML (custom toggles, dropdown menus)
  - SystemHealthDot tooltip is mouse-only (no focus/keyboard trigger)
  - Color is the sole indicator of state in many places (green/red for PnL, status dots)
- **Fix:** Add comprehensive ARIA attributes. At minimum: label all icon buttons, mark modals with `role="dialog"`, add `aria-live="polite"` to dynamic status regions.

**8. HIGH — Duplicate ErrorBoundary class definitions**
- **Files:** `app/page.tsx:6-43` and `app/trading/page.tsx:12-49`
- **Severity:** P1 / Maintainability
- **Description:** Identical ErrorBoundary class components are copy-pasted in two page files. Both have the same nuclear "Clear Data & Reload" button that calls `localStorage.clear()` — wiping ALL app state (broker connections, trading controls, autonomous settings, welcome state) as a recovery mechanism. This is aggressive for production.
- **Fix:** Extract to a shared `components/ErrorBoundary.tsx`. Add a less destructive recovery option (e.g., just reload without clearing localStorage).

**9. HIGH — Duplicate settings routes**
- **Files:** `app/settings/page.tsx` and `app/trading/settings/page.tsx`
- **Severity:** P1 / Architecture
- **Description:** Both files are byte-for-byte identical, rendering the same `TradingSettings` component. This creates two URLs (`/settings` and `/trading/settings`) for the same page, which confuses users and search engines.
- **Fix:** Remove one route and redirect to the canonical one.

**10. MEDIUM — `fetchActivities` missing from useEffect dependency array**
- **File:** `components/trading/TradingDashboard.tsx:2872-2876`
- **Severity:** P2 / React correctness
- **Description:** The `ActivityTab` useEffect calls `fetchActivities()` and sets up an interval, but `fetchActivities` is not in the dependency array. Since `fetchActivities` is not wrapped in `useCallback`, this is actually safe (it captures stale closure, but since it refetches from API each time, the practical impact is minimal). However, the `mergeWithLocal` function is redefined each render and creates a new closure each time.
- **Fix:** Wrap `fetchActivities` in `useCallback` and add to dependency array, or use `useRef` for the interval.

**11. MEDIUM — No error handling for fetch response status codes**
- **Files:** `AccountSummaryBar.tsx:8`, `TradingModeBanner.tsx:8`, `TradeFeed.tsx:22`, `LivePositionsPanel.tsx:19`
- **Severity:** P2 / Reliability
- **Description:** All `useQuery` queryFn callbacks do `.then(r => r.json())` without checking `r.ok`. If the API returns a 401 (token expired), 500, or 429 (rate limited), the response body may not be valid JSON, causing a silent parse error that react-query catches as a failed query — but the user sees no useful error message.
- **Fix:** Add response status checking: `if (!r.ok) throw new Error(\`HTTP ${r.status}\`)`

**12. MEDIUM — Large monolithic TradingDashboard.tsx (~3,600 lines)**
- **File:** `components/trading/TradingDashboard.tsx`
- **Severity:** P2 / Maintainability & Performance
- **Description:** This single file contains: the main dashboard, ExecuteTradeModal, DashboardErrorBoundary, OverviewTab, RegimeTab, TradesTab, ActivityTab, AgentsTab, and numerous helper functions/constants. This creates:
  - Slow IDE performance and code review difficulty
  - Everything re-bundles together (no code splitting between tabs)
  - High merge conflict risk
- **Fix:** Extract each tab into its own file under `components/trading/tabs/`. Extract modals into `components/modals/`.

**13. MEDIUM — `setTimeout` for toast dismissal without cleanup**
- **File:** `components/trading/TradingDashboard.tsx:830`
- **Severity:** P2 / Memory leak
- **Description:** `setTimeout(() => setTradeToast(null), 12000)` is called in `handleTradeExecuted` without storing the timer ID for cleanup. If the component unmounts before 12 seconds, this will attempt to set state on an unmounted component.
- **Fix:** Use a `useRef` to store the timer ID and clear it in a cleanup effect.

**14. MEDIUM — External font loading via CSS @import in JavaScript**
- **Files:** `TradingDashboard.tsx:217`, `TradingSettings.tsx:171`
- **Severity:** P2 / Performance
- **Description:** Google Fonts are loaded by injecting a `<style>` tag containing `@import url(...)` at runtime. This:
  - Blocks rendering until the font loads
  - Is duplicated (both files inject the same fonts)
  - Bypasses Next.js font optimization
- **Fix:** Use `next/font/google` to load JetBrains Mono and Outfit with automatic optimization and zero layout shift.

**15. MEDIUM — No error boundary on settings pages**
- **Files:** `app/settings/page.tsx`, `app/trading/settings/page.tsx`
- **Severity:** P2 / Reliability
- **Description:** Unlike the home page and trading page which wrap content in ErrorBoundary, both settings pages render `TradingSettings` without any error boundary. A runtime error in settings will show the default Next.js error page.
- **Fix:** Wrap in the shared ErrorBoundary component.

---

### Observations (Nice to Have)

**16. LOW — `ccxt` bundled as a frontend dependency**
- **File:** `package.json`
- **Description:** `ccxt` is a server-side crypto exchange library (4+ MB). It's listed as a dependency and marked as `serverExternalPackages` in `next.config.ts`, which should prevent client bundling. Verify this is only used in API routes.

**17. LOW — Hardcoded "7 AGENTS ONLINE" text**
- **File:** `TradingDashboard.tsx:979`
- **Description:** The header always shows "7 AGENTS ONLINE" regardless of actual agent status. This should either be dynamic or clearly labeled as a brand element.

**18. LOW — `localStorage.clear()` in error boundaries is destructive**
- **Files:** `app/page.tsx:31`, `app/trading/page.tsx:37`, `TradingDashboard.tsx:759`
- **Description:** Error recovery wipes ALL localStorage including auth-related data, broker connections, trading controls, and autonomous settings. A more surgical approach would only clear AIFred-specific keys.

**19. LOW — No responsive design for TradeConfirmationDialog**
- **File:** `components/TradeConfirmationDialog.tsx`
- **Description:** The dialog uses `max-w-md` but has no mobile-specific adjustments. On very small screens, content may overflow.

**20. LOW — Inline styles used extensively**
- **Files:** `TradingDashboard.tsx`, `TradingSettings.tsx`
- **Description:** Heavy use of inline `style={{}}` for font families, gradients, and animations. These could be Tailwind utilities or CSS classes for consistency and cacheability.

**21. LOW — No favicon or meta OG tags for social sharing**
- **File:** `app/layout.tsx`
- **Description:** Only `favicon.ico` is referenced. No Open Graph meta tags, Twitter cards, or manifest.json for PWA support.

**22. LOW — `useMemo` dependency on `activities` state for `userTrades`**
- **File:** `TradingDashboard.tsx:2887`
- **Description:** `userTrades` is derived from `localStorage` but uses `[activities]` as its dependency. This is a clever hack to re-derive when activities refresh, but reading localStorage in `useMemo` is a side effect and could cause inconsistencies.

**23. LOW — ConnectWallet dropdown position calculated via getBoundingClientRect**
- **File:** `components/wallet/ConnectWallet.tsx:22-28`
- **Description:** Dropdown position is calculated on toggle but not recalculated on scroll or resize. If the user scrolls while the dropdown is open, it will be mispositioned.

**24. LOW — No test files found**
- **Description:** Zero test files (no `__tests__`, no `*.test.tsx`, no `*.spec.ts`) exist in the codebase. For a trading platform handling real money, this is a significant risk.

---

### Component Health Matrix

| Component | Types | Error Handling | Loading States | Empty States | Accessibility | Grade |
|---|---|---|---|---|---|---|
| TradingDashboard.tsx | Good (interfaces defined) | Good (ErrorBoundary + per-tab) | Good (spinners per tab) | Good (per section) | None | B- |
| TradingSettings.tsx | Good | Partial (no error boundary) | Partial (no loading skeleton) | N/A | None | C+ |
| AccountSummaryBar.tsx | Adequate (uses `??` defaults) | Partial (no HTTP error check) | None (no loading state) | Good (defaults to 0) | None | C |
| KillSwitchButton.tsx | Good | Good (mutation states) | Good (pending states) | N/A | None | B- |
| SystemHealthDot.tsx | Good | Good (fallback states) | Good (unknown state) | N/A | None (mouse-only tooltip) | C+ |
| LivePositionsPanel.tsx | Good (Position interface) | Partial (no HTTP check) | Good | Good (empty message) | None | B- |
| TradeFeed.tsx | Good (Trade interface) | Partial (no HTTP check) | None | Good (empty message) | None | C+ |
| TradingModeBanner.tsx | Adequate | Partial (no HTTP check) | None | Good (defaults to paper) | None | C |
| TradeConfirmationDialog.tsx | Good (Props interface) | Good | Good (countdown) | N/A | None (no modal role) | B- |
| ConnectWallet.tsx | Good | Good (error display + retry) | Good (pending state) | Good (no wallets msg) | Partial (keyboard Esc) | B |
| HyperliquidBalance.tsx | Good (interfaces) | Good (error + retry) | Good | Good (no positions) | None | B |
| Providers.tsx | Adequate | N/A | N/A | N/A | N/A | B |
| Web3Provider.tsx | Adequate | N/A | N/A | N/A | N/A | C (dup QCP) |
| ErrorBoundary (page.tsx) | Good | Good | N/A | N/A | None | B- |

---

### Test Coverage Assessment

**Current Coverage: 0%**

No test files, no testing framework configured, no test scripts in `package.json`.

**Recommended Test Plan (Priority Order):**

1. **Unit tests for data transforms:** `timeAgo()`, `timeSince()`, `fmt()`, `pct()`, sanitize functions
2. **Component tests:** AccountSummaryBar with mock API data, KillSwitchButton state transitions, TradeConfirmationDialog countdown
3. **Integration tests:** Auth flow (login -> redirect -> protected page), trade execution flow (modal -> API -> toast -> activity log)
4. **E2E tests:** Full trading workflow with mocked API responses

**Recommended Framework:** Vitest + React Testing Library + Playwright for E2E.

---

### Security Assessment

| Check | Status | Notes |
|---|---|---|
| XSS via dangerouslySetInnerHTML | PASS | No usage found |
| XSS via user data rendering | PASS | All user data rendered as text nodes |
| Auth token handling | WARN | Fallback secret in middleware/auth.ts |
| Sensitive data in localStorage | WARN | Broker connection status cached in localStorage |
| API credentials in client code | PASS | Credentials are server-side env vars |
| CSRF protection | PASS | next-auth handles CSRF tokens |
| Rate limiting | PASS | Middleware rate limits trading endpoints |
| Input validation (client) | PARTIAL | Quantity field has min/step but no max |

---

### Performance Assessment

| Check | Status | Notes |
|---|---|---|
| Code splitting | PARTIAL | Dynamic imports for pages, but tabs within TradingDashboard are all bundled together |
| Bundle size | WARN | recharts + framer-motion + wagmi + viem = significant JS payload |
| Unnecessary re-renders | WARN | `getConnectedBrokers()` called in render path (line 955) causes localStorage reads every render |
| Lazy loading | GOOD | Key components use `dynamic(() => import(...), { ssr: false })` |
| Image optimization | N/A | No images used (icon-only via lucide-react) |
| Font loading | WARN | Runtime @import instead of next/font |

---

### React Error #31 Verification

**AccountSummaryBar.tsx:** FIXED. Lines 22-24 safely extract `openPositions` as a number, checking `typeof` and falling back to a nested path. The `regime` and `botStatus` values are coerced to strings before rendering. No object-as-child risk.

**TradingDashboard.tsx ActivityTab:** FIXED. Lines 2820-2828 include a `sanitize` function that explicitly checks `typeof e.title === "string"` and `typeof e.message === "string"` before rendering, with string fallbacks. This prevents React Error #31 when API returns unexpected object shapes.

**OverviewTab (line 2249-2255):** PARTIALLY FIXED. The sanitize function here is less rigorous — it does `e.message || e.title || e.asset || "Trade"` without `typeof` checks. If `e.message` is an object (truthy but not a string), it would still cause React Error #31. This should use the same `typeof` guards as ActivityTab.

---

### Launch Readiness: CONDITIONAL

**Must fix before launch (blockers):**
1. Remove/fix `loadCredentials` call in TradingSettings.tsx (issue #1)
2. Fix duplicate QueryClientProvider (issue #2)
3. Remove hardcoded auth secret fallback (issue #3)
4. Set `ignoreBuildErrors: false` and fix all TS errors (issue #4)

**Should fix before launch (high priority):**
5. Add basic accessibility (aria-labels on buttons, modal roles)
6. Fix OverviewTab sanitize function to match ActivityTab rigor
7. Remove duplicate settings route
8. Add error boundaries to settings pages

**Can fix post-launch:**
- Extract TradingDashboard.tsx into smaller files
- Add test coverage
- Migrate to next/font
- Add responsive improvements
