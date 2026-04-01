import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { getToken } from "next-auth/jwt";

// In-memory rate limiting (per-process, sufficient for single-user)
const rateLimits = new Map<string, { count: number; resetAt: number }>();

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
      if (isRateLimited(`execute:${clientId}`, 1, 10_000)) {
        return NextResponse.json(
          { error: "Rate limit: max 1 trade per 10 seconds" },
          { status: 429 }
        );
      }
    } else if (pathname === "/api/trading/autoscan" && request.method === "POST") {
      if (isRateLimited(`autoscan:${clientId}`, 1, 60_000)) {
        return NextResponse.json(
          { error: "Rate limit: max 1 autoscan per 60 seconds" },
          { status: 429 }
        );
      }
    } else {
      if (isRateLimited(`api:${clientId}`, 10, 60_000)) {
        return NextResponse.json(
          { error: "Rate limit: max 10 requests per minute" },
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
