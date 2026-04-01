"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { X, Cpu, Info } from "lucide-react";

interface AddModelModalProps {
  onClose: () => void;
}

const providers = [
  "Anthropic",
  "OpenAI",
  "Google",
  "Meta",
  "Custom",
];

export function AddModelModal({ onClose }: AddModelModalProps) {
  const [modelName, setModelName] = useState("");
  const [provider, setProvider] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [modelId, setModelId] = useState("");

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-model-title"
    >
      {/* Backdrop */}
      <motion.div
        initial={false}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <motion.div
        initial={false}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="relative w-full max-w-md rounded-2xl border border-white/[0.08] p-6"
        style={{
          background: "linear-gradient(135deg, rgba(15,15,20,0.98) 0%, rgba(10,10,15,0.98) 100%)",
          backdropFilter: "blur(20px)",
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-indigo-500/15 border border-indigo-500/25 flex items-center justify-center">
              <Cpu className="w-4 h-4 text-indigo-400" />
            </div>
            <div>
              <h2
                id="add-model-title"
                className="text-base font-bold text-white"
                style={{ fontFamily: "Outfit, sans-serif" }}
              >
                Add AI Model
              </h2>
              <p className="text-[10px] text-zinc-500" style={{ fontFamily: "JetBrains Mono, monospace" }}>
                Configure a new AI model
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg bg-white/[0.04] border border-white/[0.06] flex items-center justify-center text-zinc-500 hover:text-white hover:bg-white/[0.08] transition-all"
            aria-label="Close modal"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form fields */}
        <div className="space-y-4">
          {/* Model Name */}
          <div>
            <label
              className="block text-[10px] text-zinc-500 tracking-wider uppercase mb-1.5"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              Model Name
            </label>
            <input
              type="text"
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              placeholder="e.g. Claude 4 Opus"
              className="w-full px-3 py-2.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-indigo-500/40 transition-colors"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            />
          </div>

          {/* Provider */}
          <div>
            <label
              className="block text-[10px] text-zinc-500 tracking-wider uppercase mb-1.5"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              Provider
            </label>
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className="w-full px-3 py-2.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-sm text-white focus:outline-none focus:border-indigo-500/40 transition-colors appearance-none"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              <option value="" className="bg-zinc-900">Select provider...</option>
              {providers.map((p) => (
                <option key={p} value={p} className="bg-zinc-900">
                  {p}
                </option>
              ))}
            </select>
          </div>

          {/* API Key */}
          <div>
            <label
              className="block text-[10px] text-zinc-500 tracking-wider uppercase mb-1.5"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              API Key
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
              className="w-full px-3 py-2.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-indigo-500/40 transition-colors"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            />
          </div>

          {/* Model ID */}
          <div>
            <label
              className="block text-[10px] text-zinc-500 tracking-wider uppercase mb-1.5"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            >
              Model ID
            </label>
            <input
              type="text"
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              placeholder="e.g. claude-opus-4-6"
              className="w-full px-3 py-2.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-indigo-500/40 transition-colors"
              style={{ fontFamily: "JetBrains Mono, monospace" }}
            />
          </div>
        </div>

        {/* Coming soon notice */}
        <div className="mt-5 p-3 rounded-lg bg-amber-500/[0.06] border border-amber-500/15 flex items-start gap-2">
          <Info className="w-3.5 h-3.5 text-amber-400 mt-0.5 flex-shrink-0" />
          <p
            className="text-[10px] text-amber-400/80 leading-relaxed"
            style={{ fontFamily: "JetBrains Mono, monospace" }}
          >
            Coming soon — multi-model support requires backend integration. Model configuration will be available in a future update.
          </p>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3 mt-5">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-xs text-zinc-400 hover:text-white hover:bg-white/[0.08] transition-all font-medium"
            style={{ fontFamily: "Outfit, sans-serif" }}
          >
            Cancel
          </button>
          <button
            disabled
            className="flex-1 px-4 py-2.5 rounded-lg bg-indigo-500/20 border border-indigo-500/20 text-xs text-indigo-400/50 font-medium cursor-not-allowed"
            style={{ fontFamily: "Outfit, sans-serif" }}
          >
            Add Model
          </button>
        </div>
      </motion.div>
    </div>
  );
}
