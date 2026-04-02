# Git Forensics Report -- AIFred Trading Platform

**Date:** 2026-04-02
**Repository:** `aifred-trading` (98 commits, single branch)
**Scope:** Full git history analysis, secret detection, large file audit, orphaned code scan

---

## CRITICAL FINDINGS

### CRITICAL-1: GitHub OAuth Token Hardcoded in Remote URL

```
origin  https://Ladykiller101:[REDACTED_OAUTH_TOKEN]@github.com/Ladykiller101/aifred-trading.git
```

A `gho_` prefixed GitHub OAuth token is embedded directly in the git remote URL. This token is stored in `.git/config` and grants repository access to anyone who clones or has access to this machine.

**Severity:** CRITICAL
**Action required:**
1. Revoke this token immediately at https://github.com/settings/tokens
2. Reset the remote URL: `git remote set-url origin https://github.com/Ladykiller101/aifred-trading.git`
3. Use SSH keys or a credential helper instead of URL-embedded tokens

### CRITICAL-2: Hardcoded Wallet Address in Git History

The Hyperliquid wallet address `0xbec07623d9c8209E7F80dC7350b3aA0ECBdCb510` is committed in multiple locations:

- Environment variable defaults (`HYPERLIQUID_WALLET_ADDRESS`, `NEXT_PUBLIC_HYPERLIQUID_ADDRESS`)
- Hardcoded fallback in `hyperliquid/route.ts:8`
- Referenced in QA reports and board presentations

The `NEXT_PUBLIC_` prefix means this address is bundled into client-side JavaScript and shipped to every browser. While wallet addresses are public on-chain, this unnecessarily identifies the operator's wallet and makes the system vulnerable to targeted monitoring.

**Severity:** CRITICAL (information exposure)
**Action required:**
1. Remove hardcoded address from code; use server-side-only env var
2. Use `git filter-branch` or BFG Repo-Cleaner to scrub the address from history if desired
3. Remove the `NEXT_PUBLIC_` prefix and proxy through the API

---

## HIGH FINDINGS

### HIGH-1: Broken Git Ref -- `refs/remotes/origin/main 2`

A broken ref exists at `.git/refs/remotes/origin/main 2` (note the space in the filename). It points to commit `8a1ff0a` ("feat: make Hyperliquid the primary live data source for all UI").

This ref is an artifact of a botched fetch/push -- likely a shell quoting error or a GUI tool malfunction. It causes `fatal: bad object` errors when using `--all` flags on any git command.

**Action required:**
```bash
rm ".git/refs/remotes/origin/main 2"
```

### HIGH-2: Large Binary/Log Files Committed to Git

| Size | File | Status |
|------|------|--------|
| 1.39 MB | `python/.claude/skills/railway/skill-claude-railway-3.7.zip` | Still tracked |
| 584 KB | `python/paper_trading.log` | Still tracked |
| 517 KB | `python/.claude/skills/railway/claude_railway_skill_v2.4.zip` | Still tracked |

These are development artifacts (zip archives, log files) that bloat the repository. The `.gitignore` does not exclude `*.zip`, `*.log`, or `.claude/skills/`.

**Action required:**
1. Add to `.gitignore`: `*.zip`, `*.log`, `.claude/`
2. Remove from tracking: `git rm --cached python/paper_trading.log python/.claude/skills/railway/*.zip`
3. Consider BFG to purge from history (saves ~2.5 MB)

### HIGH-3: Two Redundant GitHub Actions Workflows Both Active

| Workflow | Schedule | Purpose |
|----------|----------|---------|
| `autotrade.yml` | Every 30 min (`0,30 * * * *`) | Calls Vercel `/api/autoscan` endpoint |
| `trading-autopilot.yml` | Every 12 hours (`0 0,12 * * *`) | Full Python pipeline: scan, execute, optimize |

`trading-autopilot.yml` appears to be the original (from commit `9e9ff90`, the very first commit on 2026-03-16). `autotrade.yml` was added later in commit `27fa672`.

Both are still active. The older `trading-autopilot.yml` references Binance, Alpaca, and Anthropic API keys via GitHub Secrets and runs a full Python environment. The newer `autotrade.yml` is lighter and calls the deployed Vercel API.

**Action required:**
1. Determine which workflow is the canonical one
2. Disable or delete the other
3. The older `trading-autopilot.yml` should be removed if no longer used -- it references an older architecture

---

## MEDIUM FINDINGS

