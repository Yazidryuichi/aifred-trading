"use client";

import {
  BarChart3,
  MessageSquare,
  ShieldAlert,
  Compass,
  Brain,
  Cpu,
  Eye,
} from "lucide-react";
import type { AgentContributions as AgentData } from "./DecisionCard";

// Extended agent type for the full 7-agent system
export interface FullAgentContributions extends AgentData {
  dataIngestion?: string;
  execution?: string;
  metaLearning?: string;
}

const AGENT_CONFIG: {
  key: keyof FullAgentContributions;
  label: string;
  color: string;
  dotColor: string;
  icon: typeof BarChart3;
}[] = [
  {
    key: "technical",
    label: "Technical Analysis",
    color: "text-blue-400",
    dotColor: "bg-blue-400",
    icon: BarChart3,
  },
  {
    key: "sentiment",
    label: "Sentiment Analysis",
    color: "text-purple-400",
    dotColor: "bg-purple-400",
    icon: MessageSquare,
  },
  {
    key: "risk",
    label: "Risk Management",
    color: "text-amber-400",
    dotColor: "bg-amber-400",
    icon: ShieldAlert,
  },
  {
    key: "regime",
    label: "Regime Detection",
    color: "text-emerald-400",
    dotColor: "bg-emerald-400",
    icon: Compass,
  },
  {
    key: "dataIngestion",
    label: "Data Ingestion",
    color: "text-cyan-400",
    dotColor: "bg-cyan-400",
    icon: Eye,
  },
  {
    key: "execution",
    label: "Execution Engine",
    color: "text-rose-400",
    dotColor: "bg-rose-400",
    icon: Cpu,
  },
  {
    key: "metaLearning",
    label: "Meta-Learning",
    color: "text-indigo-400",
    dotColor: "bg-indigo-400",
    icon: Brain,
  },
];

export function AgentContributionsPanel({
  agents,
}: {
  agents: FullAgentContributions;
}) {
  const active = AGENT_CONFIG.filter((a) => agents[a.key]);

  if (active.length === 0) {
    return (
      <div className="text-[10px] text-zinc-600 py-2">
        No agent contributions available for this cycle.
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      <div className="flex items-center gap-2">
        <span
          className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
        >
          Agent Breakdown
        </span>
        <span className="text-[10px] text-zinc-600">
          {active.length} of {AGENT_CONFIG.length} agents contributed
        </span>
      </div>

      <div className="space-y-2">
        {active.map((config) => {
          const Icon = config.icon;
          const value = agents[config.key]!;
          return (
            <div
              key={config.key}
              className="bg-white/[0.02] border border-white/[0.04] rounded-lg p-2.5"
            >
              <div className="flex items-center gap-2 mb-1.5">
                <Icon className={`w-3.5 h-3.5 ${config.color}`} />
                <span
                  className={`text-[11px] font-medium ${config.color}`}
                  style={{ fontFamily: "Outfit, sans-serif" }}
                >
                  {config.label}
                </span>
              </div>
              <p
                className="text-[10px] text-zinc-400 leading-relaxed pl-5.5"
                style={{ fontFamily: "JetBrains Mono, monospace" }}
              >
                {value}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
