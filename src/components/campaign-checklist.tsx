import { VERDICT_LABEL, type CampaignResult, type ClipCampaignCheck } from "@/lib/campaigns";

const VERDICT_STYLE = {
  pass: "bg-good text-bg",
  manual: "bg-warn text-bg",
  fail: "bg-bad text-bg",
  none: "border border-line text-muted",
} as const;

const MARK = { true: "✓", false: "✗", null: "?" } as const;
const MARK_STYLE = { true: "text-good", false: "text-bad", null: "text-warn" } as const;

function CampaignBlock({ result }: { result: CampaignResult }) {
  const broken = result.checks.filter((c) => c.ok === false).length;
  const dim = !result.selected ? "opacity-70" : "";
  return (
    <details className={`rounded-xl border border-line p-3 text-sm ${dim}`} open={result.selected && result.verdict === "fail"}>
      <summary className="flex cursor-pointer flex-wrap items-center gap-2">
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${VERDICT_STYLE[result.verdict]}`}>
          {VERDICT_LABEL[result.verdict]}
        </span>
        <span className="text-fg/85">{result.campaign.name}</span>
        {result.primary ? <span className="text-xs text-muted">main pool</span> : null}
        {!result.primary && !result.selected ? <span className="text-xs text-muted">not added</span> : null}
        {broken ? <span className="text-xs text-bad">{broken} rule(s) broken</span> : null}
      </summary>
      <ul className="mt-2 space-y-1">
        {result.checks.map((c) => (
          <li key={c.rule} className="flex gap-2">
            <span className={MARK_STYLE[String(c.ok) as keyof typeof MARK_STYLE]} aria-label={c.ok === null ? "check by eye" : c.ok ? "passes" : "fails"}>
              {MARK[String(c.ok) as keyof typeof MARK]}
            </span>
            <span className="text-fg/85">
              {c.rule}
              {c.detail ? <span className="text-muted"> · {c.detail}</span> : null}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted">
        {result.campaign.submitWithinMin ? `Submit the posted link within ${result.campaign.submitWithinMin} minutes. ` : ""}
        {result.campaign.rulesUrl ? (
          <a href={result.campaign.rulesUrl} target="_blank" rel="noreferrer" className="underline hover:text-fg">
            Full rules
          </a>
        ) : null}
      </p>
    </details>
  );
}

/** Rule check of one clip for every campaign it can go to; extra pools are opt-in. */
export function CampaignChecklist({ check, editable = false, busy = false, onToggle = () => {} }: {
  check: ClipCampaignCheck;
  editable?: boolean;
  busy?: boolean;
  onToggle?: (campaignId: string) => void;
}) {
  if (!check.campaigns.length) {
    return <p className="text-xs text-muted">No campaign takes this streamer&apos;s clips yet.</p>;
  }
  return (
    <div className="space-y-2">
      {check.campaigns.map((result) => (
        <div key={result.campaign.id} className="space-y-1">
          <CampaignBlock result={result} />
          {editable && !result.primary ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => onToggle(result.campaign.id)}
              className="text-xs text-fg/85 underline hover:text-fg disabled:opacity-60"
            >
              {result.selected ? `Don't submit to ${result.campaign.name}` : `Also submit to ${result.campaign.name}`}
            </button>
          ) : null}
        </div>
      ))}
      {check.caption ? (
        <details className="text-xs text-muted">
          <summary className="cursor-pointer">Caption that will be posted</summary>
          <pre className="mt-1 whitespace-pre-wrap font-sans text-fg/85">{check.caption}</pre>
        </details>
      ) : null}
    </div>
  );
}
