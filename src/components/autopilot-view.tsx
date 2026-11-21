"use client";

import { useCallback, useEffect, useState } from "react";
import type { Autopilot, AutopilotAction, AutopilotItem } from "@/lib/engine";
import { CampaignChecklist } from "@/components/campaign-checklist";
import { HeadlineControl } from "@/components/headline-control";
import { LayoutControl } from "@/components/layout-control";
import { postResult, type Notice } from "@/lib/post-result";

const POLL_MS = 15_000;

const TABS: { key: AutopilotItem["status"] | "all"; label: string }[] = [
  { key: "review", label: "To review" },
  { key: "approved", label: "Posting" },
  { key: "posted", label: "Posted" },
  { key: "rejected", label: "Rejected" },
];

function videoHref(path: string): string {
  const [, , job, file] = path.split("/");
  return `/api/videos/${job}/${encodeURIComponent(file ?? "")}`;
}

function ago(epochSec: number | null): string {
  if (!epochSec) return "never";
  const min = Math.round((Date.now() / 1000 - epochSec) / 60);
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  return `${Math.round(min / 60)} h ago`;
}

export function AutopilotView() {
  const [data, setData] = useState<Autopilot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<AutopilotItem["status"]>("review");
  const [busy, setBusy] = useState<string | null>(null);
  // The button being pressed ("<item id>:<account user>"), so it can say "Posting…".
  const [pressed, setPressed] = useState<string | null>(null);
  // Result of the last action. Kept apart from `error`, which every poll clears.
  const [notice, setNotice] = useState<Notice | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await fetch("/api/autopilot", { cache: "no-store" });
      const body = (await response.json()) as Autopilot & { error?: string };
      if (!response.ok) setError(body.error ?? "Could not load the autopilot.");
      else {
        setError(null);
        setData(body);
        return body;
      }
    } catch {
      setError("Lost the connection. Retrying…");
    }
    return null;
  }, []);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let stopped = false;
    const tick = async () => {
      await load();
      if (!stopped) timer = setTimeout(tick, POLL_MS);
    };
    void tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [load]);

  async function act(id: string, action: AutopilotAction, campaign?: string, text?: string, accountName?: string) {
    setBusy(id);
    if (action === "post") {
      setPressed(`${id}:${campaign}`);
      setNotice({ kind: "wait", text: `Posting to ${accountName ?? "the channel"}… uploading can take a minute.` });
    }
    try {
      const response = await fetch(`/api/autopilot/items/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...(campaign ? { campaign } : {}), ...(text !== undefined ? { text } : {}) }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as { error?: string };
        setNotice({ kind: "bad", text: body.error ?? "Could not update the clip." });
        await load();
        return;
      }
      const fresh = await load();
      if (action === "post") setNotice(postResult(fresh?.items.find((i) => i.id === id), accountName));
    } catch {
      setNotice({ kind: "bad", text: "Lost the connection. Check the Posted tab before pressing again." });
    } finally {
      setBusy(null);
      setPressed(null);
    }
  }

  if (!data) return <p className={error ? "text-bad" : "text-muted"}>{error ?? "Loading…"}</p>;

  const items = data.items.filter((i) => (tab === "rejected" ? i.status === "rejected" : tab === "posted" ? i.status === "posted" || i.status === "failed" : i.status === tab));
  const count = (status: AutopilotItem["status"]) => data.items.filter((i) => i.status === status).length;

  return (
    <div className="space-y-6">
      <section className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-2xl border border-line bg-panel p-4">
          <p className="text-sm text-muted">Streamers</p>
          <ul className="mt-1 space-y-1">
            {data.streamers.map((s) => (
              <li key={s.login} className="flex flex-wrap items-center justify-between gap-x-2">
                <span className="font-medium">{s.name}</span>
                <span className={s.enabled ? "text-xs text-good" : "text-xs text-muted"}>
                  {s.enabled ? "watching" : "off"}
                  {s.enabled && !s.hasAccounts ? " · no accounts yet" : ""}
                </span>
                {s.accounts.length ? <span className="basis-full text-xs text-muted">channels: {s.accounts.map((a) => a.name).join(", ")}</span> : null}
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-2xl border border-line bg-panel p-4">
          <p className="text-sm text-muted">Last check</p>
          <p className="mt-1 font-medium">{ago(data.lastRun)}</p>
          <p className="text-sm text-muted">{data.pending} stretch(es) being clipped now</p>
        </div>
        <div className="rounded-2xl border border-line bg-panel p-4">
          <p className="text-sm text-muted">Posting</p>
          <p className={data.postingReady ? "mt-1 font-medium text-good" : "mt-1 font-medium text-warn"}>
            {data.postingReady ? "Connected" : "Not connected yet"}
          </p>
          <p className="text-sm text-muted">
            {data.postingReady ? "Press Post on a clip to send it to a channel now. Links come to Telegram." : "Approved clips wait until Upload-Post is connected."}
          </p>
        </div>
      </section>

      {error ? <p className="text-sm text-warn">{error}</p> : null}

      {notice ? (
        <div
          role="status"
          aria-live="polite"
          className={`fixed inset-x-4 bottom-4 z-50 mx-auto flex max-w-xl items-start gap-3 rounded-2xl border bg-panel p-4 text-sm shadow-lg ${
            notice.kind === "bad" ? "border-bad text-bad" : notice.kind === "ok" ? "border-good text-good" : "border-line text-fg"
          }`}
        >
          <p className="min-w-0 flex-1 break-words">
            {notice.text}{" "}
            {notice.url ? (
              <a href={notice.url} target="_blank" rel="noreferrer" className="text-accent underline">{notice.url}</a>
            ) : null}
          </p>
          {notice.kind !== "wait" ? (
            <button type="button" onClick={() => setNotice(null)} aria-label="Close" className="text-muted hover:text-fg">×</button>
          ) : null}
        </div>
      ) : null}

      <nav aria-label="Queue" className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            aria-pressed={tab === t.key}
            onClick={() => setTab(t.key as AutopilotItem["status"])}
            className={tab === t.key ? "rounded-full bg-accent px-4 py-2 text-sm font-medium text-accent-ink" : "rounded-full border border-line px-4 py-2 text-sm text-fg/85 hover:border-muted"}
          >
            {t.label} {t.key !== "all" ? `(${count(t.key as AutopilotItem["status"]) + (t.key === "posted" ? count("failed") : 0)})` : ""}
          </button>
        ))}
      </nav>

      {items.length === 0 ? (
        <p className="text-muted">
          {tab === "review" ? "Nothing to review. New clips appear here after the next check." : "Nothing here yet."}
        </p>
      ) : (
        <ul className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <li key={item.id} className="overflow-hidden rounded-2xl border border-line bg-panel">
              <video controls preload="metadata" playsInline src={videoHref(item.videoPath)} className="aspect-[9/16] w-full bg-black" />
              <div className="space-y-3 p-4">
                <p className="text-xs uppercase tracking-wide text-muted">{item.streamer}</p>
                <h2 className="font-medium leading-snug">{item.title || "Untitled clip"}</h2>
                {item.hook ? <p className="text-sm text-fg/85">Hook: &ldquo;{item.hook}&rdquo;</p> : null}
                <div className="flex flex-wrap gap-2 text-xs">
                  {item.score !== null ? <span className="rounded-full bg-accent px-2.5 py-1 font-medium text-accent-ink">score {Math.round(item.score)}</span> : null}
                  {item.durationSec !== null ? <span className="rounded-full border border-line px-2.5 py-1 text-fg/85">{Math.round(item.durationSec)}s</span> : null}
                </div>
                <LayoutControl
                  layout={item.layout}
                  error={item.layoutError}
                  editable={(item.status === "review" || item.status === "approved") && !item.headline}
                  busy={busy === item.id}
                  onSwitch={(to) => act(item.id, "layout", undefined, to)}
                />
                <HeadlineControl
                  key={item.headline ?? "captions"}
                  hook={item.hook}
                  headline={item.headline}
                  editable={item.status === "review" || item.status === "approved"}
                  busy={busy === item.id}
                  onSet={(text) => act(item.id, "headline", undefined, text)}
                  onClear={() => act(item.id, "captions")}
                />
                <CampaignChecklist
                  check={item}
                  editable={item.status === "review" || item.status === "approved"}
                  busy={busy === item.id}
                  onToggle={(campaignId) => act(item.id, "toggle_campaign", campaignId)}
                />
                <a
                  href={`${videoHref(item.videoPath)}?download`}
                  className="inline-block rounded-full border border-line px-4 py-2 text-sm hover:border-muted"
                >
                  Download
                </a>
                {item.status === "review" ? (
                  <div className="flex flex-wrap gap-2">
                    {(data.streamers.find((s) => s.login === item.streamer)?.accounts ?? []).map((a) => (
                      <button
                        key={a.user}
                        type="button"
                        disabled={busy === item.id || item.verdict === "fail"}
                        title={item.verdict === "fail" ? "This clip breaks the campaign brief" : undefined}
                        onClick={() => act(item.id, "post", a.user, undefined, a.name)}
                        className="rounded-full bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-60"
                      >
                        {pressed === `${item.id}:${a.user}` ? `Posting to ${a.name}…` : `Post to ${a.name}`}
                      </button>
                    ))}
                    <button type="button" disabled={busy === item.id} onClick={() => act(item.id, "reject")} className="rounded-full border border-line px-4 py-2 text-sm hover:border-muted disabled:opacity-60">
                      Reject
                    </button>
                  </div>
                ) : null}
                {item.status === "approved" ? (
                  <button type="button" disabled={busy === item.id} onClick={() => act(item.id, "reject")} className="rounded-full border border-line px-4 py-2 text-sm hover:border-muted disabled:opacity-60">
                    Cancel
                  </button>
                ) : null}
                {item.status === "rejected" ? (
                  <button type="button" disabled={busy === item.id} onClick={() => act(item.id, "unreject")} className="rounded-full border border-line px-4 py-2 text-sm hover:border-muted disabled:opacity-60">
                    Back to review
                  </button>
                ) : null}
                {item.status === "posted" ? (
                  <ul className="space-y-1 text-sm">
                    {Object.entries(item.posts).map(([platform, url]) => (
                      <li key={platform}>
                        {platform}:{" "}
                        {url.startsWith("https://") ? (
                          <a href={url} target="_blank" rel="noreferrer" className="text-accent underline">{url}</a>
                        ) : (
                          <span className="text-warn">{url}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {item.status === "failed" ? <p className="text-sm text-bad">Posting failed: {item.error}</p> : null}
              </div>
            </li>
          ))}
        </ul>
      )}

      <details className="rounded-2xl border border-line bg-panel p-4 text-sm text-muted">
        <summary className="cursor-pointer text-fg/85">Activity log</summary>
        <ul className="mt-2 space-y-1 font-mono text-xs">
          {data.log.slice().reverse().map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      </details>
    </div>
  );
}
