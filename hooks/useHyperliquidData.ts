"use client";

import { useQuery } from "@tanstack/react-query";

export interface HLPosition {
  coin: string;
  size: number;
  entryPx: number;
  unrealizedPnl: number;
  leverage: number;
}

export interface SpotBalance {
  coin: string;
  total: number;
  hold: number;
}

export interface HyperliquidData {
  equity: number;
  availableBalance: number;
  marginUsed: number;
  positions: HLPosition[];
  spotBalances: SpotBalance[];
  portfolioValue: number; // perps equity + spot USDC value
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
  // Fetch perps and spot in parallel
  const [perpsRes, spotRes] = await Promise.all([
    fetch("https://api.hyperliquid.xyz/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "clearinghouseState", user: address }),
    }),
    fetch("https://api.hyperliquid.xyz/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "spotClearinghouseState", user: address }),
    }),
  ]);

  if (!perpsRes.ok) {
    throw new Error(`Hyperliquid API HTTP ${perpsRes.status}`);
  }

  const [perpsData, spotData] = await Promise.all([
    perpsRes.json(),
    spotRes.ok ? spotRes.json() : { balances: [] },
  ]);

  const positions: HLPosition[] = (perpsData.assetPositions || [])
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

  // Parse spot balances
  const spotBalances: SpotBalance[] = (spotData.balances || [])
    .map((b: Record<string, string>) => ({
      coin: b.coin || "?",
      total: parseFloat(b.total || "0"),
      hold: parseFloat(b.hold || "0"),
    }))
    .filter((b: SpotBalance) => b.total > 0);

  // Compute total spot USD value (USDC, USDT0, USDE, USDH are all ~$1)
  const stableCoins = ["USDC", "USDT", "USDT0", "USDE", "USDH", "DAI"];
  const spotUsdValue = spotBalances.reduce((sum: number, b: SpotBalance) => {
    if (stableCoins.includes(b.coin.toUpperCase())) return sum + b.total;
    return sum; // non-stable spot tokens would need price lookup — skip for now
  }, 0);

  const perpsEquity = parseFloat(perpsData.marginSummary?.accountValue || "0");
  const portfolioValue = perpsEquity + spotUsdValue;

  return {
    equity: perpsEquity,
    availableBalance: parseFloat(perpsData.withdrawable || "0") + spotUsdValue,
    marginUsed: parseFloat(perpsData.marginSummary?.totalMarginUsed || "0"),
    positions,
    spotBalances,
    portfolioValue,
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
