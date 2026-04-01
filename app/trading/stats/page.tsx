import { ErrorBoundary } from "@/components/ErrorBoundary";
import { TradingStats } from "@/components/trading/TradingStats";

export const metadata = {
  title: "Trading Stats — AIFred",
  description: "Detailed trading performance statistics and trade history.",
};

export default function StatsPage() {
  return (
    <ErrorBoundary>
      <div
        className="min-h-screen bg-[#06060a] text-white"
        style={{ fontFamily: "Outfit, sans-serif" }}
      >
        {/* Header */}
        <header className="border-b border-white/[0.06] px-4 md:px-6 py-3 md:py-4">
          <div className="max-w-[1600px] mx-auto flex items-center justify-between">
            <div className="flex items-center gap-3">
              <a
                href="/trading"
                className="text-zinc-500 hover:text-zinc-300 transition-colors text-xs tracking-wider uppercase"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                &larr; Dashboard
              </a>
              <span className="text-zinc-700">/</span>
              <h1
                className="text-sm font-bold text-white tracking-wider uppercase"
                style={{ fontFamily: "Outfit, sans-serif" }}
              >
                Trading Stats
              </h1>
            </div>
            <div
              className="text-[10px] text-zinc-600"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              AIFred Analytics
            </div>
          </div>
        </header>

        {/* Content */}
        <main className="max-w-[1600px] mx-auto px-4 md:px-6 py-6">
          <TradingStats />
        </main>
      </div>
    </ErrorBoundary>
  );
}
