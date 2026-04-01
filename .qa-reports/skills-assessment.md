# Skills & Tools Assessment Report
## Date: 2026-04-01
## Assessor: Senior Security & DevOps Engineer (Automated)

---

### Assessment Summary Table

| # | Repo | Type | Stars | Last Commit | Security | Relevance | Verdict |
|---|------|------|-------|-------------|----------|-----------|---------|
| 1 | wshobson/agents | Claude Code Plugin Marketplace | 32.7k | Active (2026) | LOW RISK - MIT, well-known | MEDIUM - has quant-trading plugin | INSTALL (selective) |
| 2 | RKiding/Awesome-finance-skills | Claude Code Skills Collection | 1.5k | 2026-01-31 | LOW RISK - Apache-2.0 | HIGH - finance agent skills | INVESTIGATE FURTHER |
| 3 | himself65/finance-skills | Claude Code Plugin | 663 | 2026-04-01 | LOW RISK - MIT, active | HIGH - finance analysis skills | INSTALL |
| 4 | OctagonAI/skills | Claude Code Plugin (MCP) | 27 | 2026-02-02 | MEDIUM RISK - single maintainer, requires API key | MEDIUM - financial data skills | INVESTIGATE FURTHER |
| 5 | staskh/trading_skills | Claude Code Skills + Python lib | 64 | 2026-02-27 | LOW RISK - MIT, clean deps | HIGH - options trading, IB integration | INSTALL |
| 6 | TauricResearch/TradingAgents (via tradingagents-ai.github.io) | Python Library (Research) | 45.4k | Active (2026) | LOW RISK - Apache-2.0, well-maintained | HIGH - multi-agent trading framework | INSTALL |
| 7a | freqtrade/freqtrade | Python Trading Bot | 48.2k | Active (2026) | LOW RISK - mature, huge community | MEDIUM - bot framework, not agent-native | SKIP |
| 7b | AI4Finance-Foundation/FinRL | Python RL Framework | 14.6k | Active (2026) | LOW RISK - MIT, academic pedigree | MEDIUM - RL trading, research-grade | SKIP |
| 7c | microsoft/qlib | Python Quant Platform | 39.7k | Active (2026) | VERY LOW RISK - Microsoft-backed | HIGH - ML quant platform, pip-installable | INSTALL |
| 7d | quantopian/zipline | Python Backtesting | 19.6k | Stale | LOW RISK - but unmaintained | LOW - legacy, Quantopian shut down | SKIP |
| 7e | vectorbt (polakowo) | Python Backtesting Engine | 7k | Active | LOW RISK - MIT | MEDIUM - fast backtesting | SKIP (for now) |

---

### Detailed Assessments

---

#### 1. wshobson/agents
**URL:** https://github.com/wshobson/agents
**Type:** Claude Code Plugin Marketplace (72 plugins, 112 agents, 146 skills)
**Stars:** 32,700 | **License:** MIT | **Language:** Markdown

**Description:** A comprehensive marketplace of Claude Code plugins covering full-stack development, security, infrastructure, and more. Contains a `quantitative-trading` plugin with agents and skills subdirectories.

**Security Analysis:**
- POSITIVE: MIT license, high star count, active community (3.6k forks)
- POSITIVE: Well-structured plugin architecture with clear boundaries
- CAUTION: Large surface area (72 plugins) -- only install what we need
- CAUTION: Plugin code runs within Claude Code context -- review individual plugin code before installation

**Relevance to AIFred:** The `quantitative-trading` plugin is directly relevant. The broader plugin ecosystem (dev tools, security, infrastructure) could accelerate development workflows but is not trading-specific.

**Recommendation:** INSTALL -- but only the `quantitative-trading` plugin. Review its agents/ and skills/ directories before installation. Do not bulk-install all 72 plugins.

**Installation:** `claude plugin add wshobson/agents/plugins/quantitative-trading` (verify exact syntax)

---

#### 2. RKiding (User Profile) / Awesome-finance-skills
**URL:** https://github.com/RKiding/Awesome-finance-skills
**Type:** Python-based Claude Code Skills Collection (8 skills)
**Stars:** 1,500 | **License:** Apache-2.0 | **Language:** Python

**Description:** Eight specialized finance agent skills including news aggregation, stock data (A-shares, HK, US), sentiment analysis (FinBERT), time-series prediction (Kronos), signal tracking, visualization, reporting, and RAG-based search. Built by an HKUST master's candidate specializing in AI finance.

