import { Suspense } from "react";
import { connection } from "next/server";
import { getCampaigns } from "@/lib/engine";
import type { Campaign } from "@/lib/campaigns";
import { CampaignImport } from "@/components/campaign-import";
import { RemoveCampaign } from "@/components/remove-campaign";

export const metadata = { title: "Campaigns · Clip Radar" };

function Rules({ c }: { c: Campaign }) {
  const auto = [
    c.sourceChannels.length
      ? `Footage from ${c.sourceChannels.join(", ")}${c.sourceSince ? ` streamed ${c.sourceSince.slice(0, 10)} or later` : ""}`
      : null,
    c.platforms.length ? `Post only on ${c.platforms.join(", ")}` : null,
    c.mustMention ? `Name ${c.mustMention} in the caption or on screen` : null,
    c.hashtags.length ? `Caption hashtags: ${c.hashtags.join(" ")}` : null,
    c.submitWithinMin ? `Submit the link within ${c.submitWithinMin} minutes of posting` : null,
  ].filter((r): r is string => !!r);
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div>
        <p className="text-xs uppercase tracking-wide text-muted">Checked on every clip</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-fg/85">
          {auto.map((r) => <li key={r}>{r}</li>)}
        </ul>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-muted">You confirm by eye</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-fg/85">
          {c.manual.map((r) => <li key={r}>{r}</li>)}
        </ul>
      </div>
    </div>
  );
}

async function CampaignList() {
  await connection();
  let campaigns: Campaign[] = [];
  let error: string | null = null;
  try {
    campaigns = await getCampaigns();
  } catch (e) {
    console.error("campaigns:", e);
    error = "Could not load the campaigns. Is the engine running?";
  }
  if (error) return <p className="text-bad">{error}</p>;
  return (
      <ul className="space-y-6">
        {campaigns.map((c) => (
          <li key={c.id} className="space-y-4 rounded-2xl border border-line bg-panel p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-lg font-medium">{c.name}</h2>
              <p className="text-sm text-muted">{[c.agency, c.marketplace].filter(Boolean).join(" on ")}</p>
            </div>
            <p className="text-sm text-fg/85">
              {c.payout}
              {c.minTotalViews ? ` · needs ${c.minTotalViews.toLocaleString("en-US")} approved views in total` : ""}
            </p>
            <Rules c={c} />
            <p className="flex gap-4 text-sm">
              {c.url ? <a href={c.url} target="_blank" rel="noreferrer" className="text-accent underline">Campaign page</a> : null}
              {c.rulesUrl ? <a href={c.rulesUrl} target="_blank" rel="noreferrer" className="text-accent underline">Full rules</a> : null}
              <RemoveCampaign id={c.id} name={c.name} />
            </p>
          </li>
        ))}
      </ul>
  );
}

export default function CampaignsPage() {
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-6">
      <h1 className="text-3xl font-semibold tracking-tight">Campaigns</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Every clip is checked against its campaign brief before it can go out. A clip that breaks a rule cannot be approved.
      </p>
      <div className="mt-8 space-y-8">
        <CampaignImport />
        <Suspense fallback={<p className="text-muted">Loading campaigns…</p>}>
          <CampaignList />
        </Suspense>
      </div>
    </main>
  );
}
