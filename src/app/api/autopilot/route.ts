import { NextResponse } from "next/server";
import { EngineError, getAutopilot } from "@/lib/engine";

export async function GET() {
  try {
    return NextResponse.json(await getAutopilot(), { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (error instanceof EngineError) return NextResponse.json({ error: error.message }, { status: error.status });
    throw error;
  }
}
