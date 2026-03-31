"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

export function KillSwitchButton() {
  const [confirming, setConfirming] = useState(false);
  const queryClient = useQueryClient();

  const { data: health } = useQuery({
    queryKey: ["system-health"],
    queryFn: () => fetch("/api/trading/system-health").then((r) => r.json()),
    refetchInterval: 30_000,
  });

  const isKilled = health?.kill_switch_active === true;

  const mutation = useMutation({
    mutationFn: (action: "kill" | "resume") =>
      fetch("/api/trading/kill-switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      }).then((r) => r.json()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["system-health"] });
      setConfirming(false);
    },
  });

  if (isKilled) {
    return (
      <button
        onClick={() => mutation.mutate("resume")}
        disabled={mutation.isPending}
        className="px-3 py-1.5 rounded-lg bg-green-600 hover:bg-green-700 text-white text-sm font-bold transition-colors disabled:opacity-50"
      >
        {mutation.isPending ? "Resuming..." : "RESUME TRADING"}
      </button>
    );
  }

  if (confirming) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-red-400 text-sm">Close all positions?</span>
        <button
          onClick={() => mutation.mutate("kill")}
          disabled={mutation.isPending}
          className="px-3 py-1.5 rounded-lg bg-red-700 hover:bg-red-800 text-white text-sm font-bold animate-pulse transition-colors disabled:opacity-50"
        >
          {mutation.isPending ? "KILLING..." : "CONFIRM KILL"}
        </button>
        <button
          onClick={() => setConfirming(false)}
          className="px-2 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white text-sm transition-colors"
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={() => setConfirming(true)}
      className="px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm font-bold transition-colors"
    >
      KILL SWITCH
    </button>
  );
}
