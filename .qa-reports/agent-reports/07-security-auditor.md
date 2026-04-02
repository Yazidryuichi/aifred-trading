# Security Audit Report -- Agent 07

**Auditor:** Security Auditor (Agent 07)  
**Date:** 2026-04-01  
**Scope:** Full codebase security review of AIFred Trading Platform  
**Methodology:** Static analysis of source code, configuration files, and dependencies

---

## Executive Summary

The platform has addressed several P0 issues from prior audits (JWT hardcoding, `ignoreBuildErrors`, auth bypass on autoscan). However, **5 CRITICAL** and **4 HIGH** severity issues remain, primarily around credential storage, exposed tokens, and a hardcoded wallet address that queries a real Hyperliquid account.

---

## CRITICAL Findings

### C1. Vercel OIDC Token Checked Into Repository

**Severity:** CRITICAL  
**File:** `.vercel/.env.development.local:2`  
**Status:** ACTIVE

The file `.vercel/.env.development.local` contains a full Vercel OIDC JWT token (`VERCEL_OIDC_TOKEN`). Although `.vercel` is listed in `.gitignore`, this file exists on disk and the `.gitignore` has a duplicate entry (`.vercel/` on line 3 and `.vercel` on line 22). If `.gitignore` was ever briefly misconfigured or the file was force-added, this token would be in git history.

The token decodes to reveal:
- Team: `teamdiaalloai-2167s-projects`
- Project: `aifred-trading` (ID: `prj_CsrBuw3MmCoydgb7Ne0tMlrO4ZhA`)
- User ID: `hBn0mYG5SBW7jfmmYq5DhuvB`
- Environment: `development`

**Remediation:**
1. Verify this file is NOT in git history (`git log --all --full-history -- .vercel/.env.development.local`)
2. If found in history, rotate the Vercel token immediately and use `git filter-repo` to purge it
3. Add `.vercel/` to a global `.gitignore` as defense-in-depth

---

### C2. Broker Credentials Stored as Plaintext JSON on Disk

**Severity:** CRITICAL  
**Files:**
- `lib/execute-trade.ts:46` -- reads from `/tmp/aifred-data/.broker-secrets.json`
- `app/api/trading/brokers/route.ts:200` -- writes to same path
- `app/api/trading/brokers/route.ts:281-309` -- migration logic from plaintext to encrypted

**Description:** While the brokers route now uses AES-256-GCM encryption (lines 212-257), the **execute-trade module reads secrets without decryption** (line 150-157):

```typescript
function readBrokerSecrets(): Record<string, Record<string, string>> {
  if (!existsSync(SECRETS_PATH)) return {};
  try {
    return JSON.parse(readFileSync(SECRETS_PATH, "utf-8"));
  } catch {
    return {};
  }
}
```

This function at `lib/execute-trade.ts:150-157` performs a raw `JSON.parse` without calling `decryptCredentials()`. This means:
- If the file is encrypted (as written by `brokers/route.ts`), live trades will fail silently (parse returns garbage)
- If the file is plaintext (pre-migration), credentials are readable by any process with `/tmp` access

On Vercel, `/tmp` is shared across all function invocations within the same instance. On Railway/Docker, it persists across container restarts.

**Remediation:**
1. Import and use `decryptCredentials()` in `execute-trade.ts` when reading broker secrets
2. Consider moving credential storage to a proper secrets manager (Vercel env vars, Railway variables, or a KMS)
3. Never store exchange API keys on the filesystem

---

### C3. Client-Side Code Sends Credentials in Request Body

**Severity:** CRITICAL  
**Files:**
- `app/api/trading/execute/route.ts:27` -- accepts `body.credentials`
- `app/api/trading/autoscan/route.ts:475` -- accepts `credentials` from POST body
- `app/api/trading/brokers/test/route.ts:30` -- accepts `credentials` from POST body

**Description:** API keys and secrets are transmitted from the client to the server in the JSON request body. This means:
- Credentials pass through JavaScript memory in the browser
- They appear in browser DevTools Network tab
- They may be logged by any request interceptor, proxy, or monitoring tool
- They are visible in Vercel function logs if request bodies are logged

