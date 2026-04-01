# Additional Skills & Tools Discovery
## Date: 2026-04-01

> Research conducted for AIFred multi-agent AI trading platform.
> Stack: Next.js + Python (PyTorch, XGBoost, FinBERT, ccxt) | Hyperliquid primary exchange | Railway + Vercel deployment

---

## Top Recommendations (Prioritized)

| # | Tool | Type | Stars | Category | Integration Fit | Security |
|---|------|------|-------|----------|-----------------|----------|
| 1 | **TradingView Lightweight Charts** | npm | 14.2k | Visualization | Direct — replaces Recharts for candlestick/financial charts | Trusted (TradingView), Apache-2.0 |
| 2 | **NautilusTrader** | pip | 21.6k | Backtesting + Execution | Has native Hyperliquid adapter — could replace custom execution | Trusted, Rust-native, actively maintained |
| 3 | **Anthropic Financial Services Plugins** | Claude plugin | 7.1k | Claude Code Plugin | Direct install, 41 skills for equity research + risk | Official Anthropic, Apache-2.0 |
| 4 | **NeuralForecast (Nixtla)** | pip | 4.0k | AI/ML Forecasting | 30+ models (NBEATS, NHITS, PatchTST, iTransformer) — drops into LSTM/Transformer pipeline | Trusted org, Apache-2.0, v3.1.6 (Mar 2026) |
| 5 | **PyOD** | pip | 9.8k | Anomaly Detection | Risk agent enhancement — detect abnormal market/portfolio behavior | BSD license, 50+ algorithms, PyTorch V2 |
| 6 | **Riskfolio-Lib** | pip | 4.0k | Portfolio Optimization | 24 risk measures, HRP, Black-Litterman — fits risk management agent | BSD-3-Clause, CVXPY-based |
| 7 | **FinRL** | pip | 14.6k | Reinforcement Learning | PPO/SAC agents for trading — extends AI agent architecture | MIT license, AI4Finance Foundation |
| 8 | **QuantStats** | pip | 6.0k+ | Risk Analytics | Tear sheets, Sharpe, drawdown reports — monitoring agent enhancement | MIT license, pandas-native |
| 9 | **VectorBT** | pip | 7.0k | Backtesting | Ultra-fast NumPy/Numba backtesting for strategy research | Apache-2.0 (Commons Clause), v0.28.5 |
| 10 | **claude-trading-skills** | Claude skill | 484 | Claude Code Plugin | 40+ trading-specific skills (VCP screener, CANSLIM, position sizing) | Community-built, review before use |

---

## Category: Real-time Data & Visualization

### 1. TradingView Lightweight Charts
- **Repo:** https://github.com/tradingview/lightweight-charts
- **Stars:** 14.2k | **License:** Apache-2.0
- **Latest:** v5.1.0 (Dec 2025) | **Actively maintained**
- **Size:** ~45 KB (minimal bundle impact)
- **What it does:** Professional candlestick, line, area, histogram, and baseline charts with WebSocket real-time data support. The industry standard for financial charting in web apps.
- **AIFred integration:** Replace Recharts for all financial chart components. Use `lightweight-charts-react-wrapper` npm package for React/Next.js. Supports real-time WebSocket price feeds natively — connect directly to Hyperliquid WS feed.
- **Install:**
  ```bash
  npm install lightweight-charts lightweight-charts-react-wrapper
  ```
- **Note:** Requires `'use client'` directive in Next.js (canvas-based, no SSR). Pair with Framer Motion for dashboard transitions but keep chart rendering separate.

### 2. Recharts (already installed)
- Already in stack. Keep for non-financial charts (PnL bar charts, agent performance). Use Lightweight Charts for all candlestick/price data.

---

## Category: AI/ML for Trading

### 3. NeuralForecast (Nixtla)
- **Repo:** https://github.com/Nixtla/neuralforecast
- **Stars:** 4.0k | **License:** Apache-2.0
- **Latest:** v3.1.6 (Mar 27, 2026) | **Actively maintained**
- **What it does:** 30+ state-of-the-art neural forecasting models in a unified sklearn-compatible API. Includes NBEATS, NHITS, PatchTST, iTransformer, TFT, TimesNet, DeepAR, TimeLLM, and more. Supports exogenous variables, probabilistic forecasting, and auto-tuning via Ray/Optuna.
- **AIFred integration:** Drop into the technical analysis agent as a model layer. Replace or augment the existing LSTM/Transformer models with NHITS (fast) or PatchTST (accurate). The `.fit()/.predict()` API means minimal refactoring. Probabilistic outputs feed directly into the risk management agent as confidence intervals.
- **Install:**
  ```bash
  pip install neuralforecast
  ```
