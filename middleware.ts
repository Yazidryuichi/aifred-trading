import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { getToken } from "next-auth/jwt";

// In-memory rate limiting (per-process, sufficient for single-user)
// TODO: In-memory rate limiting is ineffective on Vercel serverless — each cold
// start gets a fresh Map. For production, migrate to Redis-based rate limiting
// (e.g. @upstash/ratelimit) to share state across invocations.
const rateLimits = new Map<string, { count: number; resetAt: number }>();

// Write endpoints that modify state — keep strict rate limits
const WRITE_ENDPOINTS = new Set([
  "/api/trading/execute",
  "/api/trading/kill-switch",
  "/api/trading/controls",
  "/api/trading/autoscan",
]);

function isRateLimited(key: string, maxRequests: number, windowMs: number): boolean {
  const now = Date.now();
  const entry = rateLimits.get(key);

  if (!entry || now > entry.resetAt) {
    rateLimits.set(key, { count: 1, resetAt: now + windowMs });
    return false;
  }

  entry.count++;
  return entry.count > maxRequests;
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip auth routes and static assets
  if (
    pathname.startsWith("/api/auth") ||
    pathname.startsWith("/_next") ||
    pathname === "/login" ||
    pathname.startsWith("/favicon")
  ) {
    return NextResponse.next();
  }

  // Fail-closed: if NEXTAUTH_SECRET is not configured, reject all protected requests
  if (!process.env.NEXTAUTH_SECRET) {
    return NextResponse.json(
      { error: "Server misconfiguration" },
      { status: 500 },
    );
  }

  // Protect all /api/trading/* routes
  if (pathname.startsWith("/api/trading")) {
    const token = await getToken({
      req: request,
      secret: process.env.NEXTAUTH_SECRET,
    });

    if (!token) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    // Rate limiting for trading endpoints
    const clientId = (token.email as string) || "unknown";

    if (pathname === "/api/trading/execute" && request.method === "POST") {
      // Strict: 1 trade execution per 10 seconds
      if (isRateLimited(`execute:${clientId}`, 1, 10_000)) {
        return NextResponse.json(
          { error: "Rate limit: max 1 trade per 10 seconds" },
          { status: 429 }
        );
      }
    } else if (pathname === "/api/trading/autoscan" && request.method === "POST") {
      // Strict: 1 autoscan per 60 seconds
      if (isRateLimited(`autoscan:${clientId}`, 1, 60_000)) {
        return NextResponse.json(
          { error: "Rate limit: max 1 autoscan per 60 seconds" },
          { status: 429 }
        );
      }
    } else if (WRITE_ENDPOINTS.has(pathname) && request.method === "POST") {
      // Strict: other write endpoints — 10 requests per minute
      if (isRateLimited(`write:${clientId}`, 10, 60_000)) {
        return NextResponse.json(
          { error: "Rate limit: max 10 write requests per minute" },
          { status: 429 }
        );
      }
    } else {
      // Read-only data fetching (dashboard polling, hyperliquid, activity, etc.)
      // Dashboard generates ~23 req/min from normal polling, so 60/min is safe
      if (isRateLimited(`read:${clientId}`, 60, 60_000)) {
        return NextResponse.json(
          { error: "Rate limit: max 60 read requests per minute" },
          { status: 429 }
        );
      }
    }
  }

  // Protect dashboard pages (redirect to login)
  if (pathname === "/" || pathname.startsWith("/trading") || pathname.startsWith("/settings")) {
    const token = await getToken({
      req: request,
      secret: process.env.NEXTAUTH_SECRET,
    });

    if (!token) {
      const loginUrl = new URL("/login", request.url);
      return NextResponse.redirect(loginUrl);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/",
    "/trading/:path*",
    "/settings/:path*",
    "/api/trading/:path*",
  ],
};
