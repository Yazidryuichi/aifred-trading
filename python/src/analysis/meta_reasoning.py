"""Meta-reasoning agent: LLM-powered decision layer on top of ML signals.

The meta-reasoning agent receives structured inputs from the ML ensemble
and sentiment analysis, then uses an LLM (Claude or DeepSeek) to:

1. Evaluate whether the quantitative signals align with current market context
2. Identify risks or opportunities the ML models might miss (news, events, regime shifts)
3. Adjust confidence scores based on reasoning
4. Provide a structured trading decision with full reasoning trace
5. Flag potential issues (conflicting signals, unusual patterns, data quality)

The LLM does NOT replace ML models. It acts as a "senior trader" reviewing
the quant team's recommendations before execution.

Output is a structured JSON decision (inspired by NoFx's pattern):
{
    "action": "BUY" | "SELL" | "HOLD" | "SKIP",
    "symbol": "BTC/USDT",
    "confidence": 0.82,
    "adjusted_confidence": 0.78,
    "size_adjustment": 1.0,  # multiplier (0.5 = half size, 1.5 = increase)
    "reasoning": "Strong LSTM signal aligned with positive sentiment shift...",
    "risk_notes": "Correlation with ETH at 0.65, within limits",
    "concerns": ["Approaching resistance at $68k", "Volume declining"],
    "time_horizon": "4-8 hours",
    "conviction": "medium"  # low, medium, high
}
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.utils.types import Direction, Signal, Position

logger = logging.getLogger(__name__)


@dataclass
class MetaDecision:
    """Structured decision from the meta-reasoning agent."""
    action: str  # "BUY", "SELL", "HOLD", "SKIP"
    symbol: str
    original_confidence: float  # from signal fusion
    adjusted_confidence: float  # after LLM reasoning
    size_adjustment: float  # multiplier for position size
    reasoning: str  # full reasoning trace
    risk_notes: str
    concerns: List[str] = field(default_factory=list)
    time_horizon: str = ""
    conviction: str = "medium"  # low, medium, high
    llm_model: str = ""
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    raw_response: str = ""  # full LLM response for audit

    @property
    def should_trade(self) -> bool:
        """Return True if the decision recommends opening a position."""
        return self.action in ("BUY", "SELL")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for logging and audit trail."""
        return {
            "action": self.action,
            "symbol": self.symbol,
            "original_confidence": self.original_confidence,
            "adjusted_confidence": self.adjusted_confidence,
            "size_adjustment": self.size_adjustment,
            "reasoning": self.reasoning,
            "risk_notes": self.risk_notes,
            "concerns": self.concerns,
            "time_horizon": self.time_horizon,
            "conviction": self.conviction,
            "llm_model": self.llm_model,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp.isoformat(),
        }


