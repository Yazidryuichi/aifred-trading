"use client";

import { useAccount } from "wagmi";
import { useHyperliquidData } from "./useHyperliquidData";

/**
 * Wraps useHyperliquidData with wagmi wallet address.
 * Use this ONLY inside Web3Provider (i.e. components rendered as children of layout).
 * For components outside Web3Provider (like TradingModeBanner), use useHyperliquidData directly.
 */
export function useHyperliquidWithWallet() {
  const { address, isConnected } = useAccount();
  return useHyperliquidData(isConnected ? address : undefined);
}