**Security Analysis:**
- POSITIVE: Apache-2.0 license, 192 forks indicates community validation
- POSITIVE: Academic background (HKUST) adds credibility
- CAUTION: External data source dependencies (news APIs, market feeds) need validation
- CAUTION: Sentiment analysis uses FinBERT -- verify model provenance
- CAUTION: Multi-framework targeting (Antigravity, OpenCode, OpenClaw, Claude Code) -- ensure Claude Code integration is mature

**Relevance to AIFred:** HIGH -- the sentiment analysis (`alphaear-sentiment`), news aggregation (`alphaear-news`), and signal tracking (`alphaear-signal-tracker`) directly complement AIFred's existing capabilities. However, we already have finbert-embedding, spacy, and nltk in our requirements.txt for NLP.

**Recommendation:** INVESTIGATE FURTHER -- Clone and audit the specific skills we need (sentiment, news, signal-tracker). Check for dependency conflicts with our existing NLP stack. The prediction skill (`alphaear-predictor`) using Kronos is particularly interesting but needs validation.

---

#### 3. himself65/finance-skills
**URL:** https://github.com/himself65/finance-skills
**Type:** Claude Code Plugin / Agent Skills
**Stars:** 663 | **License:** MIT | **Last Commit:** 2026-04-01 (today)

**Description:** 11 modular agent skills for financial analysis: options payoff visualization, stock correlation analysis, market data retrieval, geopolitical risk monitoring (Hormuz Strait), and social sentiment research (Discord, Telegram, Twitter/X).

**Security Analysis:**
- POSITIVE: MIT license, actively maintained (committed today)
- POSITIVE: Installable via multiple methods (Claude Code plugin, npx, manual)
- POSITIVE: 663 stars indicates community trust
- CAUTION: Social media scraping tools (Discord CDP, Telegram `tdl`, Twitter/X) may have ToS implications
- CAUTION: External tool dependencies (`opencli`, `tdl`) need security review

**Relevance to AIFred:** HIGH -- Fills gaps we currently lack:
- Geopolitical risk monitoring (we have no equivalent)
- Options payoff visualization (we have options analysis via pandas-ta but no visualization skills)
- Social sentiment across Discord/Telegram (we only have Reddit via `praw`)
- Stock correlation analysis

**Recommendation:** INSTALL -- Start with the analysis/data skills (market data, correlation, options). Defer social sentiment skills until we audit the scraping tools (`opencli`, `tdl`) for security and ToS compliance.

**Installation:** `claude plugin add himself65/finance-skills` or `npx skills add <skill-name>`

---

#### 4. OctagonAI/skills
**URL:** https://github.com/OctagonAI/skills
**Type:** Claude Code Plugin (MCP-based)
**Stars:** 27 | **License:** MIT | **Last Commit:** 2026-02-02 | **Contributors:** 1

**Description:** 60+ skills for financial research via Octagon MCP server. Covers financial metrics (16 skills), earnings calls (14), SEC filings (16), stock/market data (18), and prediction markets (1 - Kalshi).

**Security Analysis:**
- WARNING: Single contributor (melvinmt) -- low bus factor
- WARNING: Only 27 stars -- limited community validation
- WARNING: Requires Octagon API key -- introduces third-party dependency and data flow
- CAUTION: All data flows through Octagon's MCP server -- data privacy implications for a trading platform
- POSITIVE: MIT license, clear skill organization

**Relevance to AIFred:** MEDIUM -- The SEC filings analysis and earnings call analysis are valuable capabilities we lack. However, routing all financial data through a third-party MCP server introduces latency and privacy concerns for a live trading platform.

**Recommendation:** INVESTIGATE FURTHER -- Evaluate Octagon's API terms, data privacy policy, and latency characteristics. The SEC filings and earnings call skills are compelling but the single-maintainer risk and third-party data routing are concerning for production use. Consider extracting the skill patterns and building our own implementations against direct data sources.

---

#### 5. staskh/trading_skills
**URL:** https://github.com/staskh/trading_skills
**Type:** Claude Code Skills + Python Library + MCP Server
**Stars:** 64 | **License:** MIT | **Last Commit:** 2026-02-27 | **Language:** Python (100%)

**Description:** Claude-powered advisor for options traders. Consolidates market analysis, technicals, fundamentals, option Greeks, risk metrics, and portfolio management. 21 Claude Code skills + 23 MCP tools. Supports Interactive Brokers integration.

