"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

interface EquityPoint {
  date: string;
  value: number;
}

export function EquityCurve() {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<ReturnType<typeof import("lightweight-charts").createChart> | null>(null);
  const [activeView, setActiveView] = useState<"equity" | "market">("equity");

  const { data: tradingData } = useQuery({
    queryKey: ["trading-data"],
    queryFn: () => fetch("/api/trading").then((r) => r.json()),
    refetchInterval: 30_000,
  });

  const equityCurve: EquityPoint[] = tradingData?.equityCurve ?? [];

  // Compute stats
  const initialBalance = equityCurve.length > 0 ? equityCurve[0].value : 0;
  const currentEquity = equityCurve.length > 0 ? equityCurve[equityCurve.length - 1].value : 0;
  const pnl = currentEquity - initialBalance;
  const pnlPct = initialBalance > 0 ? (pnl / initialBalance) * 100 : 0;

  useEffect(() => {
    if (!chartRef.current || equityCurve.length === 0) return;

    let disposed = false;

    import("lightweight-charts").then((lc) => {
      if (disposed || !chartRef.current) return;

      // Clean up previous chart
      if (chartInstance.current) {
        chartInstance.current.remove();
        chartInstance.current = null;
      }

      const chart = lc.createChart(chartRef.current, {
        layout: {
          background: { type: lc.ColorType.Solid, color: "transparent" },
          textColor: "#71717a",
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
        },
        grid: {
          vertLines: { color: "rgba(255,255,255,0.03)" },
          horzLines: { color: "rgba(255,255,255,0.03)" },
        },
        crosshair: {
          vertLine: { color: "rgba(16,185,129,0.3)", width: 1, labelBackgroundColor: "#10b981" },
          horzLine: { color: "rgba(16,185,129,0.3)", width: 1, labelBackgroundColor: "#10b981" },
        },
        rightPriceScale: {
          borderColor: "rgba(255,255,255,0.06)",
        },
        timeScale: {
          borderColor: "rgba(255,255,255,0.06)",
          timeVisible: false,
        },
        handleScroll: { mouseWheel: true, pressedMouseMove: true },
        handleScale: { mouseWheel: true, pinch: true },
      });

      chartInstance.current = chart;

      const areaSeries = chart.addSeries(lc.AreaSeries, {
        lineColor: "#10b981",
        lineWidth: 2,
        lineType: lc.LineType.Curved,
        topColor: "rgba(16,185,129,0.25)",
        bottomColor: "rgba(16,185,129,0.01)",
        crosshairMarkerBackgroundColor: "#10b981",
        priceFormat: { type: "price", precision: 2, minMove: 0.01 },
      });

      // Convert dates to time values
      let dateCounter = 0;
      const chartData = equityCurve.map((point) => {
        const dateStr = point.date;
        if (dateStr === "Start" || !dateStr.includes("-")) {
          dateCounter++;
          return { time: `2026-01-${String(dateCounter).padStart(2, "0")}`, value: point.value };
        }
        dateCounter++;
        return { time: dateStr, value: point.value };
      });

      // Deduplicate and sort by time
      const seen = new Set<string>();
      const uniqueData = chartData.filter((d) => {
        if (seen.has(d.time)) return false;
        seen.add(d.time);
        return true;
      });

      areaSeries.setData(uniqueData as Array<{ time: string; value: number }>);
      chart.timeScale().fitContent();

      // Responsive
      const observer = new ResizeObserver((entries) => {
        if (entries[0] && chartInstance.current) {
          const { width, height } = entries[0].contentRect;
          chartInstance.current.applyOptions({ width, height });
        }
      });
      observer.observe(chartRef.current);

      return () => {
        observer.disconnect();
      };
    });

    return () => {
      disposed = true;
      if (chartInstance.current) {
        chartInstance.current.remove();
        chartInstance.current = null;
      }
    };
  }, [equityCurve]);

  return (
    <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 pt-4 pb-2">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveView("equity")}
            className={`text-xs px-3 py-1 rounded-lg transition-all ${
              activeView === "equity"
                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            Account Equity Curve
          </button>
          <button
            onClick={() => setActiveView("market")}
            className={`text-xs px-3 py-1 rounded-lg transition-all ${
              activeView === "market"
                ? "bg-indigo-500/20 text-indigo-400 border border-indigo-500/30"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            Market Chart
          </button>
        </div>
      </div>

      {/* Chart */}
      {activeView === "equity" ? (
        <>
          <div ref={chartRef} className="w-full h-[300px]" />
          {/* Stats row */}
          <div className="grid grid-cols-3 gap-4 px-5 py-3 border-t border-white/5">
            <div>
              <p className="text-[10px] text-zinc-600 uppercase tracking-wider">Initial Balance</p>
              <p
                className="text-sm text-zinc-300 font-medium"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                ${initialBalance.toLocaleString()}
              </p>
            </div>
            <div>
              <p className="text-[10px] text-zinc-600 uppercase tracking-wider">Current Equity</p>
              <p
                className="text-sm text-zinc-300 font-medium"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                ${currentEquity.toLocaleString()}
              </p>
            </div>
            <div>
              <p className="text-[10px] text-zinc-600 uppercase tracking-wider">Return</p>
              <p
                className={`text-sm font-medium ${pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {pnl >= 0 ? "+" : ""}${pnl.toLocaleString(undefined, { maximumFractionDigits: 2 })} ({pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(1)}%)
              </p>
            </div>
          </div>
        </>
      ) : (
        <div className="w-full h-[300px] flex items-center justify-center">
          <div className="text-center">
            <p className="text-zinc-500 text-sm">Market Chart</p>
            <p className="text-zinc-600 text-xs mt-1">Coming in Sprint 2</p>
          </div>
        </div>
      )}
    </div>
  );
}