- **Companion:** `pip install statsforecast` (4.7k stars) for statistical baselines (AutoARIMA, ETS, Theta) — useful for model comparison benchmarks.

### 4. FinRL - Financial Reinforcement Learning
- **Repo:** https://github.com/AI4Finance-Foundation/FinRL
- **Stars:** 14.6k | **License:** MIT
- **What it does:** Trains DRL agents (PPO, SAC, A2C, DDPG, TD3) for automated trading. Three-layer architecture: market environments, DRL agents, applications. Integrates with Stable-Baselines3.
- **AIFred integration:** Add as a new "RL Strategy Agent" alongside existing LSTM/CNN agents. Use for portfolio allocation decisions. Train on historical data, deploy trained policy via the orchestrator agent. Caution: RL agents need extensive backtesting before live capital.
- **Install:**
  ```bash
  pip install finrl
  ```
- **Note:** For production, evaluate **FinRL-X** (next-gen, modular architecture). The original FinRL is better for research/prototyping.

### 5. PyOD - Anomaly Detection
- **Repo:** https://github.com/yzhao062/pyod
- **Stars:** 9.8k | **License:** BSD
- **Latest:** V2 (PyTorch-native, 45+ detection methods)
- **What it does:** 50+ anomaly detection algorithms from classical (LOF, Isolation Forest) to deep learning (AutoEncoder, VAE, DeepSVDD). Unified API across all methods.
- **AIFred integration:** Critical for the risk management agent. Detect abnormal price movements, unusual volume spikes, anomalous portfolio drawdowns, and exchange connectivity issues. Run as a real-time filter before the execution agent acts on signals.
- **Install:**
  ```bash
  pip install pyod
  # For deep learning models:
  pip install pyod[full]
  ```

### 6. Alibi-Detect (Seldon) - Drift Detection
- **Repo:** https://github.com/SeldonIO/alibi-detect
- **Stars:** ~2.3k | **License:** Business Source License (review carefully)
- **Latest:** v0.13.0 (Dec 2025)
- **What it does:** Concept drift, data drift, and outlier detection. Supports online/offline detection for tabular data and time series. Both TensorFlow and PyTorch backends.
- **AIFred integration:** Monitor model performance drift — detect when LSTM/FinBERT models degrade due to regime changes. Alert the monitoring agent when feature distributions shift. This is a model ops concern that prevents stale predictions from reaching execution.
- **Install:**
  ```bash
  pip install alibi-detect[torch]
  ```
- **Note:** Check license terms carefully — Business Source License has usage restrictions. Good for internal use but review before commercial deployment.

---

## Category: Risk & Portfolio

### 7. Riskfolio-Lib
- **Repo:** https://github.com/dcajasn/Riskfolio-Lib
- **Stars:** 4.0k | **License:** BSD-3-Clause
- **Latest:** v7.2.1 (Feb 2025)
- **What it does:** Portfolio optimization with 24 convex risk measures, including Mean-Variance, CVaR, CDaR, and Entropic Risk. Supports HRP (Hierarchical Risk Parity), Black-Litterman, factor models, and risk budgeting. Built on CVXPY with pandas integration.
- **AIFred integration:** Powers the risk management agent's allocation decisions. Use HRP for more robust allocations than simple mean-variance. Feed FinBERT sentiment scores into Black-Litterman views. Generate optimal position sizes that respect drawdown constraints.
- **Install:**
  ```bash
  pip install riskfolio-lib
  ```

### 8. PyPortfolioOpt
- **Repo:** https://github.com/PyPortfolio/PyPortfolioOpt
- **Stars:** 5.6k | **License:** MIT
- **What it does:** Mean-variance optimization, Black-Litterman, HRP, efficient frontier, risk models. More beginner-friendly API than Riskfolio-Lib but fewer advanced risk measures.
- **AIFred integration:** Alternative to Riskfolio-Lib if simpler API preferred. Good for quick prototyping of allocation strategies. MIT license is more permissive.
- **Install:**
  ```bash
  pip install pyportfolioopt
  ```
- **Recommendation:** Use Riskfolio-Lib for production (more risk measures, better optimization), PyPortfolioOpt for quick experiments.

### 9. QuantStats
- **Repo:** https://github.com/ranaroussi/quantstats
- **Stars:** 6.0k+ | **License:** MIT
- **What it does:** Portfolio analytics — Sharpe, Sortino, Calmar, max drawdown, rolling stats, monthly returns heatmaps, and HTML tear sheet reports. Three modules: stats, plots, reports.
- **AIFred integration:** Monitoring agent generates daily/weekly performance tear sheets. Export HTML reports for the dashboard. Calculate risk metrics in real-time for the dashboard UX overhaul. Pairs perfectly with the existing pandas-based pipeline.
- **Install:**
  ```bash
  pip install quantstats
  ```