### MEDIUM-1: Single-Branch History (No Feature Branches)

The entire 98-commit history is linear on `main`. There are no feature branches, no PRs, no code review artifacts. This means:

- No peer review ever occurred
- No rollback points exist for individual features
- All code was pushed directly to production

### MEDIUM-2: `.gitignore` Gaps

The current `.gitignore` is minimal and missing important patterns:

- `*.zip` -- skill archives are committed
- `*.log` -- `paper_trading.log` is committed
- `.claude/` -- Claude Code internal files are committed
- `*.db` -- SQLite databases (the workflow caches `trading.db`)
- `.qa-reports/` -- should likely be tracked, but review needed
- `*.png` / `*.jpg` -- screenshots in parent directory (not in this repo, but worth noting)

### MEDIUM-3: Workflow Uses GitHub Actions Cache for Trading Database

`trading-autopilot.yml` caches `data/trading.db` across runs:

```yaml
path: data/trading.db
key: trading-db-${{ github.sha }}
```

This means trading state persists in GitHub's cache infrastructure. If this workflow is abandoned, the cached state is orphaned. If both workflows run, they may have conflicting state.

---

## LOW FINDINGS

### LOW-1: Parent Directory is NOT a Git Repo (Good)

`/Users/ryuichiyazid/Desktop/AIFred Vault/` is not a git repository. No risk of nested repo issues. The parent directory contains:

- `aifred-trading/` -- this project
- `AIFred Project Vault/` -- separate project folder (Obsidian vault with `.base` files)
- `.claude/`, `.obsidian/`, `.planning/`, `.playwright-mcp/` -- tooling directories
- `aifred-dashboard-test.png`, `aifred-trading-status.png` -- screenshots
- `.mcp.json`, `skills-lock.json` -- MCP configuration

No evidence of cross-project file leakage.

### LOW-2: Only One File Ever Deleted

The entire git history shows only one deleted file:

```
delete mode 100644 python/.dockerignore
```

This suggests the codebase has only grown -- nothing has ever been cleaned up or refactored away.

---

## Project Timeline Reconstruction

| Date | Commit | Event |
|------|--------|-------|
| 2026-03-16 | `9e9ff90` | Initial commit: full standalone trading platform + `trading-autopilot.yml` |
| 2026-03-17 | `a417e1f` - `a2c6a0f` | Bug fixes: state persistence, trade execution |
| 2026-03-18 | `c686d11` - `054c2bb` | Investor-ready improvements, credential validation |
| 2026-03-19 | `27fa672` | Second workflow added: `autotrade.yml` with 30-min cron |
| 2026-03-19 - 2026-03-28 | Multiple | QA audits, P0/P1/P2 remediation sprints, NOFX dashboard overhaul |
| 2026-03-30 | Various | Hyperliquid primary data source, ML ensemble, config page |
| 2026-04-01 | `194c50a` | 14 critical issues from 12-agent audit fixed |
| 2026-04-01 | `8da5275` | Board presentation v3 (latest commit) |

The project is 17 days old with 98 commits -- all by a single author, all on main, no branches ever created.

---

## Secrets Audit Summary

| Type | Found | Severity |
|------|-------|----------|
| GitHub OAuth token in remote URL | `gho_NWzpA66...` | CRITICAL |
| Hardcoded wallet address (4+ locations) | `0xbec076...` | CRITICAL |
| Private keys in code | References only (env var pattern) | OK |
| API keys in workflows | Via `${{ secrets.* }}` (correct) | OK |
| `.env` files committed | None found | OK |
| Broker secrets in code | Stored in `/tmp/` at runtime only | OK |

---

## Recommended Actions (Priority Order)

1. **[IMMEDIATE]** Revoke the GitHub OAuth token `[REDACTED_OAUTH_TOKEN]` and reset the remote URL
2. **[IMMEDIATE]** Delete broken ref: `rm ".git/refs/remotes/origin/main 2"`
3. **[TODAY]** Remove hardcoded wallet address from code; replace with server-side env var
4. **[TODAY]** Decide which GitHub Actions workflow is canonical; disable the other
5. **[THIS WEEK]** Update `.gitignore` to exclude `*.zip`, `*.log`, `.claude/`
6. **[THIS WEEK]** Remove large tracked files: `git rm --cached` the zip/log files
7. **[THIS WEEK]** Consider running BFG Repo-Cleaner to purge the OAuth token and large files from history
