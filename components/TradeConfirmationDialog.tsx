"use client";

import { useState, useEffect } from "react";

interface TradeDetails {
  symbol: string;
  side: "LONG" | "SHORT";
  quantity: number;
  estimatedPrice: number;
  stopLoss: number;
  leverage: number;
  estimatedMaxLoss: number;
}

interface Props {
  trade: TradeDetails;
  onConfirm: () => void;
  onCancel: () => void;
  isSubmitting: boolean;
}

export function TradeConfirmationDialog({
  trade,
  onConfirm,
  onCancel,
  isSubmitting,
}: Props) {
  const [countdown, setCountdown] = useState(3);

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  const positionValue = trade.quantity * trade.estimatedPrice;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="w-full max-w-md p-6 rounded-xl border border-red-500/30 bg-[#0a0a0f]">
        <h2 className="text-xl font-bold text-red-400 mb-4">
          Confirm Live Trade
        </h2>

        <div className="space-y-3 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-400">Asset</span>
            <span className="text-white font-mono">{trade.symbol}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Direction</span>
            <span className={trade.side === "LONG" ? "text-green-400" : "text-red-400"}>
              {trade.side}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Position Size</span>
            <span className="text-white">${positionValue.toFixed(2)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Leverage</span>
            <span className="text-white">{trade.leverage}x</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Est. Entry Price</span>
            <span className="text-white font-mono">
              ${trade.estimatedPrice.toLocaleString()}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Stop Loss</span>
            <span className="text-red-400 font-mono">
              ${trade.stopLoss.toLocaleString()}
            </span>
          </div>
          <div className="flex justify-between border-t border-white/10 pt-2">
            <span className="text-gray-400">Est. Max Loss</span>
            <span className="text-red-400 font-bold">
              -${trade.estimatedMaxLoss.toFixed(2)}
            </span>
          </div>
        </div>

        <div className="flex gap-3 mt-6">
          <button
            onClick={onCancel}
            disabled={isSubmitting}
            className="flex-1 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={countdown > 0 || isSubmitting}
            className="flex-1 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white font-bold transition-colors disabled:opacity-50"
          >
            {isSubmitting
              ? "Executing..."
              : countdown > 0
                ? `Confirm (${countdown}s)`
                : "Confirm Trade"}
          </button>
        </div>
      </div>
    </div>
  );
}
