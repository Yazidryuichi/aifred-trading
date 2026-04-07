import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const RAILWAY_URL = process.env.RAILWAY_BACKEND_URL;
const HL_INFO = "https://api.hyperliquid.xyz/info";

async function getHyperliquidBalance(): Promise<number> {
  const address =
    process.env.HYPERLIQUID_WALLET_ADDRESS ||
    process.env.HYPERLIQUID_ADDRESS ||
    process.env.NEXT_PUBLIC_HYPERLIQUID_ADDRESS ||
    "";
  if (!address) return 0;

  try {
    const [perpsRes, spotRes] = await Promise.all([
      fetch(HL_INFO, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "clearinghouseState", user: address }),
        signal: AbortSignal.timeout(5000),
      }),
      fetch(HL_INFO, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "spotClearinghouseState", user: address }),
        signal: AbortSignal.timeout(5000),
      }),
    ]);

    let total = 0;
    if (perpsRes.ok) {
      const perps = await perpsRes.json();
      total += parseFloat(perps?.marginSummary?.accountValue || "0");
    }
    if (spotRes.ok) {
      const spot = await spotRes.json();
      const usdcBalance = spot?.balances?.find(
        (b: { coin: string }) => b.coin === "USDC"
      );
      total += parseFloat(usdcBalance?.total || "0");
    }
    return Math.round(total * 100) / 100;
  } catch {
    return 0;
  }
}

export async function GET() {
  if (!RAILWAY_URL) {
    return NextResponse.json({
      running: false,
      not_configured: true,
      source: "railway",
      error: "Python backend not connected. Trading via API routes.",
    });
  }

  try {
    const [healthRes, portfolioValue] = await Promise.all([
      fetch(`${RAILWAY_URL}/health`, {
        signal: AbortSignal.timeout(10000),
      }),
      getHyperliquidBalance(),
    ]);

    if (!healthRes.ok) {
      return NextResponse.json({
        running: false,
        source: "railway",
        error: `Railway health check returned HTTP ${healthRes.status}`,
      });
    }

    const health = await healthRes.json();

    return NextResponse.json({
      running: health.healthy ?? false,
      source: "railway",
      railwayUrl: RAILWAY_URL,
      uptime: health.uptime || "unknown",
      scanCount: health.scan_count || 0,
      assets: ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
      scanInterval: 24,
      signalsGenerated: 0,
      portfolioValue,
      lastPrices: {},
      agentStatus: health.checks || {},
      lastScanTime: health.timestamp || null,
    });
  } catch {
    return NextResponse.json({
      running: false,
      source: "railway",
      error: "Railway backend unreachable",
    });
  }
}
