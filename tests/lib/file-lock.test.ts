/**
 * tests/lib/file-lock.test.ts
 *
 * Tests for atomicWriteFile and readJsonWithFallback.
 * These utilities protect against data corruption from concurrent writes.
 */
import { describe, it, expect, afterEach } from "vitest";
import { atomicWriteFile, readJsonWithFallback } from "@/lib/file-lock";
import { existsSync, readFileSync, unlinkSync, mkdirSync, rmSync } from "fs";
import { join } from "path";

const TEST_DIR = join("/tmp", "aifred-test-" + process.pid);
const TEST_FILE = join(TEST_DIR, "test-data.json");

function cleanup() {
  try {
    if (existsSync(TEST_DIR)) {
      rmSync(TEST_DIR, { recursive: true, force: true });
    }
  } catch { /* best effort */ }
}

describe("atomicWriteFile", () => {
  afterEach(cleanup);

  it("creates a file with the correct content", async () => {
    const data = JSON.stringify({ hello: "world" });
    await atomicWriteFile(TEST_FILE, data);

    expect(existsSync(TEST_FILE)).toBe(true);
    const content = readFileSync(TEST_FILE, "utf-8");
    expect(JSON.parse(content)).toEqual({ hello: "world" });
  });

  it("creates parent directories if they do not exist", async () => {
    const deepPath = join(TEST_DIR, "nested", "deep", "file.json");
    await atomicWriteFile(deepPath, '{"nested":true}');

    expect(existsSync(deepPath)).toBe(true);
    expect(JSON.parse(readFileSync(deepPath, "utf-8"))).toEqual({ nested: true });
  });

  it("overwrites existing file atomically", async () => {
    await atomicWriteFile(TEST_FILE, '{"v":1}');
    await atomicWriteFile(TEST_FILE, '{"v":2}');

    const content = JSON.parse(readFileSync(TEST_FILE, "utf-8"));
    expect(content.v).toBe(2);
  });

  it("does not leave .tmp files on success", async () => {
    await atomicWriteFile(TEST_FILE, '{"clean":true}');

    // Check no .tmp files remain
    const { readdirSync } = await import("fs");
    const files = readdirSync(TEST_DIR);
    const tmpFiles = files.filter((f: string) => f.endsWith(".tmp"));
    expect(tmpFiles).toHaveLength(0);
  });
});

describe("readJsonWithFallback", () => {
  afterEach(cleanup);

  it("returns fallback when no files exist", () => {
    const result = readJsonWithFallback<{ x: number }>(
      ["/tmp/nonexistent-abc.json", "/tmp/nonexistent-def.json"],
      { x: 42 },
    );
    expect(result).toEqual({ x: 42 });
  });

  it("reads from the first existing path", async () => {
    await atomicWriteFile(TEST_FILE, '{"source":"primary"}');

    const result = readJsonWithFallback<{ source: string }>(
      [TEST_FILE, "/tmp/nonexistent.json"],
      { source: "fallback" },
    );
    expect(result.source).toBe("primary");
  });

  it("skips corrupt files and returns fallback", async () => {
    await atomicWriteFile(TEST_FILE, "not valid json {{{");

    const result = readJsonWithFallback<{ ok: boolean }>(
      [TEST_FILE],
      { ok: false },
    );
    expect(result).toEqual({ ok: false });
  });
});
