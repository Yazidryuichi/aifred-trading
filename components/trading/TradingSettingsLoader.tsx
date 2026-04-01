"use client";

import dynamic from "next/dynamic";

const TradingSettings = dynamic(
  () => import("@/components/trading/TradingSettings"),
  {
    ssr: false,
    loading: () => (
      <div className="min-h-screen bg-[#06060a] flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-emerald-500/30 border-t-emerald-500 rounded-full animate-spin" />
          <span className="text-zinc-500 text-sm font-mono tracking-wider">
            LOADING SETTINGS...
          </span>
        </div>
      </div>
    ),
  }
);

export function TradingSettingsLoader() {
  return <TradingSettings />;
}
