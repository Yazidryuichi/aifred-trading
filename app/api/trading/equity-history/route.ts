import { NextResponse } from "next/server";
import { join } from "path";
import { readJsonWithFallback, lockedReadModifyWrite } from "@/lib/file-lock";

export const dynamic = "force-dynamic";

const EQUITY_FILE = join("/tmp", "aifred-data", "equity-snapshots.json");
const TRADING_DATA = join(process.cwd(), "data", "trading-data.json");
const MAX_ENTRIES = 10_000;
const MAX_BODY_BYTES = 1024; // 1 KB — a single snapshot is tiny

interface EquitySnapshot {
  timestamp: string;
  equity: number;
  source: "hyperliquid" | "demo";
}

// ---------------------------------------------------------------------------
// GET — return equity history for charting
// ---------------------------------------------------------------------------
export async function GET() {
  try {
    // Try the live snapshots file first
    const snapshots = readJsonWithFallback<EquitySnapshot[]>(
      [EQUITY_FILE],
      [],
    );

    if (snapshots.length > 0) {
      return NextResponse.json({
        success: true,
        data: snapshots,
        count: snapshots.length,
        source: "snapshots",
      });
    }

    // Fallback: derive from equityCurve in trading-data.json
    const tradingData = readJsonWithFallback<{
      equityCurve?: { date: string; value: number }[];
    }>([TRADING_DATA], { equityCurve: [] });

    const fallbackSnapshots: EquitySnapshot[] = (
      tradingData.equityCurve ?? []
    ).map((point) => ({
      timestamp: point.date === "Start" ? new Date(0).toISOString() : point.date,
      equity: point.value,
      source: "hyperliquid" as const,
    }));

    return NextResponse.json({
      success: true,
      data: fallbackSnapshots,
      count: fallbackSnapshots.length,
      source: "trading-data-fallback",
    });
  } catch (error) {
    console.error("Equity history GET error:", error);
    return NextResponse.json(
      { success: false, error: "Failed to load equity history" },
      { status: 500 },
    );
  }
}

// ---------------------------------------------------------------------------
// POST — record a new equity snapshot (called by cron / autoscan)
// ---------------------------------------------------------------------------
export async function POST(request: Request) {
  try {
    // Body size guard
    const contentLength = parseInt(
      request.headers.get("content-length") ?? "0",
      10,
    );
    if (contentLength > MAX_BODY_BYTES) {
      return NextResponse.json(
        { success: false, error: "Request body too large" },
        { status: 413 },
      );
    }

    const body = await request.json();
    const { equity, source } = body as {
      equity?: number;
      source?: string;
    };

    if (typeof equity !== "number" || !isFinite(equity)) {
      return NextResponse.json(
        { success: false, error: "equity must be a finite number" },
        { status: 400 },
      );
    }

    const validSource =
      source === "demo" ? "demo" : ("hyperliquid" as const);

    const snapshot: EquitySnapshot = {
      timestamp: new Date().toISOString(),
      equity,
      source: validSource,
    };

    const updated = await lockedReadModifyWrite<EquitySnapshot[]>(
      EQUITY_FILE,
      (current) => {
        const list = Array.isArray(current) ? current : [];
        list.push(snapshot);
        // Rolling cap
        if (list.length > MAX_ENTRIES) {
          return list.slice(list.length - MAX_ENTRIES);
        }
        return list;
      },
    );

    return NextResponse.json({
      success: true,
      snapshot,
      totalSnapshots: updated.length,
    });
  } catch (error) {
    console.error("Equity history POST error:", error);
    return NextResponse.json(
      { success: false, error: "Failed to record snapshot" },
      { status: 500 },
    );
  }
}
