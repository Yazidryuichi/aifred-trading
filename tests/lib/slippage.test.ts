/**
 * tests/lib/slippage.test.ts
 *
 * Tests for the slippage estimation model inside execute-trade.ts.
 * Since estimateSlippage is not exported, we test it indirectly through
 * executeTrade's paper execution path. We verify the model's properties:
 * - BTC has a specific base rate
 * - Output is always positive
 * - Output stays within reasonable bounds
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

// Re-use the same mocks as execute-trade tests
vi.mock("@/lib/strategy-learning", () => ({
  loadStats: vi.fn(() => []),
  selectStrategy: vi.fn(() => "Test Strategy"),
  computeConfidence: vi.fn(() => 80),
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

vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("no network")));

import { executeTrade } from "@/lib/execute-trade";

describe("slippage model (tested via paper execution)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("execution price is always positive", async () => {
    for (const symbol of ["BTC/USDT", "ETH/USDT", "EUR/USD", "AAPL"]) {
      const result = await executeTrade({
        symbol,
        side: "LONG",
        quantity: 1,
        orderType: "market",
      });
      expect(result.data.executionPrice).toBeGreaterThan(0);
    }
  });

  it("slippage keeps execution price within 50 bps of base price", async () => {
    // Run multiple times to account for random noise in slippage model
    for (let i = 0; i < 10; i++) {
      const result = await executeTrade({
        symbol: "BTC/USDT",
        side: "LONG",
        quantity: 0.01,
        orderType: "market",
      });

      const ep = result.data.executionPrice as number;
      const basePrice = 67245.5; // MOCK_PRICES["BTC/USDT"]
      const deviation = Math.abs(ep - basePrice) / basePrice;
      // 50 bps = 0.005 = 0.5%
      expect(deviation).toBeLessThan(0.005);
    }
  });

  it("limit orders do not apply slippage", async () => {
    const result = await executeTrade({
      symbol: "BTC/USDT",
      side: "LONG",
      quantity: 0.01,
      orderType: "limit",
      price: 65000,
    });

    // Limit orders execute at exactly the base price
    expect(result.data.executionPrice).toBe(65000);
  });

  it("forex pairs use a lower base rate than crypto (smaller slippage)", async () => {
    // Collect slippage measurements for BTC and EUR/USD
    const btcSlippages: number[] = [];
    const fxSlippages: number[] = [];

    for (let i = 0; i < 20; i++) {
      const btcResult = await executeTrade({
        symbol: "BTC/USDT",
        side: "LONG",
        quantity: 1,
        orderType: "market",
      });
      const btcEp = btcResult.data.executionPrice as number;
      btcSlippages.push(Math.abs(btcEp - 67245.5) / 67245.5);

      const fxResult = await executeTrade({
        symbol: "EUR/USD",
        side: "LONG",
        quantity: 1,
        orderType: "market",
      });
      const fxEp = fxResult.data.executionPrice as number;
      fxSlippages.push(Math.abs(fxEp - 1.0842) / 1.0842);
    }

    const avgBtcSlippage = btcSlippages.reduce((a, b) => a + b, 0) / btcSlippages.length;
    const avgFxSlippage = fxSlippages.reduce((a, b) => a + b, 0) / fxSlippages.length;

    // BTC base rate is 3 bps, forex is 2 bps — so BTC should have higher avg slippage
    expect(avgBtcSlippage).toBeGreaterThan(avgFxSlippage);
  });
});
