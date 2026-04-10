import { NextResponse } from "next/server";
import { atomicWriteFile, readJsonWithFallback } from "@/lib/file-lock";
import { join } from "path";

export const dynamic = "force-dynamic";

const RAILWAY_BACKEND_URL = process.env.RAILWAY_BACKEND_URL;
const PYTHON_API = RAILWAY_BACKEND_URL || process.env.PYTHON_TRADING_API || "http://localhost:8080";

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
// Helper: POST to Railway backend with 5s timeout
// ---------------------------------------------------------------------------

async function postToBackend(endpoint: string): Promise<{ ok: boolean; source: string }> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);

  try {
    const res = await fetch(`${PYTHON_API}${endpoint}`, {
      method: "POST",
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (res.ok) {
      return { ok: true, source: RAILWAY_BACKEND_URL ? "railway" : "legacy-api" };
    }
    return { ok: false, source: "none" };
  } catch {
    clearTimeout(timeout);
    return { ok: false, source: "none" };
  }
}

// ---------------------------------------------------------------------------
// GET /api/trading/kill-switch -- return current persisted state
// ---------------------------------------------------------------------------

export async function GET() {
  try {
    const state = readKillSwitchState();
    return NextResponse.json({ success: true, ...state, source: "local" });
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

    // Also try to notify the Railway/Python backend
    const backend = await postToBackend("/kill");
    const method = backend.ok ? "api+file" : "file";
    const source = backend.ok ? backend.source : "local";

    return NextResponse.json({ success: true, status: "killed", method, source, ...state });
  }

  if (action === "resume") {
    // Clear persisted kill switch state
    const state: KillSwitchState = {
      active: false,
      activatedAt: null,
      reason: "",
    };
    await writeKillSwitchState(state);

    // Also try to notify the Railway/Python backend
    const backend = await postToBackend("/resume");
    const method = backend.ok ? "api+file" : "file";
    const source = backend.ok ? backend.source : "local";

    return NextResponse.json({ success: true, status: "resumed", method, source, ...state });
  }

  return NextResponse.json({ error: "Invalid action" }, { status: 400 });
}