**Security Analysis:**
- POSITIVE: Clean dependency chain -- yfinance, ib-async, pandas, numpy, scipy, mcp (all well-known)
- POSITIVE: No suspicious packages in pyproject.toml
- POSITIVE: MIT license, includes tests (pytest, pytest-asyncio)
- POSITIVE: Python 3.12+ requirement aligns with modern security practices
- CAUTION: Interactive Brokers integration means it handles broker credentials -- review credential management
- CAUTION: 64 stars is modest but reasonable for a specialized tool

**Relevance to AIFred:** HIGH -- Direct overlap and enhancement:
- We already use yfinance and pandas-ta -- minimal dependency overhead
- IB integration via `ib-async` complements our existing `ccxt` and `alpaca-trade-api`
- Options-specific analysis fills a gap (we lack dedicated options tooling)
- MCP server can expose trading tools to Claude Desktop for manual oversight

**Recommendation:** INSTALL -- pip install into Python backend. Start with the analysis skills (Greeks, correlation, risk). The IB integration is valuable if we expand to options trading. Review the credential handling code before connecting to a live broker.

**Installation:** `pip install trading-skills` + copy `.claude/skills/` to project

---

#### 6. TauricResearch/TradingAgents
**URL:** https://github.com/TauricResearch/TradingAgents
**Website:** https://tradingagents-ai.github.io/
**Type:** Python Library (Multi-Agent Trading Framework)
**Stars:** 45,400 | **License:** Apache-2.0 | **Language:** Python (100%)

**Description:** Multi-agent LLM framework that simulates a professional trading firm. Specialized agents (fundamental analyst, sentiment analyst, technical analyst, trader, risk manager) engage in structured debates to make trading decisions. Uses LangGraph for orchestration.

**Security Analysis:**
- POSITIVE: Apache-2.0 license, massive community (45.4k stars, 8.2k forks)
- POSITIVE: Multi-LLM support (OpenAI, Anthropic, Google, Ollama) -- not locked to one provider
- POSITIVE: Well-documented with academic backing
- CAUTION: Research disclaimer ("not financial advice") -- expected for this domain
- CAUTION: Depends on Alpha Vantage API for market data -- free tier has rate limits
- NOTE: LangGraph dependency may conflict with our existing agent orchestration

**Relevance to AIFred:** VERY HIGH -- This is architecturally similar to AIFred's multi-agent approach:
- Analyst team pattern mirrors AIFred's signal fusion concept
- Bullish/bearish debate mechanism could enhance our AI competition features
- Risk management agent aligns with our risk management module
- Backtesting capabilities complement our existing setup

**Recommendation:** INSTALL -- but as a reference/library integration, not a replacement for AIFred's core. Key integration points:
1. Study the debate mechanism for our AI competition feature
2. Potentially use their analyst agent patterns as templates
3. Evaluate LangGraph vs our current orchestration approach
4. Use their backtesting framework for validation

**Installation:** `git clone` + `pip install .` (not on PyPI as standalone package)

---

#### 7. Algorithmic Trading Topic -- Top Repos Assessment

##### 7a. freqtrade/freqtrade (48.2k stars)
**Type:** Python crypto trading bot with FreqAI ML module
**Verdict:** SKIP -- Freqtrade is a standalone bot framework, not a library. Its architecture is opinionated and would require significant adaptation. FreqAI is interesting but we already have our own ML pipeline (torch, xgboost, lightgbm, catboost). Better as a reference than a dependency.

##### 7b. AI4Finance-Foundation/FinRL (14.6k stars)
**Type:** Financial Reinforcement Learning framework (MIT, NeurIPS 2020)
**Verdict:** SKIP -- Research-grade, not production-hardened. The maintainers themselves direct production users to "FinRL-X". We already have torch and could implement specific RL strategies without taking on the full framework. Useful as a reference for RL strategy patterns.

##### 7c. microsoft/qlib (39.7k stars) -- See #8 below

##### 7d. quantopian/zipline (19.6k stars)
**Type:** Legacy backtesting library (Quantopian is defunct)
**Verdict:** SKIP -- Unmaintained since Quantopian shutdown. Community forks exist (zipline-reloaded) but the ecosystem has moved on. We have better options.

##### 7e. polakowo/vectorbt (7k stars)
**Type:** High-performance backtesting engine
**Verdict:** SKIP (for now) -- Excellent for rapid backtesting but we already have backtesting capabilities. Could be valuable later for performance optimization. Flag for Phase 6+ consideration.

---

#### 8. microsoft/qlib
**URL:** https://github.com/microsoft/qlib
**Type:** Python Quantitative Investment Platform
**Stars:** 39,700 | **License:** Apache-2.0 | **Language:** Python

