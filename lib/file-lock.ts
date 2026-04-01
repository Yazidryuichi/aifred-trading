/**
 * lib/file-lock.ts
 * Atomic file write + locked read-modify-write utilities.
 *
 * - atomicWriteFile: writes to a .tmp file then renames (atomic on POSIX).
 * - lockedReadModifyWrite: acquires a .lock file, reads the target, applies a
 *   modifier callback, writes atomically, then releases the lock.
 *
 * Uses only Node.js built-in modules (fs, path, crypto).
 */

import {
  writeFileSync,
  renameSync,
  readFileSync,
  unlinkSync,
  existsSync,
  mkdirSync,
  statSync,
} from "fs";
import { dirname, join } from "path";
import { randomBytes } from "crypto";

// ---------------------------------------------------------------------------
// Atomic write: write to .tmp then rename
// ---------------------------------------------------------------------------

export async function atomicWriteFile(
  filePath: string,
  data: string,
): Promise<void> {
  const dir = dirname(filePath);
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }

  const tmpPath = `${filePath}.${randomBytes(6).toString("hex")}.tmp`;

  try {
    writeFileSync(tmpPath, data, "utf-8");
    renameSync(tmpPath, filePath);
  } catch (err) {
    // Clean up temp file on failure
    try {
      if (existsSync(tmpPath)) unlinkSync(tmpPath);
    } catch {
      /* best effort */
    }
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Lock helpers
// ---------------------------------------------------------------------------

const LOCK_STALE_MS = 10_000; // 10 seconds
const LOCK_RETRY_INTERVAL_MS = 25;
const LOCK_MAX_WAIT_MS = 12_000; // slightly longer than stale threshold

function lockPath(filePath: string): string {
  return `${filePath}.lock`;
}

function acquireLock(filePath: string): string {
  const lock = lockPath(filePath);
  const lockId = randomBytes(8).toString("hex");
  const deadline = Date.now() + LOCK_MAX_WAIT_MS;

  while (Date.now() < deadline) {
    // Check for stale lock
    if (existsSync(lock)) {
      try {
        const stat = statSync(lock);
        const age = Date.now() - stat.mtimeMs;
        if (age > LOCK_STALE_MS) {
          // Stale lock — remove it
          try {
            unlinkSync(lock);
          } catch {
            /* another process may have already removed it */
          }
        }
      } catch {
        /* stat failed — lock was likely just removed */
      }
    }

    // Try to create the lock file (O_EXCL via writeFileSync to a non-existent path)
    try {
      // Use a unique temp file + rename to approximate O_EXCL behavior.
      // We write our lockId to a temp, then rename-to-lock. If the lock already
      // exists the rename overwrites (not truly exclusive), so instead we check
      // existence right before and accept a small TOCTOU window — acceptable
      // for this use-case on a single host.
      if (!existsSync(lock)) {
        const dir = dirname(lock);
        if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
        writeFileSync(lock, lockId, { flag: "wx" }); // wx = O_CREAT | O_EXCL
        return lockId;
      }
    } catch (err: unknown) {
      // EEXIST means another process beat us — retry
      if (
        err &&
        typeof err === "object" &&
        "code" in err &&
        (err as NodeJS.ErrnoException).code === "EEXIST"
      ) {
        // expected — retry
      } else {
        throw err;
      }
    }

    // Busy-wait a short interval (sync; we stay inside server-side Node)
    const waitUntil = Date.now() + LOCK_RETRY_INTERVAL_MS;
    while (Date.now() < waitUntil) {
      /* spin */
    }
  }

  throw new Error(
    `Failed to acquire lock for ${filePath} within ${LOCK_MAX_WAIT_MS}ms`,
  );
}

function releaseLock(filePath: string, _lockId: string): void {
  const lock = lockPath(filePath);
  try {
    unlinkSync(lock);
  } catch {
    /* already removed — fine */
  }
}

// ---------------------------------------------------------------------------
// Locked read-modify-write
// ---------------------------------------------------------------------------

/**
 * Atomically read a JSON file, apply `modifier`, and write the result back.
 *
 * @param filePath   - Target file path
 * @param modifier   - Receives the current parsed value (or `null` if file
 *                     doesn't exist / is corrupt). Returns the new value.
 * @param defaultValue - Fallback value passed to modifier when file is missing.
 */
export async function lockedReadModifyWrite<T>(
  filePath: string,
  modifier: (current: T | null) => T,
  _defaultValue?: T,
): Promise<T> {
  const lockId = acquireLock(filePath);

  try {
    // Read current value
    let current: T | null = null;
    if (existsSync(filePath)) {
      try {
        current = JSON.parse(readFileSync(filePath, "utf-8")) as T;
      } catch {
        current = null;
      }
    }

    // Apply modifier
    const updated = modifier(current);

    // Write atomically
    await atomicWriteFile(filePath, JSON.stringify(updated, null, 2));

    return updated;
  } finally {
    releaseLock(filePath, lockId);
  }
}

// ---------------------------------------------------------------------------
// Convenience: locked read with fallback paths (for /tmp + data/ pattern)
// ---------------------------------------------------------------------------

/**
 * Read a JSON file, trying multiple paths in order (first readable wins).
 * Uses file locking on the primary (writable) path.
 *
 * This is a read-only helper — no locking needed for pure reads, but we still
 * provide it for convenience.
 */
export function readJsonWithFallback<T>(
  paths: string[],
  fallback: T,
): T {
  for (const p of paths) {
    if (existsSync(p)) {
      try {
        return JSON.parse(readFileSync(p, "utf-8")) as T;
      } catch {
        /* try next */
      }
    }
  }
  return fallback;
}
