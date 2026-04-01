/**
 * lib/record-decision.ts
 *
 * Utility to record AI decision records from trade execution flows.
 * Writes directly to the decisions JSON file using file-lock utilities,
 * avoiding an HTTP round-trip (same pattern as appendActivity in execute-trade).
 */

import { existsSync, mkdirSync } from "fs";
import { join } from "path";
import { lockedReadModifyWrite } from "@/lib/file-lock";

// ---------------------------------------------------------------------------
// Types (matches app/api/trading/decisions/route.ts)
// ---------------------------------------------------------------------------

interface AssetDecision {
  asset: string;
  action: "buy" | "sell" | "hold" | "close";
  succeeded: boolean;
  confidence?: number;
  reasoning?: string;
}

interface AgentContributions {
  technical?: string;
  sentiment?: string;
  risk?: string;
  regime?: string;
  execution?: string;
}

export interface RecordDecisionParams {
  status: "success" | "failure" | "partial";
  inputPrompt: string;
  chainOfThought: string;
  assetDecisions: AssetDecision[];
  agents: AgentContributions;
  durationMs: number;
  modelVersion?: string;
}

interface DecisionRecord {
  id: string;
  cycleNumber: number;
  timestamp: string;
  status: "success" | "failure" | "partial";
  inputPrompt: string;
  chainOfThought: string;
  assetDecisions: AssetDecision[];
  agents: AgentContributions;
  durationMs: number;
  modelVersion: string;
}

interface DecisionsFile {
  decisions: DecisionRecord[];
  nextCycleNumber: number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TMP_DIR = "/tmp/aifred-data";
const DECISIONS_PATH = join(TMP_DIR, "decisions.json");
const MAX_ENTRIES = 5000;

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Record a decision to the decisions JSON file.
 * Fire-and-forget safe — errors are caught and logged.
 */
export function recordDecision(params: RecordDecisionParams): void {
  if (!existsSync(TMP_DIR)) {
    mkdirSync(TMP_DIR, { recursive: true });
  }

  lockedReadModifyWrite<DecisionsFile>(
    DECISIONS_PATH,
    (current) => {
      const file: DecisionsFile = current ?? { decisions: [], nextCycleNumber: 1 };

      const decision: DecisionRecord = {
        id: `dec_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
        cycleNumber: file.nextCycleNumber,
        timestamp: new Date().toISOString(),
        status: params.status,
        inputPrompt: params.inputPrompt,
        chainOfThought: params.chainOfThought,
        assetDecisions: params.assetDecisions,
        agents: params.agents,
        durationMs: params.durationMs,
        modelVersion: params.modelVersion || "v2.0",
      };

      file.decisions.push(decision);
      file.nextCycleNumber++;

      // Rolling cap
      if (file.decisions.length > MAX_ENTRIES) {
        file.decisions = file.decisions.slice(-MAX_ENTRIES);
      }

      return file;
    },
  ).catch((e) => {
    console.error("Failed to record decision:", e);
  });
}
