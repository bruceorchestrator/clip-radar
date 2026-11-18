import { NextResponse } from "next/server";
import { isCampaignId } from "@/lib/campaign-engine";
import { actOnAutopilotItem, AUTOPILOT_ACTIONS, EngineError, isBatchId, type AutopilotAction } from "@/lib/engine";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  // Queue item ids are 32-character hex, the same shape as batch ids.
  if (!isBatchId(id)) return NextResponse.json({ error: "Clip not found." }, { status: 404 });
  const body = (await request.json().catch(() => null)) as { action?: unknown; campaign?: unknown; text?: unknown } | null;
  const action = body?.action;
  if (typeof action !== "string" || !AUTOPILOT_ACTIONS.includes(action as AutopilotAction)) {
    return NextResponse.json({ error: "Unknown action." }, { status: 400 });
  }
  const target = typeof body?.campaign === "string" ? body.campaign : undefined;
  if (action === "toggle_campaign" && (!target || !isCampaignId(target))) {
    return NextResponse.json({ error: "Pick a campaign." }, { status: 400 });
  }
  if (action === "post" && (!target || !/^[A-Za-z0-9_@-]{1,60}$/.test(target))) {
    return NextResponse.json({ error: "Pick a channel." }, { status: 400 });
  }
  const text = typeof body?.text === "string" ? body.text.trim() : undefined;
  if (action === "headline" && (!text || text.length > 90)) {
    return NextResponse.json({ error: "Write a headline of up to 90 characters." }, { status: 400 });
  }
  if (action === "layout" && text !== "stacked" && text !== "engine") {
    return NextResponse.json({ error: "Pick a layout." }, { status: 400 });
  }
  try {
    await actOnAutopilotItem(id, action as AutopilotAction, action === "toggle_campaign" || action === "post" ? target : undefined, action === "headline" || action === "layout" ? text : undefined);
    return NextResponse.json({ status: "ok" });
  } catch (error) {
    if (error instanceof EngineError) return NextResponse.json({ error: error.message }, { status: error.status });
    throw error;
  }
}
