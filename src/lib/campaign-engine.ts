// Server-only calls to the gateway's campaign endpoints (import a brief, save, remove).
import { EngineError, engineFetch } from "./engine";

export type GatewayReply = { status: number; body: Record<string, unknown> };

const CAMPAIGN_ID = /^[a-z0-9-]{1,60}$/;

export function isCampaignId(id: string): boolean {
  return CAMPAIGN_ID.test(id);
}

async function post(path: string, payload: unknown): Promise<GatewayReply> {
  const response = await engineFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (response.status >= 500) {
    throw new EngineError(typeof body.error === "string" ? body.error : "The campaign service failed.", 502);
  }
  return { status: response.status, body };
}

/** Read a brief (link or pasted text) into a draft campaign; nothing is saved. */
export function importBrief(input: { url?: string; text?: string }): Promise<GatewayReply> {
  return post("/campaigns/import", input);
}

/** Save (add or replace) a campaign; the gateway validates every field. */
export function saveCampaign(campaign: Record<string, unknown>): Promise<GatewayReply> {
  return post("/campaigns", { campaign });
}

export function removeCampaign(id: string): Promise<GatewayReply> {
  return post(`/campaigns/${id}/remove`, {});
}
