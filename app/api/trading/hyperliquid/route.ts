import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const HL_ADDRESS =
  process.env.NEXT_PUBLIC_HYPERLIQUID_ADDRESS ||
  process.env.HYPERLIQUID_ADDRESS ||
  "0xbec07623d9c8209E7F80dC7350b3aA0ECBdCb510";

export async function GET() {
  try {
    const [perpsRes, spotRes] = await Promise.all([
      fetch("https://api.hyperliquid.xyz/info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "clearinghouseState", user: HL_ADDRESS }),
        signal: AbortSignal.timeout(8000),
      }),
      fetch("https://api.hyperliquid.xyz/info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "spotClearinghouseState", user: HL_ADDRESS }),
        signal: AbortSignal.timeout(8000),
      }),
    ]);

    const [perpsData, spotData] = await Promise.all([
      perpsRes.ok ? perpsRes.json() : { marginSummary: {}, assetPositions: [] },
      spotRes.ok ? spotRes.json() : { balances: [] },
    ]);

    // Parse positions
    const positions = (perpsData.assetPositions || [])
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
    const stableCoins = ["USDC", "USDT", "USDT0", "USDE", "USDH", "DAI"];
    const spotBalances = (spotData.balances || [])
      .map((b: Record<string, string>) => ({
        coin: b.coin || "?",
        total: parseFloat(b.total || "0"),
        hold: parseFloat(b.hold || "0"),
      }))
      .filter((b: { total: number }) => b.total > 0);

    const spotUsdValue = spotBalances.reduce(
      (sum: number, b: { coin: string; total: number }) =>
        stableCoins.includes(b.coin.toUpperCase()) ? sum + b.total : sum,
      0,
    );

    const perpsEquity = parseFloat(perpsData.marginSummary?.accountValue || "0");
    const portfolioValue = perpsEquity + spotUsdValue;

    return NextResponse.json({
      equity: perpsEquity,
      availableBalance: parseFloat(perpsData.withdrawable || "0") + spotUsdValue,
      marginUsed: parseFloat(perpsData.marginSummary?.totalMarginUsed || "0"),
      positions,
      spotBalances,
      portfolioValue,
      connected: true,
      address: HL_ADDRESS,
    });
  } catch (error) {
    console.error("Hyperliquid proxy error:", error);
    return NextResponse.json(
      { connected: false, error: "Failed to fetch Hyperliquid data" },
      { status: 502 },
    );
  }
}
