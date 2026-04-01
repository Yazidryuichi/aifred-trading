# Backend API Audit Report -- AIFred Trading Platform
## Date: 2026-04-01
## Auditor: Senior Backend Developer

---

### Executive Summary

**Overall Health: CONDITIONAL PASS**

The AIFred Trading Platform has a well-structured API layer with solid trading logic, proper authentication via NextAuth, and intelligent rate limiting in middleware. However, several critical and high-severity issues must be resolved before public launch. The most urgent concerns are: a hardcoded JWT secret fallback, credentials stored as plaintext JSON on disk, file-system race conditions on concurrent writes, the autoscan endpoint bypassing auth when calling execute internally, and `ignoreBuildErrors: true` masking potential type-safety regressions.

---

### API Endpoint Inventory

| Method | Path | Auth | Rate Limit | Status |
|--------|------|------|-----------|--------|
| GET/POST | `/api/auth/[...nextauth]` | Public | None | OK |
| GET | `/api/trading` | JWT (middleware) | 10 req/min | OK |
| POST | `/api/trading/execute` | JWT (middleware) | 1 per 10s | OK |
| GET/POST | `/api/trading/autoscan` | JWT (middleware) | 1 per 60s | WARN -- internal fetch bypasses auth |
| POST | `/api/trading/kill-switch` | JWT (middleware) | 10 req/min | WARN -- no action validation |
| GET/POST | `/api/trading/activity` | JWT (middleware) | 10 req/min | OK |
| GET/POST | `/api/trading/backtest` | JWT (middleware) | 10 req/min | OK |
| GET | `/api/trading/broker-status` | JWT (middleware) | 10 req/min | OK |
| GET/POST/DELETE | `/api/trading/brokers` | JWT (middleware) | 10 req/min | WARN -- secrets storage |
| POST | `/api/trading/brokers/test` | JWT (middleware) | 10 req/min | OK |
| GET/POST | `/api/trading/controls` | JWT (middleware) | 10 req/min | OK |
| GET | `/api/trading/live-prices` | JWT (middleware) | 10 req/min | OK |
| GET | `/api/trading/paper-status` | JWT (middleware) | 10 req/min | OK |
| GET | `/api/trading/performance` | JWT (middleware) | 10 req/min | OK |
| GET | `/api/trading/prices` | JWT (middleware) | 10 req/min | OK |
| GET | `/api/trading/regime` | JWT (middleware) | 10 req/min | OK |
| GET | `/api/trading/stats` | JWT (middleware) | 10 req/min | OK |
| GET | `/api/trading/system-health` | JWT (middleware) | 10 req/min | OK |

**Total: 18 route files, 25+ handler functions**

---

### Critical Issues (Must Fix Before Launch)

#### 1. CRITICAL -- Hardcoded JWT Secret Fallback
**File:** `middleware.ts:39`, `lib/auth.ts:39`
**Severity:** CRITICAL
**Description:** Both middleware and auth config use `"aifred-dev-secret-change-in-prod"` as a fallback when `NEXTAUTH_SECRET` is not set. If the env var is ever misconfigured or missing in production, all JWT tokens are signed with a publicly known secret, allowing anyone to forge valid sessions.
**Fix:** Remove the fallback entirely. Crash at startup if `NEXTAUTH_SECRET` is missing:
```ts
secret: process.env.NEXTAUTH_SECRET ?? (() => { throw new Error("NEXTAUTH_SECRET is required"); })(),
```

#### 2. CRITICAL -- Autoscan Internal Fetch Bypasses Authentication
**File:** `app/api/trading/autoscan/route.ts:400-401`
**Severity:** CRITICAL
**Description:** The `executeSignal()` function makes an internal HTTP `fetch()` to `/api/trading/execute` without forwarding the user's auth token. This means:
- On Vercel, the request hits middleware without a JWT and gets rejected (401), silently failing auto-execution.
- If middleware were relaxed for internal calls, it would be an auth bypass.
**Fix:** Either call the execute logic directly as a function import (shared module), or forward the `Authorization` / cookie header from the original request.

#### 3. CRITICAL -- Broker Credentials Stored as Plaintext JSON
**File:** `app/api/trading/brokers/route.ts:245-248` (`.broker-secrets.json` in `/tmp`)
**Severity:** CRITICAL
**Description:** Exchange API keys and secrets are written to `/tmp/aifred-data/.broker-secrets.json` as plaintext JSON. On shared hosting or if the server is compromised, these are trivially exfiltrated. On Vercel, `/tmp` is ephemeral but shared across function invocations within the same instance.
**Fix:** Encrypt secrets at rest using `NEXTAUTH_SECRET` as a key (AES-256-GCM), or use a proper secrets manager (e.g., Vercel encrypted environment variables, AWS Secrets Manager).

