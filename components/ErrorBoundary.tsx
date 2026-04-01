"use client";

import { Component, type ReactNode } from "react";

export class ErrorBoundary extends Component<
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
        <div className="min-h-screen bg-[#06060a] flex items-center justify-center p-8">
          <div className="max-w-lg text-center">
            <h1 className="text-2xl font-bold text-white mb-4">
              AIFred encountered an error
            </h1>
            <p className="text-red-400 text-sm font-mono mb-4 p-4 bg-red-500/10 rounded-lg border border-red-500/20 text-left whitespace-pre-wrap">
              {this.state.error.message}
            </p>
            <button
              onClick={() => {
                localStorage.clear();
                window.location.reload();
              }}
              className="px-6 py-3 bg-emerald-500 text-black font-semibold rounded-lg hover:bg-emerald-400 transition-all"
            >
              Clear Data & Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
