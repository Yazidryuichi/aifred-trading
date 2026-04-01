import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const RAILWAY_URL = process.env.RAILWAY_BACKEND_URL;

interface ComponentHealth {
  name: string;
  status: "healthy" | "degraded" | "down";
  latencyMs: number | null;
  message: string;
}

interface SystemHealthResponse {
  overall: "healthy" | "degraded" | "down";
  timestamp: string;
  components: ComponentHealth[];
}

async function checkRailwayOrchestrator(): Promise<ComponentHealth> {
  if (!RAILWAY_URL) {
    return {
      name: "Python Orchestrator",
      status: "down",
      latencyMs: null,
      message: "Backend not configured: RAILWAY_BACKEND_URL environment variable is missing",
    };
  }

  const start = Date.now();
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 8000);

    const res = await fetch(`${RAILWAY_URL}/health`, {
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    const latency = Date.now() - start;

    if (!res.ok) {
      return {
        name: "Python Orchestrator",
        status: "degraded",
        latencyMs: latency,
        message: `Railway returned HTTP ${res.status}`,
      };
    }

    const data = await res.json();
    const checks = data.checks || {};
    const uptime = data.uptime || "unknown";

    return {
      name: "Python Orchestrator",
      status: "healthy",
      latencyMs: latency,
      message: `Running on Railway (uptime: ${uptime}, trading: ${checks.trading_loop || "unknown"})`,
    };
  } catch {
    return {
      name: "Python Orchestrator",
      status: "down",
      latencyMs: Date.now() - start,
      message: "Railway backend unreachable",
    };
  }
}

async function checkHyperliquid(
  name: string,
  url: string,
): Promise<ComponentHealth> {
  const start = Date.now();
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 8000);

    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "meta" }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    const latency = Date.now() - start;

    if (!res.ok) {
      return { name, status: "degraded", latencyMs: latency, message: `HTTP ${res.status}` };
    }

    const data = await res.json();
    const assetCount = data?.universe?.length ?? 0;

    return {
      name,
      status: latency < 3000 ? "healthy" : "degraded",
      latencyMs: latency,
      message: `Connected, ${assetCount} assets (${latency}ms)`,
    };
  } catch (error) {
    return {
      name,
      status: "down",
      latencyMs: Date.now() - start,
      message: error instanceof Error ? error.message : "Connection failed",
    };
  }
}

export async function GET() {
  try {
    const [orchestrator, testnet, mainnet] = await Promise.all([
      checkRailwayOrchestrator(),
      checkHyperliquid("Hyperliquid Testnet", "https://api.hyperliquid-testnet.xyz/info"),
      checkHyperliquid("Hyperliquid Mainnet", "https://api.hyperliquid.xyz/info"),
    ]);

    const components: ComponentHealth[] = [
      { name: "Next.js API", status: "healthy", latencyMs: 0, message: "API server running" },
      orchestrator,
      testnet,
      mainnet,
    ];

    const hasDown = components.some((c) => c.status === "down");
    const hasDegraded = components.some((c) => c.status === "degraded");
    const overall = hasDown
      ? components.every((c) => c.status === "down") ? "down" : "degraded"
      : hasDegraded ? "degraded" : "healthy";

    // Determine trading mode from env vars
    const tradingMode = process.env.TRADING_MODE || "paper";
    const killSwitchActive = false; // Will be true when kill switch API is connected

    return NextResponse.json({
      overall,
      timestamp: new Date().toISOString(),
      components,
      mode: tradingMode,
      status: orchestrator.status === "healthy" ? "running" : "offline",
      kill_switch_active: killSwitchActive,
    });
  } catch (error) {
    console.error("System health API error:", error);
    return NextResponse.json({ error: "Failed to check system health" }, { status: 500 });
  }
}
