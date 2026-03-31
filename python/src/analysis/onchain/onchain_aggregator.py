"""On-chain signal aggregator -- combines DeFiLlama and Etherscan data
into a single OnChainSignal dataclass for consumption by the meta-reasoning
agent and signal fusion pipeline.

Signal components:
- tvl_trend       -- rising / falling / stable
- whale_activity  -- accumulating / distributing / neutral
- exchange_flow   -- net_inflow / net_outflow / balanced
- defi_sentiment  -- bullish / bearish / neutral
- confidence      -- 0-1 composite confidence
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from src.analysis.onchain.defi_llama import DeFiLlamaClient
from src.analysis.onchain.etherscan_onchain import EtherscanClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Component weights for composite confidence
# ---------------------------------------------------------------------------
_COMPONENT_WEIGHTS = {
    "tvl_trend": 0.25,
    "stablecoin_flow": 0.20,
    "whale_activity": 0.20,
    "exchange_flow": 0.15,
    "gas_activity": 0.10,
    "dex_volume": 0.10,
}


@dataclass
class OnChainSignal:
    """Unified on-chain signal consumed by the trading pipeline.

    Mirrors the structure of SentimentScore / Signal from utils.types
    but is specific to on-chain data sources.
    """
    asset: str
    tvl_trend: str           # "rising" | "falling" | "stable"
    whale_activity: str      # "accumulating" | "distributing" | "neutral"
    exchange_flow: str       # "net_inflow" | "net_outflow" | "balanced"
    defi_sentiment: str      # "bullish" | "bearish" | "neutral"
    confidence: float        # 0.0 - 1.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


class OnChainAggregator:
    """Combines DeFiLlama and Etherscan signals into a unified OnChainSignal.

    Usage::

        aggregator = OnChainAggregator()
        signal = await aggregator.generate_signal("ETH/USDT")
        print(signal.tvl_trend, signal.whale_activity, signal.confidence)
        await aggregator.close()

    All sub-client sessions are managed internally.  Call ``close()`` when
    done to release HTTP connections.
    """

    def __init__(
        self,
        etherscan_api_key: Optional[str] = None,
        defi_llama_client: Optional[DeFiLlamaClient] = None,
        etherscan_client: Optional[EtherscanClient] = None,
    ):
        self._llama = defi_llama_client or DeFiLlamaClient()
        self._etherscan = etherscan_client or EtherscanClient(api_key=etherscan_api_key)

    async def close(self) -> None:
        """Close all underlying HTTP sessions."""
        await asyncio.gather(
            self._llama.close(),
            self._etherscan.close(),
            return_exceptions=True,
        )

    # ------------------------------------------------------------------
    # Main signal generation
    # ------------------------------------------------------------------

    async def generate_signal(self, asset: str) -> OnChainSignal:
        """Aggregate all on-chain data sources into a single signal.

        Fetches data concurrently where possible, then combines into
        a directional on-chain signal with composite confidence.

        Args:
            asset: Asset ticker (e.g. "ETH/USDT", "BTC/USDT").

        Returns:
            OnChainSignal with trend, activity, flow, and sentiment fields.
        """
        # Run independent data fetches concurrently
        results = await asyncio.gather(
            self._fetch_tvl_data(),
            self._fetch_stablecoin_data(),
            self._fetch_dex_data(),
            self._fetch_whale_data(),
            self._fetch_exchange_flow_data(),
            self._fetch_gas_data(),
            return_exceptions=True,
        )

        # Unpack results, treating exceptions as None
        tvl_data = results[0] if not isinstance(results[0], Exception) else None
        stable_data = results[1] if not isinstance(results[1], Exception) else None
        dex_data = results[2] if not isinstance(results[2], Exception) else None
        whale_data = results[3] if not isinstance(results[3], Exception) else None
        flow_data = results[4] if not isinstance(results[4], Exception) else None
        gas_data = results[5] if not isinstance(results[5], Exception) else None

        # Log any failures
        for i, name in enumerate([
            "tvl", "stablecoin", "dex", "whale", "exchange_flow", "gas"
        ]):
            if isinstance(results[i], Exception):
                logger.warning(
                    "On-chain %s fetch failed: %s", name, results[i]
                )

        # --- Derive component signals ---
        tvl_trend, tvl_conf, tvl_meta = self._interpret_tvl(tvl_data)
        stable_dir, stable_conf, stable_meta = self._interpret_stablecoins(stable_data)
        whale_class, whale_conf, whale_meta = self._interpret_whales(whale_data)
        flow_dir, flow_conf, flow_meta = self._interpret_exchange_flow(flow_data)
        gas_level, gas_conf, gas_meta = self._interpret_gas(gas_data)
        dex_trend, dex_conf, dex_meta = self._interpret_dex_volume(dex_data)

        # --- Derive composite DeFi sentiment ---
        defi_sentiment = self._compute_defi_sentiment(
            tvl_trend=tvl_trend,
            stable_direction=stable_dir,
            dex_trend=dex_trend,
            gas_level=gas_level,
        )

        # --- Composite confidence (weighted average of available components) ---
        confidence = self._compute_confidence({
            "tvl_trend": tvl_conf,
            "stablecoin_flow": stable_conf,
            "whale_activity": whale_conf,
            "exchange_flow": flow_conf,
            "gas_activity": gas_conf,
            "dex_volume": dex_conf,
        })

        metadata = {
            "tvl": tvl_meta,
            "stablecoins": stable_meta,
            "whales": whale_meta,
            "exchange_flow": flow_meta,
            "gas": gas_meta,
            "dex": dex_meta,
            "component_confidences": {
                "tvl": tvl_conf,
                "stablecoins": stable_conf,
                "whales": whale_conf,
                "exchange_flow": flow_conf,
                "gas": gas_conf,
                "dex": dex_conf,
            },
        }

        signal = OnChainSignal(
            asset=asset,
            tvl_trend=tvl_trend,
            whale_activity=whale_class,
            exchange_flow=flow_dir,
            defi_sentiment=defi_sentiment,
            confidence=confidence,
            metadata=metadata,
        )

        logger.info(
            "OnChainSignal: asset=%s tvl=%s whales=%s flow=%s sentiment=%s conf=%.2f",
            asset, tvl_trend, whale_class, flow_dir, defi_sentiment, confidence,
        )

        return signal

    # ------------------------------------------------------------------
    # Data fetchers (wrapped for gather error handling)
    # ------------------------------------------------------------------

    async def _fetch_tvl_data(self) -> Dict[str, Any]:
        trend, magnitude = await self._llama.get_tvl_trend()
        total_tvl = await self._llama.get_total_tvl()
        return {
            "trend": trend,
            "magnitude": magnitude,
            "total_tvl": total_tvl,
        }

    async def _fetch_stablecoin_data(self) -> Dict[str, Any]:
        direction, change_pct = await self._llama.get_stablecoin_net_flow()
        return {
            "direction": direction,
            "change_pct": change_pct,
        }

    async def _fetch_dex_data(self) -> Optional[Dict[str, Any]]:
        snapshot = await self._llama.get_dex_volumes()
        if snapshot is None:
            return None
        return {
            "total_24h": snapshot.total_24h,
            "change_1d": snapshot.change_1d,
            "top_protocols": snapshot.protocols[:5],
        }

    async def _fetch_whale_data(self) -> Dict[str, Any]:
        classification, meta = await self._etherscan.classify_whale_activity()
        return {"classification": classification, **meta}

    async def _fetch_exchange_flow_data(self) -> Dict[str, Any]:
        flow = await self._etherscan.get_exchange_flow()
        return {
            "direction": flow.direction,
            "net_flow_eth": flow.net_flow_eth,
            "total_inflow_eth": flow.total_inflow_eth,
            "total_outflow_eth": flow.total_outflow_eth,
            "inflow_count": flow.inflow_count,
            "outflow_count": flow.outflow_count,
            "top_exchanges": flow.top_exchanges,
        }

    async def _fetch_gas_data(self) -> Dict[str, Any]:
        level, meta = await self._etherscan.get_gas_trend()
        return {"level": level, **meta}

    # ------------------------------------------------------------------
    # Signal interpretation
    # ------------------------------------------------------------------

    def _interpret_tvl(
        self, data: Optional[Dict]
    ) -> tuple[str, float, Dict[str, Any]]:
        """Interpret TVL data into a trend signal."""
        if data is None:
            return "stable", 0.0, {"status": "unavailable"}

        trend = data.get("trend", "stable")
        magnitude = abs(data.get("magnitude", 0))

        # Confidence scales with how decisive the trend is
        if magnitude > 5.0:
            conf = 0.9
        elif magnitude > 2.0:
            conf = 0.7
        else:
            conf = 0.4

        return trend, conf, data

    def _interpret_stablecoins(
        self, data: Optional[Dict]
    ) -> tuple[str, float, Dict[str, Any]]:
        """Interpret stablecoin flow data."""
        if data is None:
            return "balanced", 0.0, {"status": "unavailable"}

        direction = data.get("direction", "balanced")
        change = abs(data.get("change_pct", 0))

        if change > 3.0:
            conf = 0.85
        elif change > 1.0:
            conf = 0.6
        else:
            conf = 0.3

        return direction, conf, data

    def _interpret_whales(
        self, data: Optional[Dict]
    ) -> tuple[str, float, Dict[str, Any]]:
        """Interpret whale activity classification."""
        if data is None:
            return "neutral", 0.0, {"status": "unavailable"}

        classification = data.get("classification", "neutral")
        total = data.get("total_transfers", 0)

        # More transfers = higher confidence in the classification
        if total >= 20:
            conf = 0.8
        elif total >= 5:
            conf = 0.5
        else:
            conf = 0.2

        return classification, conf, data

    def _interpret_exchange_flow(
        self, data: Optional[Dict]
    ) -> tuple[str, float, Dict[str, Any]]:
        """Interpret exchange flow data."""
        if data is None:
            return "balanced", 0.0, {"status": "unavailable"}

        direction = data.get("direction", "balanced")
        net = abs(data.get("net_flow_eth", 0))

        if net > 500:
            conf = 0.8
        elif net > 100:
            conf = 0.6
        else:
            conf = 0.3

        return direction, conf, data

    def _interpret_gas(
        self, data: Optional[Dict]
    ) -> tuple[str, float, Dict[str, Any]]:
        """Interpret gas price level."""
        if data is None:
            return "unknown", 0.0, {"status": "unavailable"}

        level = data.get("level", "unknown")
        # Gas data is always fairly reliable when available
        conf = 0.7 if level != "unknown" else 0.0

        return level, conf, data

    def _interpret_dex_volume(
        self, data: Optional[Dict]
    ) -> tuple[str, float, Dict[str, Any]]:
        """Interpret DEX volume trend."""
        if data is None:
            return "stable", 0.0, {"status": "unavailable"}

        change = data.get("change_1d")
        if change is None:
            return "stable", 0.3, data

        if change > 10:
            return "rising", 0.7, data
        elif change < -10:
            return "falling", 0.7, data
        else:
            return "stable", 0.5, data

    # ------------------------------------------------------------------
    # Composite sentiment
    # ------------------------------------------------------------------

    def _compute_defi_sentiment(
        self,
        tvl_trend: str,
        stable_direction: str,
        dex_trend: str,
        gas_level: str,
    ) -> str:
        """Derive an overall DeFi sentiment from component signals.

        Scoring: each component votes bullish (+1), bearish (-1), or
        neutral (0), weighted by importance.
        """
        score = 0.0

        # TVL trend (weight: 0.35)
        tvl_map = {"rising": 1.0, "falling": -1.0, "stable": 0.0}
        score += tvl_map.get(tvl_trend, 0.0) * 0.35

        # Stablecoin flow (weight: 0.30)
        stable_map = {"inflow": 1.0, "outflow": -1.0, "balanced": 0.0}
        score += stable_map.get(stable_direction, 0.0) * 0.30

        # DEX volume (weight: 0.20)
        dex_map = {"rising": 1.0, "falling": -1.0, "stable": 0.0}
        score += dex_map.get(dex_trend, 0.0) * 0.20

        # Gas (weight: 0.15) -- high gas = active market (mildly bullish)
        gas_map = {"high": 0.5, "moderate": 0.0, "low": -0.3, "unknown": 0.0}
        score += gas_map.get(gas_level, 0.0) * 0.15

        if score > 0.2:
            return "bullish"
        elif score < -0.2:
            return "bearish"
        else:
            return "neutral"

    def _compute_confidence(self, component_confs: Dict[str, float]) -> float:
        """Compute weighted composite confidence from component confidences.

        Components that returned no data (confidence=0) are excluded from
        the weighted average so they don't dilute the score.
        """
        total_weight = 0.0
        weighted_sum = 0.0

        for component, conf in component_confs.items():
            if conf <= 0:
                continue  # skip unavailable components
            weight = _COMPONENT_WEIGHTS.get(component, 0.1)
            weighted_sum += conf * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        return min(1.0, weighted_sum / total_weight)
