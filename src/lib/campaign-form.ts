// Editable form for an imported campaign draft. The draft stays in the gateway's
// snake_case shape; the form edits a few fields and the rest passes through untouched.

export type Draft = Record<string, unknown>;

export const FORM_PLATFORMS = ["tiktok", "instagram", "youtube", "x", "facebook", "snapchat"] as const;

export type CampaignForm = {
  name: string;
  channels: string;
  since: string;
  platforms: string[];
  mustMention: string;
  hashtags: string;
  submitWithinMin: string;
  minTotalViews: string;
  minSec: string;
  maxSec: string;
  payout: string;
  manual: string;
};

function s(value: unknown): string {
  return typeof value === "string" ? value : typeof value === "number" ? String(value) : "";
}

function list(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

function count(value: string): number | null {
  const n = Number(value.replace(/[,\s]/g, ""));
  return Number.isInteger(n) && n > 0 ? n : null;
}

export function toForm(draft: Draft): CampaignForm {
  return {
    name: s(draft.name),
    channels: list(draft.source_channels).join(", "),
    since: s(draft.source_since).slice(0, 10),
    platforms: list(draft.platforms),
    mustMention: s(draft.must_mention),
    hashtags: list(draft.hashtags).join(" "),
    submitWithinMin: s(draft.submit_within_min),
    minTotalViews: s(draft.min_total_views),
    minSec: s(draft.min_sec),
    maxSec: s(draft.max_sec),
    payout: s(draft.payout),
    manual: list(draft.manual).join("\n"),
  };
}

export function applyForm(draft: Draft, form: CampaignForm): Draft {
  return {
    ...draft,
    name: form.name.trim(),
    source_channels: form.channels.split(/[\s,]+/).map((c) => c.trim().toLowerCase()).filter(Boolean),
    source_since: /^\d{4}-\d{2}-\d{2}$/.test(form.since) ? form.since : null,
    platforms: form.platforms.filter((p) => (FORM_PLATFORMS as readonly string[]).includes(p)),
    must_mention: form.mustMention.trim() || null,
    hashtags: form.hashtags.split(/[\s,]+/).filter(Boolean),
    submit_within_min: count(form.submitWithinMin),
    min_total_views: count(form.minTotalViews),
    min_sec: count(form.minSec),
    max_sec: count(form.maxSec),
    payout: form.payout.trim() || null,
    manual: form.manual.split("\n").map((m) => m.trim()).filter(Boolean),
  };
}

/** What the reviewer should look at before saving. */
export function formWarnings(form: CampaignForm): string[] {
  const out: string[] = [];
  if (!form.channels.trim()) out.push("No streamer channel: clips cannot be matched to this campaign. Add the Twitch or Kick login.");
  if (!form.platforms.length) out.push("No platforms picked.");
  if (!form.hashtags.trim() && !form.mustMention.trim()) out.push("No required hashtag or name: check the brief.");
  return out;
}