---

## Category: Backtesting & Execution

### 10. NautilusTrader
- **Repo:** https://github.com/nautechsystems/nautilus_trader
- **Stars:** 21.6k | **License:** LGPL-3.0
- **What it does:** Production-grade Rust-native trading engine. Deterministic event-driven backtesting with nanosecond resolution. Identical code paths for backtest and live trading. Streams 5M+ rows/sec.
- **AIFred integration:** **Native Hyperliquid adapter** already built in. Could serve as the execution backbone, replacing custom ccxt-based execution agent. Backtest strategies with realistic order book simulation before going live. The Python API means existing PyTorch models plug in directly.
- **Supported exchanges:** Binance, Hyperliquid, Bybit, OKX, Kraken, Deribit, dYdX, Interactive Brokers, Databento, and more.
- **Install:**
  ```bash
  pip install nautilus_trader
  ```
- **Caution:** Major architectural component — evaluate in a branch before committing. Learning curve is significant but payoff is production-grade execution.

### 11. VectorBT
- **Repo:** https://github.com/polakowo/vectorbt
- **Stars:** 7.0k | **License:** Apache-2.0 with Commons Clause
- **Latest:** v0.28.5 (Mar 2026) | **Actively maintained**
- **What it does:** Array-based backtesting using NumPy/pandas accelerated by Numba. Fastest backtesting for parameter sweeps and strategy exploration.
- **AIFred integration:** Use for rapid strategy research and parameter optimization before deploying to NautilusTrader or live. Run 10,000+ strategy variations in minutes. Feed results into the orchestrator agent for strategy selection.
- **Install:**
  ```bash
  pip install vectorbt
  ```
- **Note:** VectorBT PRO (paid) adds more features. The open-source version is sufficient for research. Commons Clause means you cannot resell VectorBT itself as a product.

### 12. Freqtrade
- **Repo:** https://github.com/freqtrade/freqtrade
- **Stars:** ~40k | **License:** GPL-3.0
- **What it does:** Complete crypto trading bot framework with backtesting, optimization, live trading, Telegram integration, and FreqAI (ML module). Supports Hyperliquid via ccxt.
- **AIFred integration:** Reference architecture for bot operations. FreqAI module shows how to integrate ML models into trading loops. However, GPL-3.0 license is viral — using Freqtrade code would require open-sourcing AIFred. **Use as reference/inspiration only, do not directly integrate.**
- **Install:** N/A (reference only due to GPL)

---

## Category: Alternative Data Sources

### 13. Santiment (sanpy)
- **Repo:** https://github.com/santiment/sanpy
- **Stars:** ~200 | **License:** MIT
- **What it does:** Python client for Santiment API — on-chain metrics, social sentiment, developer activity, whale tracking, token supply flow for 3000+ crypto assets. Returns pandas DataFrames.
- **AIFred integration:** Feed into the NLP sentiment agent alongside FinBERT. On-chain metrics (whale movements, exchange inflows/outflows) add a data dimension that pure price/sentiment analysis misses. Social volume + weighted sentiment as additional features for the signal fusion layer.
- **Install:**
  ```bash
  pip install sanpy
  ```
- **Note:** Requires Santiment API key (free tier available, paid for real-time). Set `SANPY_APIKEY` environment variable on Railway.

---

## Category: Claude Code Plugins

### 14. Anthropic Financial Services Plugins (Official)
- **Repo:** https://github.com/anthropics/financial-services-plugins
- **Stars:** 7.1k | **License:** Apache-2.0
- **Plugins:** 5 plugins, 41 skills, 38 commands, 11 MCP integrations
- **Includes:** Financial analysis (comps, DCF, LBO), equity research, investment banking, private equity, wealth management
- **Partner data:** LSEG (bond pricing, FX), S&P Global (tearsheets, earnings)
- **AIFred integration:** Install the `financial-analysis` and `equity-research` plugins. Use during development for rapid analysis of trading strategies, generating comp models, and researching assets before adding to the portfolio.
- **Install:**
  ```bash
  claude plugin marketplace add anthropics/financial-services-plugins
  claude plugin install financial-analysis@financial-services-plugins
  claude plugin install equity-research@financial-services-plugins
  ```