The execute endpoint (`execute/route.ts:27`) passes `body.credentials` directly to the trade execution function, and the autoscan endpoint (`autoscan/route.ts:475`) does the same for auto-execution mode.

**Remediation:**
1. Never send raw credentials from client to server. Store them server-side only (via the broker connection flow)
2. Reference stored credentials by broker ID, not by passing secrets in each request
3. The `credentials` field should be removed from `ExecuteTradeParams`

---

### C4. Hardcoded Hyperliquid Wallet Address Exposes Real Account

**Severity:** CRITICAL  
**Files:**
- `app/api/trading/hyperliquid/route.ts:8` -- hardcoded fallback `0xbec07623...`
- `app/api/trading/positions/route.ts:7` -- same hardcoded address
- `hooks/useHyperliquidData.ts:58,149` -- same address in client-side code

**Description:** A real Hyperliquid wallet address (`0xbec07623d9c8209E7F80dC7350b3aA0ECBdCb510`) is hardcoded as a fallback in 4 locations. The Hyperliquid API is public and read-only for account state, but this:
- Exposes the account holder's positions, PnL, and balances to anyone who views the source
- Could be used by adversaries to front-run or shadow-trade the account
- The address appears in client-side code (`hooks/useHyperliquidData.ts`), making it trivially discoverable

**Remediation:**
1. Remove all hardcoded addresses from source code
2. Require `HYPERLIQUID_ADDRESS` as a mandatory env var (fail if not set, similar to `NEXTAUTH_SECRET`)
3. Never expose wallet addresses in client-side bundles -- proxy all Hyperliquid requests through the server API

---

### C5. Encryption Key Derived from NEXTAUTH_SECRET

**Severity:** CRITICAL  
**File:** `app/api/trading/brokers/route.ts:212-219`

**Description:** The AES-256-GCM encryption key for broker credentials is derived by SHA-256 hashing `NEXTAUTH_SECRET`:

```typescript
function getEncryptionKey(): Buffer {
  const secret = process.env.NEXTAUTH_SECRET;
  return createHash("sha256").update(secret).digest();
}
```

This means:
- A single secret (`NEXTAUTH_SECRET`) protects both authentication tokens AND stored exchange credentials
- If `NEXTAUTH_SECRET` is compromised, all encrypted broker credentials are also compromised
- No key derivation function (KDF) with salt/iterations is used -- raw SHA-256 is not a proper KDF

**Remediation:**
1. Use a separate, dedicated encryption key for credential storage (`CREDENTIAL_ENCRYPTION_KEY`)
2. Use a proper KDF like PBKDF2, scrypt, or argon2 instead of raw SHA-256
3. Implement key rotation capability

---

## HIGH Findings

### H1. Rate Limiting is In-Memory and Per-Process Only

**Severity:** HIGH  
**File:** `middleware.ts:6-19`

**Description:** Rate limiting uses an in-memory `Map`:
```typescript
const rateLimits = new Map<string, { count: number; resetAt: number }>();
```

On Vercel, each serverless function invocation may run in a different process/container. The rate limiter resets whenever:
- A new cold start occurs
- The function scales to a new instance
- The process is recycled (every few minutes on Vercel)

This renders trade execution rate limiting (1 trade per 10 seconds) effectively non-functional on serverless deployments.

**Remediation:**
1. Use Redis or Upstash for distributed rate limiting
2. Alternatively, use Vercel's built-in rate limiting or a WAF
3. At minimum, document that the current rate limiter is only effective for single-process deployments (Railway/Docker)

---

### H2. File Lock Implementation Has TOCTOU Race Window

**Severity:** HIGH  
**File:** `lib/file-lock.ts:92-101`

**Description:** The lock acquisition has a documented TOCTOU (Time-of-Check-Time-of-Use) window:
```typescript
// line 96: check existence, then write -- not atomic
if (!existsSync(lock)) {
  writeFileSync(lock, lockId, { flag: "wx" });
```

The code uses `wx` flag (O_CREAT|O_EXCL) which is correct, but the preceding `existsSync` check is redundant and misleading. More critically, the `releaseLock` function (line 128-135) **does not verify lock ownership** -- it deletes the lock file regardless of which process owns it:

