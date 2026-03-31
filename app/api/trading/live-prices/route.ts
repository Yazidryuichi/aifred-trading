import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

// ---------------------------------------------------------------------------
// In-memory cache (5-second TTL)
// ---------------------------------------------------------------------------

interface PriceCache {
  data: Record<string, string> | null;
  timestamp: number;
}

let priceCache: PriceCache = { data: null, timestamp: 0 };

const CACHE_TTL_MS = 5000; // 5 seconds

// ---------------------------------------------------------------------------
// Fetch prices from Hyperliquid mainnet
// ---------------------------------------------------------------------------

async function fetchAllMids(): Promise<Record<string, string>> {
  const now = Date.now();

  // Return cached data if still fresh
  if (priceCache.data && now - priceCache.timestamp < CACHE_TTL_MS) {
    return priceCache.data;
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 8000);

  try {
    const res = await fetch("https://api.hyperliquid.xyz/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "allMids" }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!res.ok) {
      throw new Error(`Hyperliquid API returned HTTP ${res.status}`);
    }

    const data = await res.json();
    priceCache = { data, timestamp: Date.now() };
    return data;
  } catch (error) {
    clearTimeout(timeoutId);
    // If we have stale cache, return it rather than failing
    if (priceCache.data) {
      return priceCache.data;
    }
    throw error;
  }
}

// ---------------------------------------------------------------------------
// GET /api/trading/live-prices
// ---------------------------------------------------------------------------

export async function GET() {
  try {
    const allMids = await fetchAllMids();

    // Extract key prices (Hyperliquid uses symbols like "BTC", "ETH", etc.)
    const btcPrice = allMids["BTC"] ? parseFloat(allMids["BTC"]) : null;
    const ethPrice = allMids["ETH"] ? parseFloat(allMids["ETH"]) : null;
    const solPrice = allMids["SOL"] ? parseFloat(allMids["SOL"]) : null;

    const prices: Record<string, number | null> = {
      BTC: btcPrice,
      ETH: ethPrice,
      SOL: solPrice,
    };

    // Include a broader set of popular assets if available
    const extraAssets = [
      "DOGE", "XRP", "ADA", "AVAX", "LINK", "MATIC", "DOT",
      "UNI", "AAVE", "ARB", "OP", "SUI", "APT",
    ];
    for (const asset of extraAssets) {
      if (allMids[asset]) {
        prices[asset] = parseFloat(allMids[asset]);
      }
    }

    return NextResponse.json({
      prices,
      source: "hyperliquid-mainnet",
      cached: Date.now() - priceCache.timestamp < 100 ? false : true,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Live prices API error:", error);
    return NextResponse.json(
      {
        error: "Failed to fetch live prices",
        prices: { BTC: null, ETH: null, SOL: null },
        source: "unavailable",
        timestamp: new Date().toISOString(),
      },
      { status: 502 },
    );
  }
}
