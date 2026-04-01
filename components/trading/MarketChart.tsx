"use client";

import { useEffect, useRef, memo } from "react";

interface MarketChartProps {
  symbol?: string;
  interval?: string;
  theme?: "dark" | "light";
  height?: number;
}

function MarketChartInner({
  symbol = "BINANCE:BTCUSDT",
  interval = "60",
  theme = "dark",
  height = 400,
}: MarketChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Clear previous widget
    container.innerHTML = "";

    const script = document.createElement("script");
    script.src =
      "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.type = "text/javascript";
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol,
      interval,
      timezone: "Etc/UTC",
      theme,
      style: "1",
      locale: "en",
      allow_symbol_change: true,
      calendar: false,
      support_host: "https://www.tradingview.com",
      hide_top_toolbar: false,
      hide_legend: false,
      save_image: false,
      backgroundColor: "rgba(6, 6, 10, 1)",
      gridColor: "rgba(255, 255, 255, 0.04)",
    });

    container.appendChild(script);

    return () => {
      if (container) {
        container.innerHTML = "";
      }
    };
  }, [symbol, interval, theme]);

  return (
    <div
      className="rounded-xl overflow-hidden border border-white/10 bg-[#06060a]"
      style={{ height }}
    >
      <div ref={containerRef} style={{ height: "100%", width: "100%" }} />
    </div>
  );
}

export const MarketChart = memo(MarketChartInner);
