import { NextResponse } from "next/server";

export async function GET() {
  const brokers = [];

  // Hyperliquid: check if env vars are set
  if (process.env.HYPERLIQUID_ADDRESS && process.env.HYPERLIQUID_PRIVATE_KEY) {
    brokers.push({
      id: "hyperliquid",
      name: "Hyperliquid",
      connected: true,
    });
  }

  // Binance
  if (process.env.BINANCE_API_KEY && process.env.BINANCE_API_SECRET) {
    brokers.push({
      id: "binance",
      name: "Binance",
      connected: true,
    });
  }

  // Alpaca
  if (process.env.ALPACA_API_KEY && process.env.ALPACA_API_SECRET) {
    brokers.push({
      id: "alpaca",
      name: "Alpaca",
      connected: true,
    });
  }

  return NextResponse.json(brokers);
}
