import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const HYPERLIQUID_ADDRESS =
  process.env.HYPERLIQUID_WALLET_ADDRESS ||
  process.env.HYPERLIQUID_ADDRESS ||
  "";

const MAX_BODY_BYTES = 2048;

// ---------------------------------------------------------------------------
// GET — fetch current positions from Hyperliquid
// ---------------------------------------------------------------------------
export async function GET() {
  if (!HYPERLIQUID_ADDRESS) {
    return NextResponse.json(
      { success: false, error: "HYPERLIQUID_WALLET_ADDRESS not configured" },
      { status: 503 },
    );
  }

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10_000);

    const res = await fetch("https://api.hyperliquid.xyz/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        type: "clearinghouseState",
        user: HYPERLIQUID_ADDRESS,
      }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!res.ok) {
      return NextResponse.json(
        {
          success: false,
          error: `Hyperliquid returned HTTP ${res.status}`,
        },
        { status: 502 },
      );
    }

    const data = await res.json();

    // Extract position summaries from the clearinghouse state
    const assetPositions = data.assetPositions ?? [];
    const positions = assetPositions.map(
      (ap: {
        position: {
          coin: string;
          szi: string;
          entryPx: string;
          positionValue: string;
          unrealizedPnl: string;
          leverage: { value: string; type: string };
          liquidationPx: string | null;
        };
      }) => {
        const p = ap.position;
        const size = parseFloat(p.szi);
        return {
          symbol: p.coin,
          side: size >= 0 ? "LONG" : "SHORT",
          size: Math.abs(size),
          entryPrice: parseFloat(p.entryPx),
          positionValue: parseFloat(p.positionValue),
          unrealizedPnl: parseFloat(p.unrealizedPnl),
          leverage: parseFloat(p.leverage?.value ?? "1"),
          leverageType: p.leverage?.type ?? "cross",
          liquidationPrice: p.liquidationPx
            ? parseFloat(p.liquidationPx)
            : null,
        };
      },
    );

    return NextResponse.json({
      success: true,
      positions,
      marginSummary: data.marginSummary ?? null,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Positions GET error:", error);
    const message =
      error instanceof Error ? error.message : "Failed to fetch positions";
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 },
    );
  }
}

// ---------------------------------------------------------------------------
// POST — close / modify position (placeholder with safety controls)
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
    const { action, symbol, confirmationToken } = body as {
      action?: string;
      symbol?: string;
      confirmationToken?: string;
    };

    // Validate required fields
    if (!action || !symbol) {
      return NextResponse.json(
        { success: false, error: "action and symbol are required" },
        { status: 400 },
      );
    }

    if (action !== "close" && action !== "modify") {
      return NextResponse.json(
        { success: false, error: "action must be 'close' or 'modify'" },
        { status: 400 },
      );
    }

    if (!confirmationToken) {
      return NextResponse.json(
        {
          success: false,
          error: "confirmationToken is required for safety",
        },
        { status: 400 },
      );
    }

    // Placeholder — actual execution deferred to future sprint
    return NextResponse.json(
      {
        success: false,
        error: "Position management coming soon",
        status: 501,
        action,
        symbol,
      },
      { status: 501 },
    );
  } catch (error) {
    console.error("Positions POST error:", error);
    return NextResponse.json(
      { success: false, error: "Failed to process position action" },
      { status: 500 },
    );
  }
}
