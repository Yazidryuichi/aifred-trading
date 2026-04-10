import { NextResponse } from "next/server";
import { readFileSync, existsSync } from "fs";
import { join } from "path";

export const dynamic = "force-dynamic";

const RAILWAY_BACKEND_URL = process.env.RAILWAY_BACKEND_URL;

// ---------------------------------------------------------------------------
// Helper: fetch from Railway with timeout
// ---------------------------------------------------------------------------

async function fetchFromRailway(): Promise<Record<string, unknown> | null> {
  if (!RAILWAY_BACKEND_URL) return null;

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);

    const res = await fetch(`${RAILWAY_BACKEND_URL}/performance`, {
      signal: controller.signal,
      headers: { Accept: "application/json" },
    });
    clearTimeout(timeout);

    if (!res.ok) return null;
    return (await res.json()) as Record<string, unknown>;
  } catch {
    // Railway unreachable — fall through to local data
    return null;
  }
}

export async function GET() {
  try {
    const defaultData = {
      summary: {
        totalPnl: 0, winRate: 0, totalTrades: 0, openPositions: 0,
        avgConfidence: 0, signalCount: 0, activeStrategies: 0,
      },
      byAsset: [],
      byStrategy: [],
      recentTrades: [],
      equity: [],
      signals: [],
    };

    // --- Try Railway first ---
    const railwayData = await fetchFromRailway();
    if (railwayData) {
      return NextResponse.json({ ...defaultData, ...railwayData, source: "railway" });
    }

    // --- Fallback: local static JSON ---
    const jsonPath = join(process.cwd(), "data", "trading-data.json");

    if (!existsSync(jsonPath)) {
      return NextResponse.json({ ...defaultData, source: "local" });
    }

    const raw = readFileSync(jsonPath, "utf-8");
    const data = JSON.parse(raw);

    // Merge with defaults to ensure all fields exist
    return NextResponse.json({ ...defaultData, ...data, source: "local" });
  } catch (error) {
    console.error("Trading API error:", error);
    return NextResponse.json(
      { error: "Failed to load trading data" },
      { status: 500 }
    );
  }
}
