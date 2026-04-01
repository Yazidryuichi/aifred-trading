import { NextRequest, NextResponse } from "next/server";
import { executeTrade, type ExecuteTradeParams } from "@/lib/execute-trade";

export const dynamic = "force-dynamic";

// ---------------------------------------------------------------------------
// POST handler — delegates to shared executeTrade() after middleware auth
// ---------------------------------------------------------------------------

export async function POST(request: NextRequest) {
  try {
    const rawBody = await request.text();
    if (rawBody.length > 10_000) {
      return NextResponse.json({ error: "Request body too large" }, { status: 413 });
    }
    const body = JSON.parse(rawBody);
    const params: ExecuteTradeParams = {
      symbol: body.symbol,
      side: body.side,
      quantity: body.quantity,
      orderType: body.orderType,
      brokerId: body.brokerId,
      price: body.price,
      forceExecution: body.forceExecution,
      mode: body.mode,
      limitPrice: body.limitPrice,
      credentials: body.credentials,
    };

    const result = await executeTrade(params);

    return NextResponse.json(result.data, { status: result.status });
  } catch (error) {
    console.error("Trade execution error:", error);
    return NextResponse.json(
      { success: false, message: "Trade execution failed" },
      { status: 500 }
    );
  }
}