#### 4. CRITICAL -- File System Race Conditions on Concurrent Writes
**Files:** Multiple -- `activity/route.ts`, `controls/route.ts`, `brokers/route.ts`, `autoscan/route.ts`, `strategy-learning.ts`
**Severity:** CRITICAL
**Description:** All file-based persistence uses `readFileSync` -> modify -> `writeFileSync` without any locking mechanism. If two concurrent requests read the same file, modify it, and write back, one write will silently overwrite the other (lost update). This affects:
- Activity log (entries dropped)
- Strategy stats (learning data corrupted)
- Trading controls (state inconsistency)
- Daily PnL tracking (incorrect accounting)
**Fix:** Use file-level advisory locking (`proper-lockfile` or `lockfile` npm package), or migrate to a database (SQLite at minimum). For Vercel serverless, use Vercel KV, Upstash Redis, or Supabase.

#### 5. CRITICAL -- `ignoreBuildErrors: true` in next.config.ts
**File:** `next.config.ts:5`
**Severity:** CRITICAL
**Description:** TypeScript build errors are silently ignored. This means type-safety regressions, missing imports, or incorrect function signatures can ship to production without any build-time gate. For a financial platform handling real money, this is unacceptable.
**Fix:** Set `ignoreBuildErrors: false`, then fix any build errors that surface.

---

### Security Assessment

