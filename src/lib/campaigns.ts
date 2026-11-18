// Campaign briefs (Content Rewards / Reach and others) and the per-clip rule check.
// The gateway owns the rules and runs the check; this file only maps its JSON.

export type Campaign = {
  id: string;
  name: string;
  agency: string | null;
  marketplace: string | null;
  url: string | null;
  rulesUrl: string | null;
  payout: string | null;
  minTotalViews: number | null;
  creator: string | null;
  sourceChannels: string[];
  sourceSince: string | null;
  platforms: string[];
  mustMention: string | null;
  hashtags: string[];
  submitWithinMin: number | null;
  audience: string | null;
  manual: string[];
};

export type RuleCheck = { rule: string; ok: boolean | null; detail: string };

export type Verdict = "pass" | "manual" | "fail" | "none";

export type CampaignSummary = { id: string; name: string; url: string | null; rulesUrl: string | null; submitWithinMin: number | null };

/** One campaign a clip can go to: its rule check, and whether the clip is going there. */
export type CampaignResult = { campaign: CampaignSummary; checks: RuleCheck[]; verdict: Verdict; selected: boolean; primary: boolean };

export type ClipCampaignCheck = { campaigns: CampaignResult[]; verdict: Verdict; caption: string | null };

const VERDICTS: Verdict[] = ["pass", "manual", "fail", "none"];

function str(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function int(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

export function mapCampaign(raw: Record<string, unknown>): Campaign | null {
  const id = str(raw.id);
  const name = str(raw.name);
  if (!id || !name) return null;
  return {
    id,
    name,
    agency: str(raw.agency),
    marketplace: str(raw.marketplace),
    url: str(raw.url),
    rulesUrl: str(raw.rules_url),
    payout: str(raw.payout),
    minTotalViews: int(raw.min_total_views),
    creator: str(raw.creator),
    sourceChannels: strings(raw.source_channels),
    sourceSince: str(raw.source_since),
    platforms: strings(raw.platforms),
    mustMention: str(raw.must_mention),
    hashtags: strings(raw.hashtags),
    submitWithinMin: int(raw.submit_within_min),
    audience: str(raw.audience),
    manual: strings(raw.manual),
  };
}

export function mapCampaigns(raw: unknown): Campaign[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((c) => (c && typeof c === "object" ? mapCampaign(c as Record<string, unknown>) : null))
    .filter((c): c is Campaign => c !== null);
}

function mapChecks(raw: unknown): RuleCheck[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((x): x is Record<string, unknown> => !!x && typeof x === "object")
    .map((x) => ({ rule: str(x.rule) ?? "", ok: typeof x.ok === "boolean" ? x.ok : null, detail: str(x.detail) ?? "" }))
    .filter((x) => x.rule);
}

function verdictOf(raw: unknown): Verdict {
  return VERDICTS.includes(raw as Verdict) ? (raw as Verdict) : "none";
}

function mapResult(raw: Record<string, unknown>): CampaignResult | null {
  const c = raw.campaign && typeof raw.campaign === "object" ? (raw.campaign as Record<string, unknown>) : null;
  const id = c ? str(c.id) : null;
  const name = c ? str(c.name) : null;
  if (!c || !id || !name) return null;
  return {
    campaign: { id, name, url: str(c.url), rulesUrl: str(c.rules_url), submitWithinMin: int(c.submit_within_min) },
    checks: mapChecks(raw.checks),
    verdict: verdictOf(raw.verdict),
    selected: raw.selected === true,
    primary: raw.primary === true,
  };
}

export function mapClipCheck(raw: Record<string, unknown>): ClipCampaignCheck {
  const campaigns = Array.isArray(raw.campaigns)
    ? raw.campaigns
        .map((r) => (r && typeof r === "object" ? mapResult(r as Record<string, unknown>) : null))
        .filter((r): r is CampaignResult => r !== null)
    : [];
  const text = raw.text && typeof raw.text === "object" ? (raw.text as Record<string, unknown>) : null;
  return { campaigns, verdict: verdictOf(raw.verdict), caption: text ? str(text.caption) : null };
}

export const VERDICT_LABEL: Record<Verdict, string> = {
  pass: "Meets the brief",
  manual: "Check by eye",
  fail: "Breaks the brief",
  none: "No campaign",
};
