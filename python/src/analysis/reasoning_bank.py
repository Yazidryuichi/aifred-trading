"""ReasoningBank — semantic memory for LLM trading decisions.

Inspired by FenixAI's ReasoningBank (arXiv:2509.25140).
Stores every meta-reasoning trace with market context embeddings.
Before new decisions, retrieves similar past situations and their outcomes.
"""

import json
import logging
import os
import time
from typing import Dict, List, Optional
from collections import deque

logger = logging.getLogger(__name__)


class ReasoningEntry:
    """A single reasoning trace with context and outcome."""
    def __init__(self, symbol: str, timestamp: float, market_context: Dict,
                 reasoning: str, decision: str, confidence: float,
                 outcome_pnl: Optional[float] = None, quality_score: Optional[float] = None):
        self.symbol = symbol
        self.timestamp = timestamp
        self.market_context = market_context  # indicators, prices, etc.
        self.reasoning = reasoning
        self.decision = decision  # BUY/SELL/HOLD
        self.confidence = confidence
        self.outcome_pnl = outcome_pnl  # filled after trade closes
        self.quality_score = quality_score  # filled by LLM-as-Judge

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "decision": self.decision,
            "confidence": self.confidence,
            "reasoning": self.reasoning[:200],  # truncate for prompt
            "outcome_pnl": self.outcome_pnl,
            "quality_score": self.quality_score,
        }


class ReasoningBank:
    """Store and retrieve past LLM reasoning with simple similarity matching.

    Uses a lightweight approach: match by symbol + similar indicator values
    instead of heavy embedding models (keeps it fast and dependency-free).
    """

    MAX_ENTRIES = 500
    PERSIST_PATH = "data/reasoning_bank.json"

    def __init__(self, persist_path: Optional[str] = None):
        self._entries: List[ReasoningEntry] = []
        self._persist_path = persist_path or self.PERSIST_PATH
        self._load()

    def store(self, entry: ReasoningEntry) -> None:
        """Store a new reasoning trace."""
        self._entries.append(entry)
        if len(self._entries) > self.MAX_ENTRIES:
            self._entries = self._entries[-self.MAX_ENTRIES:]
        self._save()
        logger.debug("ReasoningBank: stored entry for %s (total: %d)",
                     entry.symbol, len(self._entries))

    def retrieve_similar(self, symbol: str, market_context: Dict, n: int = 3) -> List[ReasoningEntry]:
        """Find the N most similar past situations for this symbol.

        Similarity is based on matching symbol + closest indicator values.
        """
        # Filter by same symbol first
        same_symbol = [e for e in self._entries if e.symbol == symbol and e.outcome_pnl is not None]
        if not same_symbol:
            return []

        # Score similarity based on key indicator values
        scored = []
        for entry in same_symbol:
            score = self._similarity_score(market_context, entry.market_context)
            scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:n]]

    def update_outcome(self, symbol: str, timestamp: float, pnl: float) -> None:
        """Update the outcome P&L for a past reasoning entry."""
        for entry in reversed(self._entries):
            if entry.symbol == symbol and abs(entry.timestamp - timestamp) < 300:
                entry.outcome_pnl = pnl
                self._save()
                logger.info("ReasoningBank: updated outcome for %s: P&L=%.2f", symbol, pnl)
                return

    def update_quality_score(self, symbol: str, timestamp: float, score: float) -> None:
        """Update the LLM-as-Judge quality score."""
        for entry in reversed(self._entries):
            if entry.symbol == symbol and abs(entry.timestamp - timestamp) < 300:
                entry.quality_score = score
                self._save()
                return

    def format_for_prompt(self, similar_entries: List[ReasoningEntry]) -> str:
        """Format similar past decisions for inclusion in LLM prompt."""
        if not similar_entries:
            return ""

        lines = ["\n## Similar Past Situations (from memory):"]
        for i, entry in enumerate(similar_entries, 1):
            pnl_str = f"P&L: {entry.outcome_pnl:+.2f}%" if entry.outcome_pnl is not None else "outcome unknown"
            quality_str = f", quality: {entry.quality_score:.1f}/1.0" if entry.quality_score is not None else ""
            lines.append(
                f"{i}. [{entry.decision}] conf={entry.confidence:.0f}% ({pnl_str}{quality_str})"
                f"\n   Reasoning: {entry.reasoning[:150]}"
            )
        return "\n".join(lines)

    def _similarity_score(self, ctx_a: Dict, ctx_b: Dict) -> float:
        """Simple similarity based on shared numeric indicator values."""
        if not ctx_a or not ctx_b:
            return 0.0

        score = 0.0
        compared = 0
        for key in ctx_a:
            if key in ctx_b:
                val_a = ctx_a[key]
                val_b = ctx_b[key]
                if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
                    if val_b != 0:
                        # Closer values = higher score
                        ratio = 1 - min(abs(val_a - val_b) / max(abs(val_b), 0.001), 1.0)
                        score += ratio
                        compared += 1

        return score / max(compared, 1)

    def _save(self) -> None:
        """Persist to JSON."""
        try:
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
            data = [e.to_dict() for e in self._entries[-self.MAX_ENTRIES:]]
            with open(self._persist_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug("ReasoningBank save failed: %s", e)

    def _load(self) -> None:
        """Load from JSON."""
        try:
            if os.path.exists(self._persist_path):
                with open(self._persist_path) as f:
                    data = json.load(f)
                for d in data:
                    entry = ReasoningEntry(
                        symbol=d.get("symbol", ""),
                        timestamp=d.get("timestamp", 0),
                        market_context={},  # not persisted
                        reasoning=d.get("reasoning", ""),
                        decision=d.get("decision", "HOLD"),
                        confidence=d.get("confidence", 0),
                        outcome_pnl=d.get("outcome_pnl"),
                        quality_score=d.get("quality_score"),
                    )
                    self._entries.append(entry)
                logger.info("ReasoningBank: loaded %d entries from disk", len(self._entries))
        except Exception as e:
            logger.debug("ReasoningBank load failed: %s", e)
