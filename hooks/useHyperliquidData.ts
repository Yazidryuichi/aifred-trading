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
  portfolioValue: number;
  connected: boolean;
}

/**
 * Fetch Hyperliquid data via server-side proxy (bulletproof — no CORS issues).
 * Falls back to direct Hyperliquid API if proxy fails.
 */
async function fetchHyperliquidData(): Promise<HyperliquidData> {
  // Primary: server-side proxy (handles CORS, env vars, address resolution)
  try {
    const res = await fetch("/api/trading/hyperliquid", {
      signal: AbortSignal.timeout(10000),
    });
    if (res.ok) {
      const data = await res.json();
      if (data.connected) {
        return {
          equity: data.equity ?? 0,
          availableBalance: data.availableBalance ?? 0,
          marginUsed: data.marginUsed ?? 0,
          positions: data.positions ?? [],
          spotBalances: data.spotBalances ?? [],
          portfolioValue: data.portfolioValue ?? 0,
          connected: true,
        };
      }
    }
  } catch {
    // Proxy failed — try direct
  }

  // Fallback: direct Hyperliquid API (may fail on some deployments due to CORS)
  const address = "0xbec07623d9c8209E7F80dC7350b3aA0ECBdCb510";
  const [perpsRes, spotRes] = await Promise.all([
    fetch("https://api.hyperliquid.xyz/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "clearinghouseState", user: address }),
      signal: AbortSignal.timeout(8000),
    }),
    fetch("https://api.hyperliquid.xyz/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "spotClearinghouseState", user: address }),
      signal: AbortSignal.timeout(8000),
    }),
  ]);

  if (!perpsRes.ok) throw new Error(`Hyperliquid API HTTP ${perpsRes.status}`);

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

  const stableCoins = ["USDC", "USDT", "USDT0", "USDE", "USDH", "DAI"];
  const spotBalances: SpotBalance[] = (spotData.balances || [])
    .map((b: Record<string, string>) => ({
      coin: b.coin || "?",
      total: parseFloat(b.total || "0"),
      hold: parseFloat(b.hold || "0"),
    }))
    .filter((b: SpotBalance) => b.total > 0);

  const spotUsdValue = spotBalances.reduce(
    (sum: number, b: SpotBalance) =>
      stableCoins.includes(b.coin.toUpperCase()) ? sum + b.total : sum,
    0,
  );

  const perpsEquity = parseFloat(perpsData.marginSummary?.accountValue || "0");

  return {
    equity: perpsEquity,
    availableBalance: parseFloat(perpsData.withdrawable || "0") + spotUsdValue,
    marginUsed: parseFloat(perpsData.marginSummary?.totalMarginUsed || "0"),
    positions,
    spotBalances,
    portfolioValue: perpsEquity + spotUsdValue,
    connected: true,
  };
}

/**
 * Shared hook for Hyperliquid exchange data.
 * Uses server-side proxy as primary source (no CORS issues).
 * Auto-refreshes every 12 seconds.
 */
export function useHyperliquidData(_address?: string) {
  const query = useQuery<HyperliquidData>({
    queryKey: ["hyperliquid-data"],
    queryFn: fetchHyperliquidData,
    refetchInterval: 12_000,
    staleTime: 8_000,
    retry: 2,
  });

  return {
    data: query.data ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    hasAddress: true,
    address: "0xbec07623d9c8209E7F80dC7350b3aA0ECBdCb510",
  };
}
