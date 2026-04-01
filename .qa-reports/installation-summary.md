# Installation Summary — 2026-04-01

## Successfully Installed

### 1. TradingView Lightweight Charts (npm)
- **Package:** `lightweight-charts`
- **Version:** ^5.1.0
- **Status:** Installed and added to package.json
- **Notes:** Peer dependency warnings for `use-sync-external-store` with React 19 (non-blocking, resolved via npm override). 1 pre-existing moderate severity vulnerability (not introduced by this install).

### 2. Python Dependencies (added to requirements.txt)
- **`quantstats>=0.0.62`** — Performance analytics and tear sheets
- **`riskfolio-lib>=6.0.0`** — Portfolio optimization
- **`neuralforecast>=1.7.0`** — Advanced time series forecasting (NBEATS, NHITS, PatchTST)
- **Status:** Added to `/python/requirements.txt` under new sections (Performance Analytics, Portfolio Optimization, Advanced Time Series Forecasting)
- **Note:** Not pip-installed into a live environment (no virtualenv detected in project). These will be installed when `pip install -r requirements.txt` is next run in the deployment pipeline or local dev setup.

## Failed / Not Compatible

### 3. Claude Code Plugins
All three plugin installs failed. `claude plugin add` is not a recognized command in the current Claude Code CLI version.

| Plugin | Result |
|--------|--------|
| `himself65/finance-skills` | `error: unknown command 'add'` |
| `staskh/trading_skills` | `error: unknown command 'add'` |
| `wshobson/agents` | `error: unknown command 'add'` |

These may need to be installed via a different mechanism (e.g., `claude mcp add`, manual plugin directory placement, or a future CLI update).

## Not Installed (by design)
- freqtrade (GPL license conflict)
- FinRL (research-grade only)
- zipline (unmaintained)
- OctagonAI/skills (unverified single maintainer)
- lightweight-charts React wrapper (deferred per instructions)

## Build Verification
- **`next build` with `NEXTAUTH_SECRET=test`**: Passed
- All 8 static pages generated, all dynamic API routes compiled
- No TypeScript errors
- No build errors introduced by `lightweight-charts` addition

## Files Modified
- `/package.json` — added `lightweight-charts: ^5.1.0` to dependencies
- `/package-lock.json` — updated (2 packages added)
- `/python/requirements.txt` — added 3 new entries (quantstats, riskfolio-lib, neuralforecast)