#### Authentication
- **Mechanism:** NextAuth with CredentialsProvider, JWT sessions (24h expiry). Single admin user defined via `AUTH_EMAIL` and `AUTH_PASSWORD_HASH` env vars.
- **Strength:** bcrypt password hashing, JWT-based stateless sessions.
- **Weakness:** Single-user credential store via env vars is fine for personal use but does not scale. No MFA support.
- **FINDING:** The hardcoded JWT secret fallback (Critical #1) is the most dangerous auth vulnerability.

#### Authorization
- All `/api/trading/*` routes are protected by middleware JWT check -- GOOD.
- The `/api/auth/*` routes are correctly excluded from auth -- GOOD.
- Static assets and login page are excluded -- GOOD.
- **FINDING:** No role-based access control. If multi-user is ever needed, all users would have full admin privileges.

#### Rate Limiting
- Execute: 1 request per 10 seconds per user -- GOOD.
- Autoscan: 1 request per 60 seconds per user -- GOOD.
- General API: 10 requests per 60 seconds per user -- GOOD.
- **FINDING:** In-memory rate limiting resets on every serverless cold start (Vercel). An attacker could exploit cold starts to bypass limits by hitting different regions or waiting for instance rotation. Consider Vercel KV or Upstash Redis for distributed rate limiting.

#### Input Validation
- `POST /api/trading/execute`: Validates `symbol`, `side` (LONG/SHORT), `quantity > 0` -- GOOD.
- `POST /api/trading/backtest`: Validates date range, leverage (1-10), confirmations (1-8) -- GOOD.
- `POST /api/trading/kill-switch`: Only validates `action` is "kill" or "resume" -- GOOD.
- `POST /api/trading/activity`: Validates `type` and `message` required -- GOOD.
- `POST /api/trading/brokers`: Validates `brokerId` against registry, checks required credentials -- GOOD.
- **FINDING:** No maximum length validation on string inputs. A malicious user could send extremely large JSON payloads to exhaust memory. Add `Content-Length` limits.

#### Injection Vulnerabilities
- **SQL Injection:** N/A -- no SQL database.
- **Command Injection:** No child process execution found -- GOOD.
- **Path Traversal:** File paths are constructed with `join()` using hardcoded directory names, never from user input -- GOOD.
- **SSRF:** The autoscan `executeSignal()` constructs a URL from `VERCEL_URL` or `NEXT_PUBLIC_APP_URL` env vars, not user input -- LOW RISK.

#### Secrets Management
- Auth credentials: env vars (`AUTH_EMAIL`, `AUTH_PASSWORD_HASH`) -- GOOD.
- JWT secret: env var with hardcoded fallback -- BAD (Critical #1).
- Broker API keys: plaintext JSON in `/tmp` -- BAD (Critical #3).
- Railway URL: env var with hardcoded fallback (production URL exposed in source) -- MEDIUM RISK.
  - **File:** `app/api/trading/paper-status/route.ts:5`, `system-health/route.ts:3`
  - The default `https://aifred-orchestrator-production.up.railway.app` is committed to source code. This reveals infrastructure details.

#### CORS
- No explicit CORS configuration found. Next.js defaults apply (same-origin for API routes). This is acceptable for a same-domain deployment but should be explicitly configured if the API is consumed from other origins.

---

### Warnings (Should Fix)

#### 1. WARNING -- Railway Backend URL Hardcoded in Source
**Files:** `app/api/trading/paper-status/route.ts:5`, `app/api/trading/system-health/route.ts:3`
**Description:** The production Railway URL `https://aifred-orchestrator-production.up.railway.app` is hardcoded as a default. This exposes infrastructure details and would break if the Railway deployment URL changes.
**Fix:** Remove the hardcoded default; require `RAILWAY_BACKEND_URL` env var.

#### 2. WARNING -- Duplicated Code Across Route Files
**Files:** `activity/route.ts`, `execute/route.ts`, `autoscan/route.ts`, `controls/route.ts`, `brokers/route.ts`
**Description:** The `readActivities()`, `appendActivity()`, `ensureTmpDir()`, `CRYPTO_BINANCE` map, and live price fetching logic are copy-pasted across 5+ route files. Changes to one copy may not propagate, leading to inconsistent behavior.
**Fix:** Extract shared helpers into `lib/activity-log.ts`, `lib/prices.ts`, and `lib/storage.ts`.

#### 3. WARNING -- In-Memory Caches Have No Bound
**Files:** `execute/route.ts:49` (livePriceCache), `prices/route.ts:6` (priceCache), `regime/route.ts:13` (regimeCache), `backtest/route.ts:12` (backtestCache)
**Description:** Multiple route files maintain in-memory `Map` caches. While some have eviction logic (backtest, regime), others (livePriceCache, priceCache) grow unboundedly. On a long-lived server process, this is a slow memory leak.
**Fix:** Add maximum size limits and LRU eviction to all caches. Consider a shared cache (Redis).

#### 4. WARNING -- Kill Switch Has No Persistence or Verification
**File:** `app/api/trading/kill-switch/route.ts`
**Description:** The kill switch POSTs to a Python backend `/kill` endpoint. If that fails, it returns `{ success: true, method: "file" }` but never actually creates the kill file. The "resume" path has the same issue. Additionally, there is no state tracking -- calling GET to check kill switch status is not implemented.
**Fix:** Actually create the kill file on fallback. Add a GET handler to check status. Persist kill state to `/tmp/aifred-data/kill-switch.json`.

#### 5. WARNING -- Autoscan Open Positions Not Persisted
**File:** `app/api/trading/autoscan/route.ts:541-582`
**Description:** The autoscan takes `openPositions` as input from the request body and returns `updatedPositions` in the response, but never persists the position state. If the frontend loses state (refresh, crash), all position tracking is lost.
**Fix:** Persist open positions to `/tmp/aifred-data/open-positions.json` and load them as the default when `inputPositions` is empty.

#### 6. WARNING -- Simulated Technical/Sentiment Signals Use Random Numbers
**File:** `app/api/trading/activity/route.ts:198-233`
**Description:** `generateTechnicalSignals()` and `generateSentimentSignals()` produce random RSI, FinBERT scores, and Fear & Greed values for display in the activity log. This could mislead users into thinking these are real signals.
**Fix:** Clearly label seed/demo data as simulated, or remove random generation in favor of actual computed values from the regime/confirmation pipeline.

#### 7. WARNING -- Paper Trade Outcome Is Purely Random
**File:** `app/api/trading/execute/route.ts:887-892`
**Description:** Paper trade PnL is determined by `Math.random()` compared against confidence. This means strategy learning (`recordTradeOutcome`) is training on noise, not actual market movements. The "learning" system learns from random data.
**Fix:** For paper trades, compute simulated PnL based on actual price movement over a time horizon (e.g., check the price 1 hour later via a background job).

#### 8. WARNING -- No Request Body Size Limit
**Files:** All POST handlers
**Description:** None of the POST endpoints enforce a maximum request body size. A malicious user could send multi-GB payloads to exhaust server memory.
**Fix:** Add body size limits in `next.config.ts` or middleware.

#### 9. WARNING -- `any` Types in Critical Code Paths
**Files:** `brokers/route.ts:262` (`let ccxt: any`), `brokers/test/route.ts:6` (`let ccxt: any`), `execute/route.ts` (ccxt usage)
**Description:** The `ccxt` library is imported via `require()` with `any` typing, bypassing TypeScript safety in live trade execution code paths.
**Fix:** Use proper ccxt TypeScript types or create a typed wrapper module.

#### 10. WARNING -- Backtest Cache Key Does Not Include All Parameters
**File:** `app/api/trading/backtest/route.ts:19`
**Description:** The cache key does not include `initialCapital`, which means different capital values for the same date range will return cached results from the first request.
**Fix:** Actually, `initialCapital` IS included in the key. However, the key uses string concatenation with `:` separator, which could collide if parameter values contain `:`. Use JSON.stringify or a hash function.

---

### Data Flow Diagram

```
                                  +-------------------+
                                  |   Next.js Client  |
                                  |  (React Frontend) |
                                  +--------+----------+
                                           |
                                    HTTPS requests
                                           |
                                  +--------v----------+
                                  |   middleware.ts    |
                                  | - JWT validation   |
                                  | - Rate limiting    |
                                  |   (in-memory Map)  |
                                  +--------+----------+
                                           |
                          +----------------+----------------+
                          |                |                |
                 +--------v------+ +------v-------+ +------v--------+
                 | /api/trading/ | | /api/trading | | /api/trading  |
                 |   execute     | |   autoscan   | |   brokers     |
                 +--------+------+ +------+-------+ +------+--------+
                          |               |                |
              +-----------+------+  +-----+-----+   +-----+------+
              |                  |  |           |   |            |
     +--------v---+   +---------v--v-+ +-------v---v---+  +-----v---------+
     | Binance US |   | HMM Regime   | | Strategy      |  | /tmp/aifred/  |
     | API (prices|   | Detection    | | Learning      |  | .broker-      |
     | + klines)  |   | (lib/hmm-    | | (lib/strategy-|  |  secrets.json |
     +------------+   |  regime.ts)  | |  learning.ts) |  | activity-log  |
                      +--------------+ +-------+-------+  | controls.json |
                                               |          | daily-pnl.json|
                                       +-------v-------+  +---------------+
                                       | /tmp/aifred/  |
                                       | strategy-     |
                                       |  stats.json   |
                                       +---------------+
                          |
              +-----------v-----------+
              |    External APIs      |
              | - Binance US (prices) |
              | - Hyperliquid (prices)|
              | - Railway Python      |
              |   Orchestrator        |
              | - ccxt (live trades)  |
              +-----------------------+
```

### Data Persistence Strategy

| Data | Storage | Persistence | Risk |
|------|---------|------------|------|
| Trading data (historical) | `data/trading-data.json` | Build-time, read-only | LOW -- immutable at runtime |
| Activity log | `/tmp/aifred-data/activity-log.json` | Ephemeral (Vercel) | HIGH -- lost on redeploy |
| Strategy stats | `/tmp/aifred-data/strategy-stats.json` | Ephemeral | HIGH -- learning data lost |
| Trading controls | `/tmp/aifred-data/trading-controls.json` | Ephemeral | MEDIUM -- resets to defaults |
| Broker credentials | `/tmp/aifred-data/.broker-secrets.json` | Ephemeral | CRITICAL -- plaintext, lost on redeploy |
| Broker connections | `/tmp/aifred-data/broker-connections.json` | Ephemeral | MEDIUM |
| Daily PnL | `/tmp/aifred-data/daily-pnl.json` | Ephemeral | HIGH -- risk limits reset |
| Open positions | Client-side only (passed in request body) | None server-side | HIGH -- lost on refresh |

---

### External Dependencies

| Dependency | Usage | Timeout | Retry | Fallback | Reliability |
|-----------|-------|---------|-------|----------|------------|
| **Binance US API** | Price feeds, klines for regime detection & confirmations | 3-10s (AbortSignal) | None | Mock prices (hardcoded) | GOOD -- timeouts and fallbacks implemented |
| **Hyperliquid Mainnet** | Live prices (`/api/trading/live-prices`) | 8s (AbortSignal) | None | Stale cache | GOOD -- returns stale cache on failure |
| **Hyperliquid Testnet** | Health check only | 8s (AbortSignal) | None | Reports "down" | GOOD -- graceful degradation |
| **Railway Python Backend** | Paper status, system health, kill switch | 5-10s (AbortSignal) | None | Returns offline status | GOOD -- graceful degradation |
| **ccxt (npm)** | Live trade execution (Binance, Coinbase, Kraken, Bybit) | 30s | None | Paper mode fallback | MEDIUM -- no retry on transient errors |

**Positive findings:**
- All external API calls use `AbortSignal.timeout()` -- no hanging requests.
- Binance price fetching has graceful fallback to mock/cached prices.
- Hyperliquid has stale cache fallback.
- System health checks run in parallel with `Promise.all()`.

**Gaps:**
- No retry logic for any external API call. A single transient failure causes the request to fail.
- No circuit breaker pattern. If Binance is down, every request still attempts the call (with timeout).
- ccxt live trading has a 30s timeout but no retry, which is appropriate for order execution (retry could cause duplicate orders).

---

### Performance & Scalability

#### Blocking I/O
- **All file reads/writes use `readFileSync`/`writeFileSync`** (synchronous). This blocks the Node.js event loop during file I/O. For a low-traffic single-user platform this is tolerable, but it will not scale. Use `fs.promises.readFile`/`writeFile` for async I/O.

#### Concurrent Access
- File-based storage with no locking (Critical #4). Two concurrent autoscans or trades could corrupt state.

#### Memory Usage
- Multiple in-memory `Map` caches across route files. Each Vercel function invocation gets its own memory space, so caches are cold on most requests (defeating the purpose). On a persistent server (Railway, self-hosted), caches work but accumulate without bounds.

#### Bottlenecks
1. **Autoscan:** Fetches regime + klines + live price for each asset sequentially per asset, but assets are scanned in parallel via `Promise.all()`. A scan of 10 assets makes ~30 external API calls. Each has a 5-10s timeout. Worst case: 10s for all parallel fetches.
2. **Execute:** Regime detection + kline fetch + trade execution runs sequentially for the confirmation step, then execution. Typical latency: 3-8 seconds for paper, 5-15 seconds for live.
3. **Backtest:** Fetches all klines from Binance, then runs the backtest computation in-process. No streaming or pagination. Large date ranges may be slow but are bounded by Binance's 1000-candle limit per request.

---

### API Response Consistency

#### Positive Patterns
- Most endpoints return `{ success: boolean, ... }` for POST responses.
- Error responses generally include `{ error: string }` or `{ success: false, message: string }`.
- Timestamps are consistently ISO-8601 strings.

#### Inconsistencies Found
1. **Error field naming:** Some endpoints use `{ error: "..." }` (activity, broker-status, system-health), others use `{ success: false, message: "..." }` (execute, autoscan, controls, brokers). Pick one pattern.
2. **GET /api/trading/broker-status** returns a bare array `[{...}]`, while **GET /api/trading/brokers** returns `{ brokers: [...] }`. The bare array is harder to extend.
3. **POST /api/trading/execute** returns HTTP 422 for regime-blocked trades -- this is correct (Unprocessable Entity) and well-documented.
4. **POST /api/trading/execute** returns HTTP 502 for live trade failures -- appropriate (Bad Gateway from upstream exchange).

---

### Launch Readiness: CONDITIONAL

**The platform is NOT ready for public launch as-is.** The following must be resolved:

#### MUST FIX (Blockers):
1. Remove the hardcoded JWT secret fallback (Critical #1) -- 10 minutes
2. Fix autoscan internal fetch auth bypass (Critical #2) -- 1-2 hours
3. Encrypt broker credentials at rest (Critical #3) -- 2-4 hours
4. Address file race conditions (Critical #4) -- 4-8 hours (migrate to Redis/DB) or 1-2 hours (add file locking)
5. Disable `ignoreBuildErrors` and fix any surfaced errors (Critical #5) -- 1-4 hours

#### SHOULD FIX (High Priority):
1. Persist open positions server-side (Warning #5)
2. Fix kill switch fallback to actually create the file (Warning #4)
3. Remove hardcoded Railway URL (Warning #1)
4. Add request body size limits (Warning #8)

#### NICE TO HAVE (Post-Launch):
1. Extract duplicated code into shared modules (Warning #2)
2. Add bounded caches with LRU eviction (Warning #3)
3. Migrate from `/tmp` file storage to a proper database
4. Add retry logic for external API calls
5. Replace synchronous file I/O with async
6. Add proper ccxt TypeScript types (Warning #9)

**Estimated effort to reach launch-ready: 2-3 days of focused engineering work.**
