/**
 * tests/components/AccountSummaryBar.test.tsx
 *
 * Basic render tests for the AccountSummaryBar component.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AccountSummaryBar } from "@/components/AccountSummaryBar";

// Mock react-query to return controlled data
vi.mock("@tanstack/react-query", () => ({
  useQuery: vi.fn(({ queryKey }: { queryKey: string[] }) => {
    if (queryKey[0] === "performance") {
      return {
        data: {
          summary: { currentEquity: 10500, totalPnl: 500, openPositions: 2 },
          openPositions: [
            { size: 0.01, entry_price: 67000 },
            { size: 0.5, entry_price: 3500 },
          ],
          maxPositions: 5,
          regime: "bull",
        },
        isLoading: false,
        error: null,
      };
    }
    if (queryKey[0] === "system-health") {
      return {
        data: {
          status: "running",
          kill_switch_active: false,
          components: [
            { name: "Hyperliquid Testnet", status: "healthy" },
          ],
        },
        isLoading: false,
        error: null,
      };
    }
    return { data: null, isLoading: false, error: null };
  }),
}));

describe("AccountSummaryBar", () => {
  it("renders without crashing", () => {
    render(<AccountSummaryBar />);
    // Should render something
    expect(screen.getByText("Hyperliquid")).toBeInTheDocument();
  });

  it("displays the balance from mock data", () => {
    render(<AccountSummaryBar />);
    expect(screen.getByText("$10500.00")).toBeInTheDocument();
  });

  it("displays the total PnL", () => {
    render(<AccountSummaryBar />);
    expect(screen.getByText(/\+\$500\.00/)).toBeInTheDocument();
  });

  it("shows Hyperliquid branding", () => {
    render(<AccountSummaryBar />);
    expect(screen.getByText("Hyperliquid")).toBeInTheDocument();
  });

  it("shows bot status as RUNNING", () => {
    render(<AccountSummaryBar />);
    expect(screen.getByText("RUNNING")).toBeInTheDocument();
  });

  it("shows regime information", () => {
    render(<AccountSummaryBar />);
    expect(screen.getByText("bull")).toBeInTheDocument();
  });
});
