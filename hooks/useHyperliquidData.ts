"use client";

import { useQuery } from "@tanstack/react-query";

export interface HLPosition {
  coin: string;
  size: number;
  entryPx: number;
  unrealizedPnl: number;
  leverage: number;
}

export interface HyperliquidData {
  equity: number;
  availableBalance: number;
  marginUsed: number;
  positions: HLPosition[];
  connected: boolean;
}

function getStaticAddress(): string | null {
  // Try env var
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_HYPERLIQUID_ADDRESS) {
    return process.env.NEXT_PUBLIC_HYPERLIQUID_ADDRESS;
  }

  // Try localStorage
  if (typeof window !== "undefined") {
    const stored = localStorage.getItem("hyperliquid_address");
    if (stored) return stored;
  }

  return null;
}

async function fetchHyperliquidState(address: string): Promise<HyperliquidData> {
  const res = await fetch("https://api.hyperliquid.xyz/info", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      type: "clearinghouseState",
      user: address,
    }),
  });

  if (!res.ok) {
    throw new Error(`Hyperliquid API HTTP ${res.status}`);
  }

  const data = await res.json();

  const positions: HLPosition[] = (data.assetPositions || [])
    .filter(
      (p: Record<string, Record<string, string>>) =>
        parseFloat(p.position?.szi || "0") !== 0,
    )
    .map(
      (p: Record<string, Record<string, string | Record<string, string>>>) => ({
        coin: p.position.coin as string,
        size: parseFloat(p.position.szi as string),
        entryPx: parseFloat(p.position.entryPx as string),
        unrealizedPnl: parseFloat(p.position.unrealizedPnl as string),
        leverage: parseFloat(
          typeof p.position.leverage === "object"
            ? (p.position.leverage as Record<string, string>).value || "1"
            : (p.position.leverage as string) || "1",
        ),
      }),
    );

  return {
    equity: parseFloat(data.marginSummary?.accountValue || "0"),
    availableBalance: parseFloat(data.withdrawable || "0"),
    marginUsed: parseFloat(data.marginSummary?.totalMarginUsed || "0"),
    positions,
    connected: true,
  };
}

/**
 * Shared hook for Hyperliquid exchange data.
 * Uses react-query for caching and auto-refresh (12s interval).
 *
 * Address resolution order:
 *   1. Explicit `address` parameter (pass wagmi address from useAccount when inside Web3Provider)
 *   2. NEXT_PUBLIC_HYPERLIQUID_ADDRESS env var
 *   3. localStorage "hyperliquid_address"
 *
 * This hook does NOT import wagmi so it can be used outside WagmiProvider.
 * Components inside Web3Provider should use useHyperliquidWithWallet() instead.
 */
export function useHyperliquidData(address?: string) {
  const resolvedAddress = address || getStaticAddress();

  const query = useQuery<HyperliquidData>({
    queryKey: ["hyperliquid-data", resolvedAddress],
    queryFn: () => {
      if (!resolvedAddress) {
        throw new Error("No Hyperliquid address configured");
      }
      return fetchHyperliquidState(resolvedAddress);
    },
    enabled: !!resolvedAddress,
    refetchInterval: 12_000,
    staleTime: 8_000,
    retry: 2,
  });

  return {
    data: query.data ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    hasAddress: !!resolvedAddress,
    address: resolvedAddress ?? null,
  };
}
