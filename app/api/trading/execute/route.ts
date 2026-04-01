import { NextRequest, NextResponse } from "next/server";
import { executeTrade, type ExecuteTradeParams } from "@/lib/execute-trade";

export const dynamic = "force-dynamic";

// ---------------------------------------------------------------------------
// POST handler — delegates to shared executeTrade() after middleware auth
// ---------------------------------------------------------------------------

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
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
