import { NextResponse } from "next/server";
import { saveCampaign } from "@/lib/campaign-engine";
import { EngineError } from "@/lib/engine";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { campaign?: unknown } | null;
  const campaign = body?.campaign;
  if (!campaign || typeof campaign !== "object" || Array.isArray(campaign)) {
    return NextResponse.json({ error: "Send the campaign to save." }, { status: 400 });
  }
  try {
    const reply = await saveCampaign(campaign as Record<string, unknown>);
    return NextResponse.json(reply.body, { status: reply.status });
  } catch (error) {
    if (error instanceof EngineError) return NextResponse.json({ error: error.message }, { status: error.status });
    throw error;
  }
}
