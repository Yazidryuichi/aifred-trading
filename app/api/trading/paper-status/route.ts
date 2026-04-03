import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const RAILWAY_URL = process.env.RAILWAY_BACKEND_URL;

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
    // Use /health as primary source of truth (works in both paper and live mode)
    const healthRes = await fetch(`${RAILWAY_URL}/health`, {
      signal: AbortSignal.timeout(10000),
    });

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
      portfolioValue: 10.80,
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
