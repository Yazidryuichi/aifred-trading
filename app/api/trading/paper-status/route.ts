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
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);

    const res = await fetch(`${RAILWAY_URL}/status`, {
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!res.ok) {
      return NextResponse.json({
        running: false,
        source: "railway",
        error: `Railway returned HTTP ${res.status}`,
      });
    }

    const data = await res.json();

    // Also fetch health for uptime info
    let uptime = "unknown";
    try {
      const healthRes = await fetch(`${RAILWAY_URL}/health`, {
        signal: AbortSignal.timeout(5000),
      });
      if (healthRes.ok) {
        const health = await healthRes.json();
        uptime = health.uptime || "unknown";
      }
    } catch {
      // ignore
    }

    return NextResponse.json({
      running: data.log_available ?? false,
      source: "railway",
      railwayUrl: RAILWAY_URL,
      uptime,
      ...data,
    });
  } catch {
    return NextResponse.json({
      running: false,
      source: "railway",
      error: "Railway backend unreachable",
    });
  }
}
