# Stale Files Audit Report

**Date:** 2026-04-02
**Scope:** `/aifred-trading/` full codebase

---

## 1. GitHub Workflows Audit

### `.github/workflows/autotrade.yml` -- REVIEW

- **What:** Calls `POST /api/trading/autoscan` on the Vercel app every 30 minutes via cron. Lightweight -- no checkout, just curl.
- **Issue:** This is the **old/v1 workflow**. It calls the Vercel API route directly and has no Python execution. The newer `trading-autopilot.yml` does the same job but runs the full Python pipeline with proper artifact caching.
- **Both have cron schedules active**, which means duplicate scans are running (one every 30min, one every 12hr).
- **Verdict:** This is likely the "old autoscan" the user flagged. **REMOVE** if `trading-autopilot.yml` is the canonical workflow.

### `.github/workflows/trading-autopilot.yml` -- REVIEW

- **What:** Full pipeline: checkout -> Python install -> trading scan -> optimizer (on-demand) -> report -> Vercel deploy. Runs every 12 hours.
- **Issue:** References `python scripts/export_trading_data.py` but **no `scripts/` directory exists**. The file is at `python/export_trading_data.py`. This workflow would fail on every run.
- **Also references `requirements.txt` at repo root** (there is none -- it's at `python/requirements.txt`).
- **Verdict:** Broken as-is. Either **FIX** paths or **REMOVE** if not in use.

---

## 2. Dead Code Detection

### Orphaned Components (exported but never imported by any page/component)

| File | Status | Reason |
|------|--------|--------|
| `components/LivePositionsPanel.tsx` | **REMOVE** | Only self-references its own export. Not imported anywhere. |
| `components/TradeConfirmationDialog.tsx` | **REMOVE** | Only self-references its own export. Not imported anywhere. |
| `components/TradeFeed.tsx` | **REMOVE** | Only self-references its own export. Not imported anywhere. |
| `components/AccountSummaryBar.tsx` | **REVIEW** | Only imported in test file `tests/components/AccountSummaryBar.test.tsx`. Not used in any page. May be planned for future use. |

### Unused API Routes (no frontend callers)

| Route | Status | Reason |
|-------|--------|--------|
| `app/api/trading/equity-history/route.ts` | **REVIEW** | Zero frontend references. May be called by external tools or the GitHub workflow. |
| `app/api/trading/positions/route.ts` | **REVIEW** | Zero frontend references. Possibly intended for future use or external callers. |
| `app/api/trading/prices/route.ts` | **REVIEW** | Zero frontend references. Overlaps with `live-prices` route. |

### Empty Directory

| Path | Status | Reason |
|------|--------|--------|
| `python/src/models/` | **REMOVE** | Empty directory. Not imported by anything. |

### TODO/FIXME/DEPRECATED Comments

| File | Comment | Status |
|------|---------|--------|
| `middleware.ts:6` | `TODO: In-memory rate limiting is ineffective on Vercel serverless` | **REVIEW** -- Known limitation, not stale code but needs architectural fix. |
| `python/.claude/skills/use-railway/scripts/analyze-postgres.py:1003` | `DEPRECATED: Use get_all_metrics_from_api() instead` | **KEEP** -- Internal skill tooling deprecation notice. |

---

## 3. Draft/Old Files

### Investor/Presentation Files in Git

| File | Status | Reason |
|------|--------|--------|
| `INVESTOR_SUMMARY.md` | **REVIEW** | Marketing doc in repo root. Should this be in `.qa-reports/` or a separate docs repo? |
| `.qa-reports/BOARD-PRESENTATION.md` (v1) | **REMOVE** | Superseded by v2 and v3. |
| `.qa-reports/BOARD-PRESENTATION-v2.md` | **REMOVE** | Superseded by v3. |
| `.qa-reports/QA-FINAL-REPORT.md` (v1) | **REMOVE** | Superseded by v2 and v3. |
| `.qa-reports/QA-FINAL-REPORT.md.zip` | **REMOVE** | Zip of the v1 report. Binary file in git. |
| `.qa-reports/QA-FINAL-REPORT-v2.md` | **REVIEW** | Superseded by v3 but may have unique content. |

### Data Seeding Script

| File | Status | Reason |
|------|--------|--------|
| `python/seed_demo_data.py` | **REVIEW** | Seeds fake trading data into SQLite. Referenced by `trading-autopilot.yml` as a fallback. Not needed for production Railway deployment but useful for dev/CI. Should not be deployed. |

### Validation/Testing Scripts

| File | Status | Reason |
|------|--------|--------|
| `python/validate_system.py` | **KEEP** | Health validation tool. Useful for debugging. |
| `python/paper_trading.py` | **KEEP** | Standalone paper trading validator. Used for local testing. |

### Log File Committed to Git

| File | Status | Reason |
|------|--------|--------|
| `python/paper_trading.log` | **REMOVE** | 583KB log file committed to git. Should be in `.gitignore`. |

### Seeded Demo Data in Git

| File | Status | Reason |
|------|--------|--------|
| `data/activity-log.json` | **REVIEW** | Seeded demo data (IDs start with `seed_`). Git-tracked. The frontend reads this. In production, should come from the Python engine, not a static JSON file. |
| `data/trading-data.json` | **REVIEW** | 67KB of demo data with inflated metrics (78% WR, $54K P&L). Git-tracked. Same concern as above. |

---

## 4. Config Conflicts

### Dual Dockerfiles

| File | Purpose | Status |
|------|---------|--------|
| `python/Dockerfile` | Full build with TA-Lib C compilation. Multi-stage. Uses `requirements.txt`. | **REVIEW** | 
| `python/Dockerfile.railway` | Railway-specific. No TA-Lib. Uses `requirements-railway.txt`. Python 3.12. | **KEEP** |

**Conflict:** `Dockerfile` uses Python 3.11 + TA-Lib + full `requirements.txt`. `Dockerfile.railway` uses Python 3.12 + no TA-Lib + slimmed `requirements-railway.txt`. The full Dockerfile is for docker-compose local dev. Both are needed but the full `Dockerfile` may be unused if everyone deploys to Railway.

### Dual Requirements Files

| File | Packages | Status |
|------|----------|--------|
| `python/requirements.txt` | 40+ packages including TA-Lib, lightgbm, catboost, mlflow, streamlit, plotly, neuralforecast, riskfolio-lib, spacy, nltk, newspaper3k, psycopg2, redis, pyarrow, quantstats, empyrical, oandapyV20 | **REVIEW** |
| `python/requirements-railway.txt` | ~20 packages. Lean subset for Railway. | **KEEP** |

**Issues with `requirements.txt`:**
- Includes `streamlit` -- only used in `monitoring/dashboard.py` which is a standalone Streamlit app, not part of the main trading engine.
- Includes `TA-Lib` -- requires C library compilation, not available on Railway.
- Includes `mlflow`, `quantstats`, `riskfolio-lib`, `neuralforecast` -- heavy ML packages not imported in the core pipeline.
- Includes `psycopg2-binary`, `redis` -- database connectors not used (SQLite is the DB).
- Includes `oandapyV20` -- forex broker SDK, not referenced in production code.
- Includes `newspaper3k`, `spacy`, `nltk` -- heavy NLP packages; only `feedparser` is in the Railway requirements.
- **Verdict:** `requirements.txt` is a wishlist from early development. It should be trimmed to match actual imports.

### `.env.docker` vs `.env.example`

| Variable | `.env.docker` | `.env.example` | Status |
|----------|--------------|----------------|--------|
| `BINANCE_API_SECRET` | `BINANCE_API_SECRET` | `BINANCE_SECRET` | **INCONSISTENT** -- different key names |
| `ALPACA_API_SECRET` | `ALPACA_API_SECRET` | `ALPACA_SECRET` | **INCONSISTENT** -- different key names |
| `OANDA_*` | absent | present | `.env.example` has Oanda keys; `.env.docker` does not |
| `NEWSAPI_KEY` | absent | present | `.env.example` has it; `.env.docker` does not |
| `REDDIT_*` | absent | present | `.env.example` has Reddit creds; `.env.docker` does not |
| `HYPERLIQUID_*` | `HYPERLIQUID_ADDRESS`, `HYPERLIQUID_PRIVATE_KEY` | `HYPERLIQUID_WALLET_ADDRESS`, `NEXT_PUBLIC_HYPERLIQUID_ADDRESS` | **INCONSISTENT** -- different key names |
| `MLFLOW_TRACKING_URI` | absent | present | Old dev dependency |
| `NEXT_PUBLIC_TRADING_MODE` | absent | present | Frontend-specific, not needed for Docker |

**Verdict:** These files have diverged. `.env.docker` is for the Python engine (Docker Compose), `.env.example` is for the full-stack app. They should be reconciled or clearly labeled.

---

## 5. Build Artifacts in Git

### `.gitignore` Gaps

| Item | In `.gitignore`? | Actually in repo? | Status |
|------|------------------|--------------------|--------|
| `node_modules/` | Yes | Not tracked | OK |
| `.next/` | Yes | Not tracked | OK |
| `.vercel/` | Yes | Not tracked | OK |
| `__pycache__/` | Yes (`__pycache__/`) | **Exists on disk** in `python/`, `python/src/`, and 14 subdirs | The gitignore works but `__pycache__` dirs exist locally. Not in git. OK. |
| `*.pyc` | Yes | Not tracked | OK |
| `python/paper_trading.log` | **No** | **TRACKED** (583KB) | **FIX** -- add `*.log` or `python/paper_trading.log` to `.gitignore` |
| `data/*.json` | **No** | **TRACKED** (2 files, 79KB total) | **REVIEW** -- these are seeded demo data; see Section 3 |
| `python/data/*.db` | Yes (`/python/data/`) | Not tracked | OK |
| `.DS_Store` | Yes | Not tracked at top level | OK, but `.qa-reports/.DS_Store` exists on disk |
| `*.zip` | **No** | **TRACKED** (`QA-FINAL-REPORT.md.zip`, 2 Railway skill zips) | **FIX** -- binary zip files should not be in git |

### Missing `.gitignore` entries

```
*.log
*.zip
python/paper_trading.log
.qa-reports/.DS_Store
```

---

## 6. Unused Dependencies

### npm (`package.json`)

| Package | Import Count | Status |
|---------|-------------|--------|
| `@walletconnect/modal` | **0** | **REMOVE** -- zero imports anywhere. WalletConnect is handled via wagmi. |
| All others | 1+ | KEEP |

### Python (`requirements.txt` vs `requirements-railway.txt`)

**In `requirements.txt` only (not in Railway, not imported in core pipeline):**

| Package | Status | Reason |
|---------|--------|--------|
| `TA-Lib>=0.4.28` | **REMOVE from requirements.txt** | Requires C compilation. `pandas-ta` is the pure-Python replacement used in Railway. |
| `lightgbm>=4.0.0` | **REVIEW** | Not in Railway requirements. May not be used in production. |
| `catboost>=1.2.0` | **REVIEW** | Not in Railway requirements. May not be used in production. |
| `pytorch-forecasting>=1.0.0` | **REVIEW** | Not in Railway. May not be actively used. |
| `neuralforecast>=1.7.0` | **REVIEW** | Not in Railway. May not be actively used. |
| `streamlit>=1.28.0` | **REVIEW** | Only used in `monitoring/dashboard.py` standalone app. |
| `plotly>=5.18.0` | **REVIEW** | Only used with Streamlit dashboard. |
| `mlflow>=2.9.0` | **REVIEW** | ML tracking -- not used in production pipeline. |
| `quantstats>=0.0.62` | **REVIEW** | Performance analytics -- may be used in evaluation scripts only. |
| `riskfolio-lib>=6.0.0` | **REVIEW** | Portfolio optimization -- not imported in core code. |
| `empyrical>=0.5.5` | **REVIEW** | Risk analysis -- may overlap with custom implementations. |
| `spacy>=3.7.0` | **REVIEW** | Heavy NLP. Railway uses lightweight approach. |
| `nltk>=3.8.0` | **REVIEW** | Heavy NLP. Railway uses lightweight approach. |
| `newspaper3k>=0.2.8` | **REVIEW** | Article extraction. Not in Railway. |
| `finbert-embedding>=0.1.4` | **REVIEW** | FinBERT. Railway uses `transformers` directly. |
| `psycopg2-binary>=2.9.9` | **REVIEW** | PostgreSQL connector. SQLite is the actual DB. |
| `redis>=5.0.0` | **REVIEW** | Redis connector. Not used in production. |
| `pyarrow>=14.0.0` | **REVIEW** | Data format. Not in Railway. |
| `oandapyV20>=0.7.2` | **REVIEW** | Oanda forex broker SDK. Not used. |
| `alpaca-trade-api>=3.0.0` | **REVIEW** | Alpaca SDK. Railway uses `ccxt` for all exchanges. |
| `yfinance>=0.2.30` | **REVIEW** | Yahoo Finance data. Not in Railway requirements. |
| `optuna>=3.4.0` | **REVIEW** | Hyperparameter optimization. Not in Railway. |
| `mcp>=1.0.0` | **REVIEW** | Model Context Protocol. Not in Railway. |

---

## 7. Additional Findings

### Skill Archives in Git

| File | Status |
|------|--------|
| `python/.claude/skills/railway/claude_railway_skill_v2.4.zip` | **REMOVE** -- binary zip in git |
| `python/.claude/skills/railway/skill-claude-railway-3.7.zip` | **REMOVE** -- binary zip in git |

### `python/src/monitoring/dashboard.py` -- Streamlit Standalone

- **REVIEW** -- This is a standalone Streamlit dashboard (`import streamlit as st`). It requires `streamlit` and `plotly` which are not in the Railway requirements. This is a development/local tool, not part of the production system. Consider moving to a `tools/` or `dev/` directory.

### `python/export_trading_data.py` -- Misplaced

- **REVIEW** -- This is at `python/export_trading_data.py` but `trading-autopilot.yml` references `python scripts/export_trading_data.py` (wrong path). If this workflow is fixed, the file should either move to `python/scripts/` or the workflow path should be corrected.

### Superseded Reports Accumulation

The `.qa-reports/` directory has 26 files (200KB+). Multiple versions of the same reports (v1, v2, v3) are all tracked. Consider keeping only the latest version in git and archiving older ones.

---

## Summary

### REMOVE (safe to delete)

1. `.github/workflows/autotrade.yml` -- old workflow, superseded by `trading-autopilot.yml`
2. `components/LivePositionsPanel.tsx` -- orphaned, never imported
3. `components/TradeConfirmationDialog.tsx` -- orphaned, never imported
4. `components/TradeFeed.tsx` -- orphaned, never imported
5. `python/src/models/` -- empty directory
6. `python/paper_trading.log` -- log file committed to git (583KB)
7. `.qa-reports/BOARD-PRESENTATION.md` (v1) -- superseded by v3
8. `.qa-reports/BOARD-PRESENTATION-v2.md` -- superseded by v3
9. `.qa-reports/QA-FINAL-REPORT.md` (v1) -- superseded by v3
10. `.qa-reports/QA-FINAL-REPORT.md.zip` -- binary zip of v1 report
11. `python/.claude/skills/railway/claude_railway_skill_v2.4.zip` -- binary archive
12. `python/.claude/skills/railway/skill-claude-railway-3.7.zip` -- binary archive
13. `@walletconnect/modal` from `package.json` -- zero imports

### REVIEW (needs human decision)

1. `.github/workflows/trading-autopilot.yml` -- broken paths, needs fixing or removal
2. `components/AccountSummaryBar.tsx` -- only used in tests, not in any page
3. `app/api/trading/equity-history/route.ts` -- no frontend callers
4. `app/api/trading/positions/route.ts` -- no frontend callers
5. `app/api/trading/prices/route.ts` -- no frontend callers, overlaps with `live-prices`
6. `python/seed_demo_data.py` -- dev tool, should not be in production image
7. `data/activity-log.json` and `data/trading-data.json` -- seeded demo data in git
8. `python/requirements.txt` -- bloated with ~20 unused packages
9. `.env.docker` vs `.env.example` -- inconsistent variable names
10. `python/Dockerfile` -- may be unused if Railway is the only deploy target
11. `INVESTOR_SUMMARY.md` -- marketing doc in repo root
12. `.qa-reports/QA-FINAL-REPORT-v2.md` -- may have unique content
13. `python/src/monitoring/dashboard.py` -- standalone Streamlit app, not production code

### KEEP (belongs here)

1. `.github/workflows/trading-autopilot.yml` (after fixing paths)
2. `python/Dockerfile.railway` -- active Railway deployment
3. `python/requirements-railway.txt` -- lean production deps
4. `python/validate_system.py` -- useful health check tool
5. `python/paper_trading.py` -- standalone validation tool
6. `python/export_trading_data.py` -- needed for data pipeline
7. `docker-compose.yml` -- local dev orchestration
8. All components, hooks, stores, lib files not flagged above
9. All Python `src/` modules not flagged above
10. `.qa-reports/BOARD-PRESENTATION-v3.md` -- latest version
11. `.qa-reports/QA-FINAL-REPORT-v3.md` -- latest version

### .gitignore Fixes Needed

Add these entries:
```
*.log
*.zip
docs/superpowers/.DS_Store
.qa-reports/.DS_Store
```
