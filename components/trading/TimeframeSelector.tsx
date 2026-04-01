"use client";

const TIMEFRAMES = [
  { label: "1m", value: "1" },
  { label: "5m", value: "5" },
  { label: "15m", value: "15" },
  { label: "30m", value: "30" },
  { label: "1H", value: "60" },
  { label: "4H", value: "240" },
  { label: "1D", value: "D" },
  { label: "1W", value: "W" },
] as const;

interface TimeframeSelectorProps {
  value?: string;
  onChange?: (interval: string) => void;
}

export function TimeframeSelector({
  value = "60",
  onChange,
}: TimeframeSelectorProps) {
  return (
    <div className="flex items-center gap-1">
      {TIMEFRAMES.map((tf) => (
        <button
          key={tf.value}
          onClick={() => onChange?.(tf.value)}
          className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
            value === tf.value
              ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
              : "text-zinc-500 border border-transparent hover:text-zinc-300"
          }`}
        >
          {tf.label}
        </button>
      ))}
    </div>
  );
}
