"""On-chain data analysis for the AI trading bot.

Integrates DeFiLlama (TVL, stablecoin flows, DEX volumes, yields) and
Etherscan (whale tracking, exchange flows, gas trends) into unified
on-chain trading signals."""

from src.analysis.onchain.onchain_aggregator import OnChainAggregator, OnChainSignal

__all__ = ["OnChainAggregator", "OnChainSignal"]