```typescript
function releaseLock(filePath: string, _lockId: string): void {
  // _lockId is unused!
  try { unlinkSync(lock); } catch { }
}
```

This means Process A could release Process B's lock, leading to data corruption in concurrent scenarios (e.g., two autoscan requests hitting different Vercel instances writing to the same `/tmp` file).

**Remediation:**
1. In `releaseLock`, read the lock file content and only delete if it matches the caller's `lockId`
2. Remove the redundant `existsSync` check before the `wx` write
3. On serverless (Vercel), file locking is fundamentally unreliable across instances -- consider using database-level locking or atomic operations instead

---

### H3. No Input Sanitization on Trading Symbols

**Severity:** HIGH  
**Files:**
- `app/api/trading/execute/route.ts:17-28` -- passes `body.symbol` directly
- `app/api/trading/autoscan/route.ts:469` -- passes `assets` array from body

**Description:** The `symbol` field from user input is passed through to external API calls (Binance, Hyperliquid) without validation against an allowlist. While the `CRYPTO_BINANCE` map provides implicit validation for known symbols, the `normalizeSymbol` function (`lib/execute-trade.ts:135-143`) attempts to parse arbitrary strings. Combined with `ccxt` exchange instantiation, a crafted `brokerId` + `symbol` could potentially trigger unexpected behavior.

Additionally, `assets` array in the autoscan POST body has no length limit or content validation -- an attacker could send thousands of symbols to cause resource exhaustion.

**Remediation:**
1. Validate `symbol` against the `CRYPTO_BINANCE` allowlist before processing
2. Limit the `assets` array to a maximum length (e.g., 20)
3. Validate `brokerId` against `EXCHANGE_MAP` keys early in the request handler

---

### H4. Error Messages Leak Internal Details

**Severity:** HIGH  
**Files:**
- `lib/execute-trade.ts:472` -- exposes diagnostics in error messages
- `app/api/trading/brokers/test/route.ts:137` -- exposes raw error details

**Description:** Error responses include internal diagnostics and raw error messages:
```typescript
throw new Error(`${rawMsg}\n\n[Diagnostics] ${diagnostics.join(" -> ")}`);
```

And:
```typescript
{ details: err?.message?.slice(0, 200) }
```

These could reveal internal architecture, exchange connection details, API endpoints, and potentially partial credentials to clients.

**Remediation:**
1. Log detailed errors server-side only (`console.error`)
2. Return generic error messages to clients
3. Use error codes that map to user-friendly messages on the frontend

---

## MEDIUM Findings

### M1. No CSRF Protection Beyond NextAuth Default

**Severity:** MEDIUM  
**File:** `middleware.ts`

**Description:** CSRF protection relies entirely on NextAuth's built-in CSRF token for auth routes. However, all `/api/trading/*` endpoints use JWT bearer auth via middleware, which is not inherently CSRF-resistant. If a session cookie is used (NextAuth default), state-changing POST requests to trading endpoints could be vulnerable to CSRF attacks from malicious sites.

**Remediation:**
1. Verify NextAuth is using httpOnly, sameSite=strict cookies
2. Add explicit CSRF token validation for all state-changing endpoints
3. Consider requiring a custom header (e.g., `X-Requested-With`) that cannot be sent by simple cross-origin forms

---

### M2. MarketChart Component Uses innerHTML

**Severity:** MEDIUM  
**File:** `components/trading/MarketChart.tsx:25,32,54`

**Description:** The TradingView widget embedding uses `innerHTML` to clear the container and `script.innerHTML` to set configuration. While the configuration is serialized via `JSON.stringify` from controlled props, the `container.innerHTML = ""` pattern is a code smell. If the `symbol` prop were ever sourced from user input without sanitization, this could become an XSS vector.

**Remediation:**
1. Use `removeChild` or React refs instead of `innerHTML = ""`
2. Validate the `symbol` prop against an allowlist before embedding

---

### M3. Synchronous Busy-Wait in Lock Acquisition

**Severity:** MEDIUM  
**File:** `lib/file-lock.ts:117-120`

**Description:** The lock retry uses a synchronous busy-wait spin loop:
```typescript
const waitUntil = Date.now() + LOCK_RETRY_INTERVAL_MS;
while (Date.now() < waitUntil) { /* spin */ }
```

