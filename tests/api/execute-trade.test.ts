/**
 * tests/api/execute-trade.test.ts
 *
 * Tests for the shared executeTrade module (lib/execute-trade.ts).
 * This is the core trade execution logic — paper mode only (no live credentials in tests).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock ccxt — its starknet dependency crashes in jsdom
vi.mock("ccxt", () => ({
  default: {},
  InsufficientFunds: class extends Error {},
  InvalidOrder: class extends Error {},
  AuthenticationError: class extends Error {},
  PermissionDenied: class extends Error {},
  RateLimitExceeded: class extends Error {},
  NetworkError: class extends Error {},
}));

// Mock all heavy dependencies so executeTrade runs without network or filesystem
vi.mock("@/lib/strategy-learning", () => ({
  loadStats: vi.fn(() => [
    { strategy_name: "Momentum Breakout", total_trades: 50, winning_trades: 40, losing_trades: 10, total_pnl: 12000, ema_win_rate: 0.80, avg_confidence: 85, kelly_fraction: 0.03, last_updated: new Date().toISOString() },
  ]),
  selectStrategy: vi.fn(() => "Momentum Breakout"),
  computeConfidence: vi.fn(() => 82),
  recordTradeOutcome: vi.fn(),
}));

vi.mock("@/lib/hmm-regime", () => ({
  detectRegime: vi.fn().mockRejectedValue(new Error("no network")),
  getRegimeAction: vi.fn(() => ({ action: "HOLD", leverage: 0, description: "test" })),
}));

vi.mock("@/lib/technical-indicators", () => ({
  calculateConfirmations: vi.fn(() => ({
    confirmations: [],
    passed: 0,
    required: 7,
    total: 8,
    overallPass: false,
    signalStrength: 0,
  })),
}));

vi.mock("@/lib/file-lock", () => ({
  atomicWriteFile: vi.fn().mockResolvedValue(undefined),
  readJsonWithFallback: vi.fn().mockReturnValue({}),
  lockedReadModifyWrite: vi.fn().mockResolvedValue([]),
}));

vi.mock("fs", async () => {
  const actual = await vi.importActual<typeof import("fs")>("fs");
  return {
    ...actual,
    existsSync: vi.fn().mockReturnValue(false),
    readFileSync: vi.fn().mockReturnValue("{}"),
    mkdirSync: vi.fn(),
  };
});

// Mock fetch for live price lookups
vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("no network")));

import { executeTrade, type ExecuteTradeParams } from "@/lib/execute-trade";

describe("executeTrade — paper mode", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 400 when symbol is missing", async () => {
    const result = await executeTrade({ symbol: "", side: "LONG", quantity: 1, orderType: "market" });
    expect(result.status).toBe(400);
    expect(result.success).toBe(false);
  });

  it("returns 400 when side is invalid", async () => {
    const result = await executeTrade({ symbol: "BTC/USDT", side: "UP" as any, quantity: 1, orderType: "market" });
    expect(result.status).toBe(400);
  });

  it("returns 400 when quantity is zero", async () => {
    // quantity: 0 is falsy, so it hits the "required" check
    const result = await executeTrade({ symbol: "BTC/USDT", side: "LONG", quantity: 0, orderType: "market" });
    expect(result.status).toBe(400);
    expect(result.success).toBe(false);
  });

  it("returns 400 when quantity is negative", async () => {
    const result = await executeTrade({ symbol: "BTC/USDT", side: "LONG", quantity: -1, orderType: "market" });
    expect(result.status).toBe(400);
    expect(result.data.message).toContain("positive");
  });

  it("executes a valid paper trade successfully", async () => {
    const params: ExecuteTradeParams = {
      symbol: "BTC/USDT",
      side: "LONG",
      quantity: 0.01,
      orderType: "market",
    };

    const result = await executeTrade(params);

    expect(result.success).toBe(true);
    expect(result.status).toBe(200);
    expect(result.data.mode).toBe("paper");
    expect(result.data.symbol).toBe("BTC/USDT");
    expect(result.data.side).toBe("LONG");
    expect(result.data.quantity).toBe(0.01);
    expect(result.data.status).toBe("filled");
    expect(result.data.orderId).toBeDefined();
    expect(typeof result.data.executionPrice).toBe("number");
    expect((result.data.executionPrice as number)).toBeGreaterThan(0);
  });

  it("paper trade includes stop loss and take profit", async () => {
    const result = await executeTrade({
      symbol: "ETH/USDT",
      side: "LONG",
      quantity: 0.1,
      orderType: "market",
    });

    expect(result.data.stopLoss).toBeDefined();
    expect(result.data.takeProfit).toBeDefined();
    const ep = result.data.executionPrice as number;
    const sl = result.data.stopLoss as number;
    const tp = result.data.takeProfit as number;
    // For LONG: SL < entry < TP
    expect(sl).toBeLessThan(ep);
    expect(tp).toBeGreaterThan(ep);
  });

  it("SHORT trade has SL above and TP below entry", async () => {
    const result = await executeTrade({
      symbol: "BTC/USDT",
      side: "SHORT",
      quantity: 0.01,
      orderType: "market",
    });

    expect(result.success).toBe(true);
    const ep = result.data.executionPrice as number;
    const sl = result.data.stopLoss as number;
    const tp = result.data.takeProfit as number;
    // For SHORT: TP < entry < SL
    expect(sl).toBeGreaterThan(ep);
    expect(tp).toBeLessThan(ep);
  });

  it("slippage is applied for market orders and execution price differs from base", async () => {
    const result = await executeTrade({
      symbol: "BTC/USDT",
      side: "LONG",
      quantity: 0.01,
      orderType: "market",
    });

    // The mock price for BTC/USDT is 67245.5
    // With slippage the execution price should be slightly different
    const ep = result.data.executionPrice as number;
    expect(ep).toBeGreaterThan(0);
    // Slippage should be small (within 0.5% of base price)
    expect(Math.abs(ep - 67245.5) / 67245.5).toBeLessThan(0.005);
  });

  it("uses provided price over mock price when given", async () => {
    const result = await executeTrade({
      symbol: "BTC/USDT",
      side: "LONG",
      quantity: 0.01,
      orderType: "market",
      price: 50000,
    });

    const ep = result.data.executionPrice as number;
    // Should be near the provided price of 50000, not the mock 67245.5
    expect(Math.abs(ep - 50000)).toBeLessThan(500);
  });

  it("defaults to paper mode when no brokerId provided", async () => {
    const result = await executeTrade({
      symbol: "BTC/USDT",
      side: "LONG",
      quantity: 0.01,
      orderType: "market",
      mode: "live", // requesting live but no brokerId
    });

    expect(result.data.mode).toBe("paper");
  });
});
