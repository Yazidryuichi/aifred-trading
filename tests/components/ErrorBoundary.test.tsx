/**
 * tests/components/ErrorBoundary.test.tsx
 *
 * Tests for the ErrorBoundary component — must catch errors and show recovery UI.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { ErrorBoundary } from "@/components/ErrorBoundary";

// Suppress React error boundary console.error noise during tests
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
});

function ThrowingChild({ message }: { message: string }) {
  throw new Error(message);
}

function GoodChild() {
  return <div>Everything is fine</div>;
}

describe("ErrorBoundary", () => {
  it("renders children when there is no error", () => {
    render(
      <ErrorBoundary>
        <GoodChild />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Everything is fine")).toBeInTheDocument();
  });

  it("catches errors and displays the error message", () => {
    render(
      <ErrorBoundary>
        <ThrowingChild message="Something went wrong!" />
      </ErrorBoundary>,
    );
    expect(screen.getByText("AIFred encountered an error")).toBeInTheDocument();
    expect(screen.getByText("Something went wrong!")).toBeInTheDocument();
  });

  it("shows a reload button when an error occurs", () => {
    render(
      <ErrorBoundary>
        <ThrowingChild message="Crash" />
      </ErrorBoundary>,
    );
    const button = screen.getByRole("button", { name: /clear data & reload/i });
    expect(button).toBeInTheDocument();
  });
});
