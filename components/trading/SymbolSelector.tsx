"use client";

import { useState, useCallback } from "react";

const EXCHANGES = [
  { id: "BINANCE", label: "Binance" },
  { id: "COINBASE", label: "Coinbase" },
  { id: "BYBIT", label: "Bybit" },
] as const;

const SYMBOLS = [
  { id: "BTCUSDT", label: "BTC/USDT" },
  { id: "ETHUSDT", label: "ETH/USDT" },
  { id: "SOLUSDT", label: "SOL/USDT" },
  { id: "BTCUSD", label: "BTC/USD" },
] as const;

type ExchangeId = (typeof EXCHANGES)[number]["id"];
type SymbolId = (typeof SYMBOLS)[number]["id"];

interface SymbolSelectorProps {
  value?: string;
  onChange?: (combined: string) => void;
}

export function SymbolSelector({
  value = "BINANCE:BTCUSDT",
  onChange,
}: SymbolSelectorProps) {
  const [exchange, symbol] = value.includes(":")
    ? (value.split(":") as [ExchangeId, SymbolId])
    : (["BINANCE", value] as [ExchangeId, SymbolId]);

  const [activeExchange, setActiveExchange] = useState<ExchangeId>(exchange);
  const [activeSymbol, setActiveSymbol] = useState<SymbolId>(symbol);

  const handleChange = useCallback(
    (newExchange: ExchangeId, newSymbol: SymbolId) => {
      onChange?.(`${newExchange}:${newSymbol}`);
    },
    [onChange]
  );

  const selectExchange = useCallback(
    (ex: ExchangeId) => {
      setActiveExchange(ex);
      handleChange(ex, activeSymbol);
    },
    [activeSymbol, handleChange]
  );

  const selectSymbol = useCallback(
    (sym: SymbolId) => {
      setActiveSymbol(sym);
      handleChange(activeExchange, sym);
    },
    [activeExchange, handleChange]
  );

  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Exchange pills */}
      <div className="flex items-center gap-1">
        {EXCHANGES.map((ex) => (
          <button
            key={ex.id}
            onClick={() => selectExchange(ex.id)}
            className={`px-3 py-1 text-xs font-medium rounded-full transition-colors ${
              activeExchange === ex.id
                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                : "text-zinc-500 border border-white/10 hover:text-zinc-300 hover:border-white/20"
            }`}
          >
            {ex.label}
          </button>
        ))}
      </div>

      <div className="w-px h-4 bg-white/10" />

      {/* Symbol pills */}
      <div className="flex items-center gap-1">
        {SYMBOLS.map((sym) => (
          <button
            key={sym.id}
            onClick={() => selectSymbol(sym.id)}
            className={`px-3 py-1 text-xs font-medium rounded-full transition-colors ${
              activeSymbol === sym.id
                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                : "text-zinc-500 border border-white/10 hover:text-zinc-300 hover:border-white/20"
            }`}
          >
            {sym.label}
          </button>
        ))}
      </div>
    </div>
  );
}
