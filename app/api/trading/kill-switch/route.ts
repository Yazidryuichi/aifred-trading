import { NextResponse } from "next/server";
import { atomicWriteFile, readJsonWithFallback } from "@/lib/file-lock";
import { join } from "path";

export const dynamic = "force-dynamic";

const PYTHON_API = process.env.PYTHON_TRADING_API || process.env.RAILWAY_BACKEND_URL || "http://localhost:8080";

const TMP_DIR = "/tmp/aifred-data";
const KILL_SWITCH_PATH = join(TMP_DIR, "kill-switch.json");

// ---------------------------------------------------------------------------
// Kill switch persisted state
// ---------------------------------------------------------------------------

interface KillSwitchState {
  active: boolean;
  activatedAt: string | null;
  reason: string;
}

const DEFAULT_STATE: KillSwitchState = {
  active: false,
  activatedAt: null,
  reason: "",
};

function readKillSwitchState(): KillSwitchState {
  const raw = readJsonWithFallback<Partial<KillSwitchState>>(
    [KILL_SWITCH_PATH],
    {},
  );
  return { ...DEFAULT_STATE, ...raw };
}

async function writeKillSwitchState(state: KillSwitchState): Promise<void> {
  await atomicWriteFile(KILL_SWITCH_PATH, JSON.stringify(state, null, 2));
}

// ---------------------------------------------------------------------------
// GET /api/trading/kill-switch -- return current persisted state
// ---------------------------------------------------------------------------

export async function GET() {
  try {
    const state = readKillSwitchState();
    return NextResponse.json({ success: true, ...state });
  } catch (error) {
    console.error("Kill switch GET error:", error);
    return NextResponse.json(
      { error: "Failed to read kill switch state" },
      { status: 500 },
    );
  }
}

// ---------------------------------------------------------------------------
// POST /api/trading/kill-switch -- activate or resume
// ---------------------------------------------------------------------------

export async function POST(request: Request) {
  const rawBody = await request.text();
  if (rawBody.length > 1_000) {
    return NextResponse.json({ error: "Request body too large" }, { status: 413 });
  }

  let action: string;
  let reason: string | undefined;
  try {
    const parsed = JSON.parse(rawBody);
    action = parsed.action;
    reason = parsed.reason;
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  if (action === "kill") {
    // Persist kill switch state first (file-based, survives restarts)
    const state: KillSwitchState = {
      active: true,
      activatedAt: new Date().toISOString(),
      reason: reason || "Manual kill switch activation",
    };
    await writeKillSwitchState(state);

    // Also try to notify the Python backend
    try {
      const res = await fetch(`${PYTHON_API}/kill`, { method: "POST" });
      if (res.ok) {
        return NextResponse.json({ success: true, status: "killed", method: "api+file", ...state });
      }
    } catch {
      // Python backend unreachable -- state is still persisted to file
    }

    return NextResponse.json({ success: true, status: "killed", method: "file", ...state });
  }

  if (action === "resume") {
    // Clear persisted kill switch state
    const state: KillSwitchState = {
      active: false,
      activatedAt: null,
      reason: "",
    };
    await writeKillSwitchState(state);

    // Also try to notify the Python backend
    try {
      const res = await fetch(`${PYTHON_API}/resume`, { method: "POST" });
      if (res.ok) {
        return NextResponse.json({ success: true, status: "resumed", method: "api+file", ...state });
      }
    } catch {
      // Python backend unreachable -- state is still persisted to file
    }

    return NextResponse.json({ success: true, status: "resumed", method: "file", ...state });
  }

  return NextResponse.json({ error: "Invalid action" }, { status: 400 });
}
