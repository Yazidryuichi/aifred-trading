"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

export function SystemHealthDot() {
  const [showTooltip, setShowTooltip] = useState(false);

  const { data } = useQuery({
    queryKey: ["system-health"],
    queryFn: () => fetch("/api/trading/system-health").then((r) => r.json()),
    refetchInterval: 30_000,
  });

  const status = data?.status ?? "unknown";
  const killActive = data?.kill_switch_active ?? false;
  const backendConfigured = data?.backend_configured ?? false;

  let color = "bg-gray-500";
  let label = "Unknown";
  let sublabel = "";

  if (killActive) {
    color = "bg-red-500";
    label = "Kill Switch Active";
  } else if (status === "running" || status === "healthy") {
    color = "bg-green-500";
    label = "Healthy";
  } else if (status === "not_configured") {
    color = "bg-amber-500";
    label = "Standalone Mode";
    sublabel = "Python backend not connected. Trading via API routes.";
  } else if (status === "degraded") {
    color = "bg-yellow-500";
    label = "Degraded";
  } else if (status === "offline" || status === "error") {
    color = "bg-red-500";
    label = backendConfigured ? "Offline" : "Backend Not Configured";
  }

  return (
    <div
      className="relative"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <div className={`w-3 h-3 rounded-full ${color} ${color !== "bg-gray-500" ? "animate-pulse" : ""}`} />
      {showTooltip && (
        <div className="absolute right-0 top-5 px-3 py-2 rounded-lg bg-[#1a1a2e] border border-white/10 text-xs text-white whitespace-nowrap z-50">
          <p className="font-bold">{label}</p>
          {sublabel && (
            <p className="text-amber-400/80 text-[10px] mt-0.5 max-w-[220px] whitespace-normal">
              {sublabel}
            </p>
          )}
          {data?.exchange_connected !== undefined && (
            <p className="text-gray-400">
              Exchange: {data.exchange_connected ? "Connected" : "Disconnected"}
            </p>
          )}
          {data?.last_scan && (
            <p className="text-gray-400">
              Last scan: {new Date(data.last_scan).toLocaleTimeString()}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