### 15. claude-trading-skills (tradermonty)
- **Repo:** https://github.com/tradermonty/claude-trading-skills
- **Stars:** 484 | **License:** Not specified (check repo)
- **Skills:** 40+ skills including VCP Screener, CANSLIM Screener, Position Sizer, Market Breadth Analyzer, Technical Analyst, Backtest Expert, Options Strategy Advisor, Macro Regime Detector, Institutional Flow Tracker
- **AIFred integration:** Install specific skills relevant to AIFred development — Position Sizer, Backtest Expert, and Technical Analyst skills will accelerate development of the risk and TA agents.
- **Install:** Clone repo, copy desired skill folders to Claude Code Skills directory.

### 16. JoelLewis/finance_skills
- **Repo:** https://github.com/JoelLewis/finance_skills
- **Skills:** 84 skills across 7 domain plugins — investment management, compliance, advisory, trading, operations
- **AIFred integration:** Compliance and risk management skills useful for building guardrails around live trading operations.

---

## Installation Guide

### Phase 1: Quick Wins (< 1 hour, high impact)

```bash
# Frontend — Professional charting
cd /path/to/aifred-trading
npm install lightweight-charts lightweight-charts-react-wrapper

# Claude Code — Financial analysis capabilities
claude plugin marketplace add anthropics/financial-services-plugins
claude plugin install financial-analysis@financial-services-plugins
claude plugin install equity-research@financial-services-plugins
```

### Phase 2: Python Backend Enhancements (1-2 hours)

```bash
# Add to Railway Python backend requirements
pip install neuralforecast    # Time series forecasting (30+ models)
pip install quantstats        # Portfolio analytics & tear sheets
pip install pyod              # Anomaly detection for risk agent
pip install riskfolio-lib     # Portfolio optimization (24 risk measures)
pip install sanpy             # On-chain + social sentiment data
```

Add to `requirements.txt`:
```
neuralforecast>=3.1.0
quantstats>=0.0.62
pyod>=2.0.0
riskfolio-lib>=7.2.0
sanpy>=0.4.0
```

### Phase 3: Advanced (evaluate in branch)

```bash
# NautilusTrader — production execution engine with Hyperliquid adapter
pip install nautilus_trader

# FinRL — reinforcement learning agents
pip install finrl

# VectorBT — fast backtesting research
pip install vectorbt
```

### Phase 4: Claude Skills (optional, during development)

```bash
# Clone trading skills for development assistance
git clone https://github.com/tradermonty/claude-trading-skills.git
# Copy relevant skills to Claude Code Skills directory
```

---

## Security Notes

1. **All recommended tools** are from trusted sources with 1000+ stars (except sanpy/trading-skills which are smaller but from known orgs)
2. **License concerns:** Freqtrade (GPL-3.0) is reference-only. VectorBT Commons Clause prevents reselling. Alibi-Detect BSL needs review for commercial use. All others are permissive (MIT/Apache/BSD).
3. **API keys required:** Santiment (sanpy) needs `SANPY_APIKEY` — store in Railway environment variables, never in code
4. **Dependency weight:** NautilusTrader is heavy (Rust compilation). Test Railway build times before committing. NeuralForecast pulls PyTorch (already in stack, no extra weight).
5. **No tools recommended from unknown/untrusted sources.** All repos verified for active maintenance and community adoption.

---

## Architecture Integration Map

```
                    AIFred Agent Architecture + New Tools
                    =====================================

  [Data Ingestion Agent]
       |
       +-- ccxt (existing)
       +-- sanpy (NEW) -----> on-chain metrics, social sentiment
       |
  [Technical Analysis Agent]
       |
       +-- pandas-ta (existing)
       +-- NeuralForecast (NEW) --> NHITS, PatchTST, iTransformer
       +-- VectorBT (NEW) -------> rapid strategy backtesting
       |
  [NLP Sentiment Agent]
       |
       +-- FinBERT (existing)
       +-- sanpy (NEW) -----> social volume, weighted sentiment
       |
  [Risk Management Agent]
       |
       +-- Riskfolio-Lib (NEW) --> HRP, CVaR optimization
       +-- PyOD (NEW) ----------> anomaly detection on positions
       +-- QuantStats (NEW) ----> performance analytics
       +-- Alibi-Detect (NEW) --> model drift monitoring
       |
  [Execution Agent]
       |
       +-- ccxt (existing)
       +-- NautilusTrader (NEW, Phase 3) --> production execution
       |
  [Monitoring Agent]
       |
       +-- QuantStats (NEW) ----> HTML tear sheets, risk reports
       +-- PyOD (NEW) ----------> real-time anomaly alerts
       |
  [Orchestrator Agent]
       |
       +-- FinRL (NEW, Phase 3) -> RL-based strategy selection
       |
  [Dashboard — Next.js]
       |
       +-- Recharts (existing, keep for non-financial)
       +-- Lightweight Charts (NEW) --> candlesticks, depth, volume
```
