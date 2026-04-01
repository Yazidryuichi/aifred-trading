"use client";

import { Component, type ReactNode, Suspense, lazy } from "react";

// Error boundary
class ArenaErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen bg-[#06060a] flex items-center justify-center">
          <div className="text-center p-8">
            <p className="text-zinc-400 mb-2">Arena render error:</p>
            <p className="text-red-400 text-xs font-mono mb-4">
              {this.state.error.message}
            </p>
            <button
              onClick={() => this.setState({ error: null })}
              className="px-4 py-2 bg-amber-500 text-black rounded-lg text-sm font-bold"
            >
              Retry
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

const ArenaPanel = lazy(() => import("@/components/trading/ArenaPanel"));

function ArenaLoading() {
  return (
    <div className="min-h-screen bg-[#06060a] flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="w-10 h-10 border-2 border-amber-500/30 border-t-amber-500 rounded-full animate-spin" />
        <span
          className="text-zinc-500 text-sm tracking-[0.3em]"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          LOADING ARENA...
        </span>
      </div>
    </div>
  );
}

export default function ArenaPage() {
  return (
    <ArenaErrorBoundary>
      <Suspense fallback={<ArenaLoading />}>
        <ArenaPanel />
      </Suspense>
    </ArenaErrorBoundary>
  );
}