class MetaReasoningAgent:
    """LLM-powered meta-reasoning layer for trading decisions.

    Sits between signal fusion and risk gate:

    ML Signals + Sentiment -> Signal Fusion -> **Meta-Reasoning** -> Risk Gate -> Execution

    The agent:
    1. Receives the fused signal (direction + confidence)
    2. Gets current market context (prices, indicators, positions)
    3. Asks the LLM to reason about whether to act
    4. Returns a structured MetaDecision
    5. The orchestrator uses this to adjust confidence before risk gate
    """

    def __init__(self, config: Dict[str, Any]):
        self._config = config
        meta_cfg = config.get("meta_reasoning", {})

        self._enabled = meta_cfg.get("enabled", True)
        self._model = meta_cfg.get("model", "claude-sonnet-4-20250514")
        self._provider = meta_cfg.get("provider", "anthropic")  # "anthropic" or "openai"
        self._max_tokens = meta_cfg.get("max_tokens", 1024)
        self._temperature = meta_cfg.get("temperature", 0.3)
        self._timeout = meta_cfg.get("timeout_seconds", 30)

        # Confidence adjustment bounds
        self._max_confidence_boost = meta_cfg.get("max_confidence_boost", 10.0)
        self._max_confidence_penalty = meta_cfg.get("max_confidence_penalty", 20.0)

        # Minimum fused confidence to trigger meta-reasoning (avoid wasting LLM calls)
        self._min_trigger_confidence = meta_cfg.get("min_trigger_confidence", 60.0)

        # API client (lazy-initialized)
        self._client = None
        self._init_client()

        # Metrics
        self._call_count: int = 0
        self._total_latency_ms: float = 0.0
        self._error_count: int = 0

    @property
    def enabled(self) -> bool:
        """Whether the meta-reasoning agent is enabled and has an API client."""
        return self._enabled and self._client is not None

    @property
    def status(self) -> Dict[str, Any]:
        """Return status dict for monitoring."""
        avg_latency = (
            self._total_latency_ms / self._call_count
            if self._call_count > 0
            else 0.0
        )
        return {
            "enabled": self._enabled,
            "provider": self._provider,
            "model": self._model,
            "client_initialized": self._client is not None,
            "call_count": self._call_count,
            "error_count": self._error_count,
            "avg_latency_ms": round(avg_latency, 1),
        }

    def _init_client(self):
        """Initialize the LLM API client."""
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if self._provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "")

        if not api_key:
            api_key = self._config.get("meta_reasoning", {}).get("api_key", "")

        if not api_key:
            logger.warning("Meta-reasoning agent: no API key found, will be disabled")
            self._enabled = False
            return

        if self._provider == "anthropic":
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=api_key)
                logger.info(
                    "Meta-reasoning agent initialized (provider=anthropic, model=%s)",
                    self._model,
                )
            except ImportError:
                logger.warning(
                    "anthropic package not installed, meta-reasoning disabled"
                )
                self._enabled = False
        elif self._provider == "openai":
            try:
                import openai
                self._client = openai.OpenAI(api_key=api_key)
                logger.info(
                    "Meta-reasoning agent initialized (provider=openai, model=%s)",
                    self._model,
                )
            except ImportError:
                logger.warning(
                    "openai package not installed, meta-reasoning disabled"
                )
                self._enabled = False
        else:
            logger.error("Unknown meta-reasoning provider: %s", self._provider)
            self._enabled = False

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        symbol: str,
        fused_signal: Signal,
        tech_signal: Optional[Signal],
        sentiment_signal: Optional[Signal],
        indicators: Dict[str, Any],
        positions: List[Position],
        portfolio_value: float,
        risk_state: Dict[str, Any],
    ) -> str:
        """Build the reasoning prompt with full context."""

        prompt = f"""You are a senior quantitative trader reviewing a trading signal from an AI ensemble system.
Your job is to evaluate whether this signal should be acted upon, considering factors the models might miss.

## Current Signal
- Symbol: {symbol}
- Direction: {fused_signal.direction.value}
- Confidence: {fused_signal.confidence:.1f}%
- Source: {fused_signal.source}

## Technical Analysis Signal
{self._format_signal(tech_signal) if tech_signal else "Unavailable"}

## Sentiment Analysis Signal
{self._format_signal(sentiment_signal) if sentiment_signal else "Unavailable"}

## Current Market Data
{json.dumps(indicators, indent=2, default=str)}

## Portfolio State
- Total Value: ${portfolio_value:,.2f}
- Open Positions: {len(positions)}
{self._format_positions(positions)}

## Risk State
{json.dumps(risk_state, indent=2, default=str)}

## Your Task
Analyze the above and respond with a JSON decision. Consider:
1. Do the technical and sentiment signals agree or conflict?
2. Are there any warning signs in the indicators (extreme RSI, divergences, low volume)?
3. Is the portfolio already exposed to correlated risk?
4. What is your confidence level, and should it be higher or lower than the model's {fused_signal.confidence:.1f}%?
5. Any concerns about timing, market conditions, or data quality?

Respond ONLY with valid JSON in this exact format:
{{
    "action": "BUY" or "SELL" or "HOLD" or "SKIP",
    "adjusted_confidence": <number 0-100>,
    "size_adjustment": <number 0.5-1.5>,
    "reasoning": "<2-3 sentences explaining your decision>",
    "risk_notes": "<key risk factors>",
    "concerns": ["<concern 1>", "<concern 2>"],
    "time_horizon": "<expected holding period>",
    "conviction": "low" or "medium" or "high"
}}"""
        return prompt

    def _format_signal(self, signal: Signal) -> str:
        """Format a signal for the prompt."""
        if not signal:
            return "N/A"
        meta = signal.metadata or {}
        return (
            f"- Direction: {signal.direction.value}\n"
            f"- Confidence: {signal.confidence:.1f}%\n"
            f"- Source: {signal.source}\n"
            f"- Details: {json.dumps(meta, default=str)}"
        )

    def _format_positions(self, positions: List[Position]) -> str:
        """Format positions for the prompt."""
        if not positions:
            return "- No open positions"
        lines = []
        for p in positions:
            pnl = p.unrealized_pnl
            lines.append(
                f"- {p.asset} {p.side}: entry=${p.entry_price:,.2f}, "
                f"current=${p.current_price:,.2f}, P&L=${pnl:,.2f}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Core evaluation
    # ------------------------------------------------------------------

    async def evaluate(
        self,
        symbol: str,
        fused_signal: Signal,
        tech_signal: Optional[Signal] = None,
        sentiment_signal: Optional[Signal] = None,
        indicators: Optional[Dict[str, Any]] = None,
        positions: Optional[List[Position]] = None,
        portfolio_value: float = 0.0,
        risk_state: Optional[Dict[str, Any]] = None,
    ) -> MetaDecision:
        """Evaluate a trading signal through LLM reasoning.

        Returns a MetaDecision with adjusted confidence and full reasoning.
        If the LLM is unavailable, returns a pass-through decision (no adjustment).
        """
        if not self._enabled or not self._client:
            return self._passthrough_decision(
                symbol, fused_signal,
                reasoning="Meta-reasoning disabled, passing through ML signal",
            )

        # Don't waste LLM calls on low-confidence signals
        if fused_signal.confidence < self._min_trigger_confidence:
            return self._passthrough_decision(
                symbol, fused_signal,
                reasoning=(
                    f"Fused confidence {fused_signal.confidence:.1f}% below "
                    f"meta-reasoning trigger threshold {self._min_trigger_confidence}%"
                ),
            )

        # Build prompt
        prompt = self._build_prompt(
            symbol,
            fused_signal,
            tech_signal,
            sentiment_signal,
            indicators or {},
            positions or [],
            portfolio_value,
            risk_state or {},
        )

        # Call LLM with timeout
        start_time = time.time()
        try:
            raw_response = await self._call_llm(prompt)
            latency = (time.time() - start_time) * 1000
            self._call_count += 1
            self._total_latency_ms += latency
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            self._error_count += 1
            logger.error(
                "Meta-reasoning LLM call failed after %.0fms: %s", latency, e
            )
            return self._passthrough_decision(
                symbol, fused_signal,
                reasoning=f"LLM call failed: {e}. Passing through ML signal.",
            )

        # Parse response
        decision = self._parse_response(raw_response, symbol, fused_signal)
        decision.latency_ms = latency
        decision.llm_model = self._model
        decision.raw_response = raw_response

        # Clamp confidence adjustment within bounds
        max_boost = fused_signal.confidence + self._max_confidence_boost
        min_penalty = fused_signal.confidence - self._max_confidence_penalty
        decision.adjusted_confidence = max(
            min_penalty, min(max_boost, decision.adjusted_confidence)
        )
        decision.adjusted_confidence = max(0.0, min(100.0, decision.adjusted_confidence))

        # Clamp size adjustment
        decision.size_adjustment = max(0.5, min(1.5, decision.size_adjustment))

        logger.info(
            "Meta-reasoning for %s: %s (conf %.1f->%.1f, size x%.2f, "
            "conviction=%s) [%dms]",
            symbol,
            decision.action,
            decision.original_confidence,
            decision.adjusted_confidence,
            decision.size_adjustment,
            decision.conviction,
            int(decision.latency_ms),
        )

        return decision

    # ------------------------------------------------------------------
    # LLM API call
    # ------------------------------------------------------------------

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM API and return the response text.

        Runs the synchronous API client in a thread to avoid blocking
        the asyncio event loop.
        """
        import asyncio

        if self._provider == "anthropic":
            def _call():
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text

            return await asyncio.wait_for(
                asyncio.to_thread(_call),
                timeout=self._timeout,
            )

        elif self._provider == "openai":
            def _call():
                response = self._client.chat.completions.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.choices[0].message.content

            return await asyncio.wait_for(
                asyncio.to_thread(_call),
                timeout=self._timeout,
            )

        raise ValueError(f"Unknown LLM provider: {self._provider}")

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(
        self, response: str, symbol: str, fused_signal: Signal
    ) -> MetaDecision:
        """Parse LLM JSON response into MetaDecision.

        Handles markdown code blocks and gracefully falls back to HOLD
        on parse failure (conservative default).
        """
        try:
            # Extract JSON from response (handle markdown code blocks)
            text = response.strip()
            if text.startswith("```"):
                # Remove opening ``` (with optional language tag) and closing ```
                parts = text.split("```")
                # parts[0] is empty, parts[1] is the code block content
                if len(parts) >= 2:
                    text = parts[1]
                    if text.startswith("json"):
                        text = text[4:]
            text = text.strip()

            data = json.loads(text)

            action = data.get("action", "HOLD").upper()
            # Validate action
            if action not in ("BUY", "SELL", "HOLD", "SKIP"):
                logger.warning(
                    "Invalid meta-reasoning action '%s', defaulting to HOLD", action
                )
                action = "HOLD"

            # Validate conviction
            conviction = data.get("conviction", "medium").lower()
            if conviction not in ("low", "medium", "high"):
                conviction = "medium"

            return MetaDecision(
                action=action,
                symbol=symbol,
                original_confidence=fused_signal.confidence,
                adjusted_confidence=float(
                    data.get("adjusted_confidence", fused_signal.confidence)
                ),
                size_adjustment=float(data.get("size_adjustment", 1.0)),
                reasoning=data.get("reasoning", ""),
                risk_notes=data.get("risk_notes", ""),
                concerns=data.get("concerns", []),
                time_horizon=data.get("time_horizon", ""),
                conviction=conviction,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning("Failed to parse meta-reasoning response: %s", e)
            return MetaDecision(
                action="HOLD",
                symbol=symbol,
                original_confidence=fused_signal.confidence,
                adjusted_confidence=fused_signal.confidence,
                size_adjustment=1.0,
                reasoning=f"Parse error: {e}. Original response: {response[:200]}",
                risk_notes="LLM response could not be parsed, defaulting to HOLD",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _passthrough_decision(
        self, symbol: str, fused_signal: Signal, reasoning: str
    ) -> MetaDecision:
        """Create a pass-through decision that does not alter the fused signal."""
        # Map direction to action string
        if fused_signal.direction in (Direction.BUY, Direction.STRONG_BUY):
            action = "BUY"
        elif fused_signal.direction in (Direction.SELL, Direction.STRONG_SELL):
            action = "SELL"
        else:
            action = "HOLD"

        return MetaDecision(
            action=action,
            symbol=symbol,
            original_confidence=fused_signal.confidence,
            adjusted_confidence=fused_signal.confidence,
            size_adjustment=1.0,
            reasoning=reasoning,
            risk_notes="",
            llm_model="none (passthrough)",
        )
