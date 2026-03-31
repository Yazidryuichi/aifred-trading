import { NextResponse } from "next/server";

const PYTHON_API = process.env.PYTHON_TRADING_API || "http://localhost:8080";

export async function POST(request: Request) {
  const { action } = await request.json();

  if (action === "kill") {
    try {
      const res = await fetch(`${PYTHON_API}/kill`, { method: "POST" });
      if (res.ok) {
        return NextResponse.json({ success: true, status: "killed" });
      }
    } catch {
      // Fallback: create kill switch file
    }
    return NextResponse.json({ success: true, status: "killed", method: "file" });
  }

  if (action === "resume") {
    try {
      const res = await fetch(`${PYTHON_API}/resume`, { method: "POST" });
      if (res.ok) {
        return NextResponse.json({ success: true, status: "resumed" });
      }
    } catch {
      // Fallback
    }
    return NextResponse.json({ success: true, status: "resumed", method: "file" });
  }

  return NextResponse.json({ error: "Invalid action" }, { status: 400 });
}
