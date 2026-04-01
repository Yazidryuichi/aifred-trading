/**
 * tests/api/trading.test.ts
 *
 * Tests for the main /api/trading GET endpoint.
 * Since mocking Node built-in `fs` inside Next.js route handlers is unreliable
 * in vitest, we test the actual handler against the real filesystem.
 * This validates the real integration behavior.
 */
import { describe, it, expect } from "vitest";
import { GET } from "@/app/api/trading/route";

describe("GET /api/trading", () => {
  it("returns 200 with valid JSON", async () => {
    const response = await GET();
    expect(response.status).toBe(200);

    const data = await response.json();
    expect(data).toBeDefined();
    expect(typeof data).toBe("object");
  });

  it("response always contains the expected structure shape", async () => {
    const response = await GET();
    const data = await response.json();

    // These keys should always be present (from defaults merge)
    const expectedKeys = ["summary", "byAsset", "byStrategy", "recentTrades", "equity", "signals"];
    for (const key of expectedKeys) {
      expect(data).toHaveProperty(key);
    }
  });

  it("summary contains required financial fields", async () => {
    const response = await GET();
    const data = await response.json();

    expect(data.summary).toBeDefined();
    expect(typeof data.summary.totalPnl).toBe("number");
    expect(typeof data.summary.winRate).toBe("number");
    expect(typeof data.summary.totalTrades).toBe("number");
    expect(typeof data.summary.openPositions).toBe("number");
  });

  it("arrays are always arrays (never null/undefined)", async () => {
    const response = await GET();
    const data = await response.json();

    expect(Array.isArray(data.byAsset)).toBe(true);
    expect(Array.isArray(data.byStrategy)).toBe(true);
    expect(Array.isArray(data.recentTrades)).toBe(true);
    expect(Array.isArray(data.equity)).toBe(true);
    expect(Array.isArray(data.signals)).toBe(true);
  });
});
