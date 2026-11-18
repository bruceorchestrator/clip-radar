import { NextResponse } from "next/server";
import { isCampaignId, removeCampaign } from "@/lib/campaign-engine";
import { EngineError } from "@/lib/engine";

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isCampaignId(id)) return NextResponse.json({ error: "Campaign not found." }, { status: 404 });
  try {
    const reply = await removeCampaign(id);
    return NextResponse.json(reply.body, { status: reply.status });
  } catch (error) {
    if (error instanceof EngineError) return NextResponse.json({ error: error.message }, { status: error.status });
    throw error;
  }
}