**Description:** Microsoft's AI-oriented quant investment platform. Covers data processing, model training (LightGBM, Transformer, LSTM, TabNet), backtesting, portfolio optimization, and order execution. Includes RD-Agent for LLM-based autonomous research.

**Security Analysis:**
- VERY LOW RISK: Microsoft-maintained, Apache-2.0, massive community (6.2k forks)
- POSITIVE: Enterprise-grade code quality expectations
- POSITIVE: Well-documented, actively maintained
- POSITIVE: Pip-installable (`pip install pyqlib`)
- NOTE: Heavy dependency chain (Cython, NumPy, LightGBM) -- but we already use most of these

**Relevance to AIFred:** HIGH -- Complementary capabilities:
- Point-in-Time database prevents look-ahead bias (critical for backtesting integrity)
- Model zoo (HIST, IGMTF, KRNN) provides pre-built quant models
- Nested Decision Framework for multi-level strategy optimization
- RD-Agent for autonomous factor mining aligns with our AI-first approach
- Minimal new dependency overhead (we already have lightgbm, numpy, pandas, scipy)

**Recommendation:** INSTALL -- `pip install pyqlib`. Start with:
1. Data infrastructure (Point-in-Time DB) for backtesting integrity
2. Model zoo for benchmarking our existing models
3. RD-Agent integration for autonomous strategy research

**Installation:** `pip install pyqlib`

---

#### 9. TauricResearch/TradingAgents
(Covered in #6 above -- same repo referenced by tradingagents-ai.github.io)

---

### Recommended Installations (Priority Order)

#### Priority 1 -- High Value, Low Risk (Install This Week)

| Tool | Type | Installation | Rationale |
|------|------|-------------|-----------|
| microsoft/qlib | pip package | `pip install pyqlib` | Microsoft-backed, fills backtesting/model gaps |
| staskh/trading_skills | pip + Claude skills | `pip install trading-skills` | Clean deps, options analysis, IB integration |
| himself65/finance-skills | Claude Code plugin | `claude plugin add himself65/finance-skills` | Geopolitical risk, correlation analysis, active today |

#### Priority 2 -- High Value, Needs Integration Work (Install This Month)

| Tool | Type | Installation | Rationale |
|------|------|-------------|-----------|
| TauricResearch/TradingAgents | Python library | `git clone` + `pip install .` | Multi-agent debate architecture, study for AIFred enhancement |
| wshobson/agents (quant-trading plugin only) | Claude Code plugin | `claude plugin add` (quant-trading) | Selective install of trading plugin only |

#### Priority 3 -- Needs Investigation Before Decision

| Tool | Action Needed | Timeline |
|------|--------------|----------|
| RKiding/Awesome-finance-skills | Audit alphaear-sentiment and alphaear-predictor for dep conflicts | 1-2 weeks |
| OctagonAI/skills | Evaluate Octagon API terms, privacy policy, latency | 1-2 weeks |

---

### Repos to Skip (with Reasons)

| Repo | Reason |
|------|--------|
| freqtrade/freqtrade | Standalone bot framework, not a library. Opinionated architecture incompatible with AIFred's multi-agent design. We already have our own ML pipeline. |
| AI4Finance-Foundation/FinRL | Research-grade only. Maintainers direct production users elsewhere. We can implement specific RL strategies with our existing torch stack. |
| quantopian/zipline | Unmaintained since Quantopian shutdown. Legacy codebase with no future. |
| polakowo/vectorbt | Good backtesting engine but redundant with our current capabilities. Revisit in Phase 6+ if we need performance optimization for backtesting. |

---

### Security Notes for All Installations

1. **Dependency Pinning:** All new packages must be pinned to specific versions in requirements.txt before deployment
2. **Credential Isolation:** Any tool that handles broker credentials (trading_skills IB integration) must use environment variables, never hardcoded values
3. **API Key Management:** OctagonAI and Alpha Vantage API keys must go through our existing secrets management (Railway env vars)
4. **Data Flow Audit:** Before enabling any MCP-based tool in production, audit what data leaves our infrastructure
5. **Claude Code Plugin Sandbox:** Claude Code plugins execute within the Claude context -- they cannot directly access our production trading infrastructure unless we explicitly expose it via MCP
6. **Pre-Installation Checklist:**
   - [ ] Run `pip audit` after installing new Python packages
   - [ ] Review LICENSE compatibility (MIT and Apache-2.0 are both fine for commercial use)
   - [ ] Test in staging environment before production deployment
   - [ ] Verify no dependency version conflicts with existing requirements.txt