This blocks the Node.js event loop for up to 25ms per retry, potentially up to 12 seconds total. On serverless, this wastes compute time and can cause timeouts for other requests queued on the same instance.

**Remediation:**
1. Use `setTimeout` or `setImmediate` for async waiting
2. Make `acquireLock` async and use `await new Promise(r => setTimeout(r, 25))`

---

### M4. Python Dependencies Use Minimum Version Pins Only

**Severity:** MEDIUM  
**File:** `python/requirements.txt`

**Description:** All 40+ Python dependencies use `>=` minimum version pins (e.g., `torch>=2.0.0`, `transformers>=4.35.0`). This means:
- Any `pip install` will pull the latest version, which may introduce breaking changes or vulnerabilities
- No lockfile exists to ensure reproducible builds
- Several packages have known CVE histories (e.g., `transformers`, `torch`, `requests`, `aiohttp`)

**Remediation:**
1. Pin exact versions or use `~=` compatible release pins
2. Generate and commit a `requirements.lock` or use `pip-compile`
3. Run `pip-audit` or `safety check` as part of CI

---

## LOW Findings

### L1. `.gitignore` Has Duplicate/Conflicting Entries for `.vercel`

**Severity:** LOW  
**File:** `.gitignore:3,22`

Lines 3 and 22 both exclude `.vercel` (one as `.vercel/`, one as `.vercel`). While functionally equivalent, this suggests the gitignore was modified without checking for existing entries.

---

### L2. Hardcoded Default Fallback Prices

**Severity:** LOW  
**File:** `lib/execute-trade.ts:33-44`

`MOCK_PRICES` contains hardcoded asset prices used as fallbacks. These will become increasingly inaccurate over time and could lead to incorrect position sizing in paper trading mode.

---

### L3. Activity Log Has No Authentication Check for Reads

**Severity:** LOW  
**File:** `app/api/trading/activity/route.ts`

While the middleware protects `/api/trading/*` routes, the activity log may contain sensitive details (trade amounts, broker names, signals). Ensure the middleware matcher correctly captures all sub-routes.

**Status:** VERIFIED OK -- the middleware matcher `/api/trading/:path*` does cover this route.

---

### L4. JWT Session Max Age is 24 Hours

**Severity:** LOW  
**File:** `lib/auth.ts:41`

A 24-hour session lifetime is long for a financial application. If a session is compromised, the attacker has a full day of access.

**Remediation:** Consider reducing to 4-8 hours with refresh token rotation.

---

## P0 Resolution Verification

| P0 Issue | Status | Evidence |
|----------|--------|----------|
| Hardcoded JWT secret | **RESOLVED** | `lib/auth.ts:5-9` throws if `NEXTAUTH_SECRET` is not set. `middleware.ts:35-39` fails closed. No hardcoded secrets found. |
| Plaintext credentials | **PARTIALLY RESOLVED** | `brokers/route.ts` now encrypts. But `execute-trade.ts` reads without decryption (see C2). |
| `ignoreBuildErrors: true` | **RESOLVED** | `next.config.ts:5` sets `ignoreBuildErrors: false`. |
| Auth bypass on autoscan | **RESOLVED** | `middleware.ts:43-51` requires JWT token for all `/api/trading/*` routes. Autoscan calls `executeTrade()` directly instead of HTTP round-trip. |
| File race conditions | **PARTIALLY RESOLVED** | `lib/file-lock.ts` implements locking, but `releaseLock` does not verify ownership (see H2). |

---

## Summary Table

| Severity | Count | Key Areas |
|----------|-------|-----------|
| CRITICAL | 5 | Credential storage, exposed tokens, hardcoded address, key derivation |
| HIGH | 4 | Rate limiting, file locks, input validation, error leakage |
| MEDIUM | 4 | CSRF, innerHTML, busy-wait, dependency pinning |
| LOW | 4 | Gitignore, mock prices, session lifetime |

---

## Top 3 Recommended Actions

1. **Immediately audit git history** for the Vercel OIDC token and rotate if found (C1)
2. **Fix credential decrypt mismatch** in `execute-trade.ts` to use the encrypted store (C2)
3. **Remove hardcoded wallet address** from all source files and require env var (C4)
