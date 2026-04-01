/**
 * tests/api/kill-switch.test.ts
 *
 * Tests for the kill switch API (/api/trading/kill-switch).
 * The kill switch is the most critical safety mechanism — it must always work.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock file-lock module (used internally by kill switch route)
vi.mock("@/lib/file-lock", () => ({
  atomicWriteFile: vi.fn().mockResolvedValue(undefined),
  readJsonWithFallback: vi.fn().mockReturnValue({}),
}));

// Mock global fetch so the Python backend calls don't go out
vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

import { GET, POST } from "@/app/api/trading/kill-switch/route";
import { readJsonWithFallback, atomicWriteFile } from "@/lib/file-lock";

const mockReadJson = vi.mocked(readJsonWithFallback);
const mockAtomicWrite = vi.mocked(atomicWriteFile);

function makeRequest(body: unknown): Request {
  return new Request("http://localhost/api/trading/kill-switch", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

describe("GET /api/trading/kill-switch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns inactive state by default", async () => {
    mockReadJson.mockReturnValue({});

    const response = await GET();
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data.success).toBe(true);
    expect(data.active).toBe(false);
    expect(data.activatedAt).toBeNull();
  });

  it("returns active state when kill switch has been activated", async () => {
    mockReadJson.mockReturnValue({
      active: true,
      activatedAt: "2026-01-01T00:00:00.000Z",
      reason: "Emergency stop",
    });

    const response = await GET();
    const data = await response.json();

    expect(data.success).toBe(true);
    expect(data.active).toBe(true);
    expect(data.reason).toBe("Emergency stop");
  });
});

describe("POST /api/trading/kill-switch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("activates kill switch with action 'kill'", async () => {
    const response = await POST(makeRequest({ action: "kill", reason: "Test kill" }));
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data.success).toBe(true);
    expect(data.status).toBe("killed");
    expect(data.active).toBe(true);
    expect(data.reason).toBe("Test kill");
    expect(mockAtomicWrite).toHaveBeenCalledTimes(1);
  });

  it("resumes trading with action 'resume'", async () => {
    const response = await POST(makeRequest({ action: "resume" }));
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data.success).toBe(true);
    expect(data.status).toBe("resumed");
    expect(data.active).toBe(false);
    expect(mockAtomicWrite).toHaveBeenCalledTimes(1);
  });

  it("returns 400 for invalid action", async () => {
    const response = await POST(makeRequest({ action: "invalid" }));
    const data = await response.json();

    expect(response.status).toBe(400);
    expect(data.error).toBe("Invalid action");
  });

  it("returns 400 for invalid JSON body", async () => {
    const request = new Request("http://localhost/api/trading/kill-switch", {
      method: "POST",
      body: "not json at all",
    });
    const response = await POST(request);
    const data = await response.json();

    expect(response.status).toBe(400);
    expect(data.error).toBe("Invalid JSON");
  });

  it("returns 413 for oversized request body", async () => {
    const request = new Request("http://localhost/api/trading/kill-switch", {
      method: "POST",
      body: "x".repeat(1001),
    });
    const response = await POST(request);
    const data = await response.json();

    expect(response.status).toBe(413);
    expect(data.error).toBe("Request body too large");
  });

  it("uses 'file' method when Python backend is unreachable", async () => {
    const response = await POST(makeRequest({ action: "kill" }));
    const data = await response.json();

    // fetch is mocked to reject, so method should be "file" not "api+file"
    expect(data.method).toBe("file");
  });
});
