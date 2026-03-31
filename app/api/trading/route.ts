import { NextResponse } from "next/server";
import { readFileSync, existsSync } from "fs";
import { join } from "path";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const jsonPath = join(process.cwd(), "data", "trading-data.json");

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

    if (!existsSync(jsonPath)) {
      return NextResponse.json(defaultData);
    }

    const raw = readFileSync(jsonPath, "utf-8");
    const data = JSON.parse(raw);

    // Merge with defaults to ensure all fields exist
    return NextResponse.json({ ...defaultData, ...data });
  } catch (error) {
    console.error("Trading API error:", error);
    return NextResponse.json(
      { error: "Failed to load trading data" },
      { status: 500 }
    );
  }
}
