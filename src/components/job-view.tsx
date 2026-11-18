"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Batch, BatchTask, JobClip } from "@/lib/engine";

const POLL_MS = 5_000;

function videoHref(clip: JobClip, download = false): string {
  // videoPath is "/videos/<engine job>/<file>"; the app serves it at /api/videos/...
  const [, , job, file] = clip.videoPath.split("/");
  return `/api/videos/${job}/${encodeURIComponent(file ?? "")}${download ? "?download" : ""}`;
}

function clock(sec: number | null): string {
  if (sec === null) return "";
  const s = Math.round(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${r}` : `${m}:${r}`;
}

function taskLine(task: BatchTask): string {
  if (task.state === "failed") return task.error ? `Skipped: ${task.error}` : "Skipped";
  if (task.state === "waiting") return "Waiting";
  if (task.state === "cutting") return "Cutting this stretch…";
  const job = task.job;
  if (!job) return "Handed to the clipper…";
  if (job.status === "queued") return "In line for the clipper";
  if (job.status === "failed") return "No clips from this stretch";
  if (job.status === "completed") {
    return job.clips.length === 1 ? "1 clip" : `${job.clips.length} clips`;
  }
  return job.progress ?? "Working…";
}

const TITLE: Record<Batch["status"], string> = {
  planning: "Getting ready",
  running: "Making your clips",
  completed: "Clips ready",
  failed: "This one did not work",
};

export function JobView({ id }: { id: string }) {
  const [batch, setBatch] = useState<Batch | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const response = await fetch(`/api/jobs/${id}`, { cache: "no-store" });
        const body = (await response.json()) as Batch & { error?: string };
        if (stopped) return;
        if (!response.ok) {
          setError(body.error ?? "Could not load this job.");
          if (response.status === 404) return;
        } else {
          setError(null);
          setBatch(body);
          if (body.status === "completed" || body.status === "failed") return;
        }
      } catch {
        if (!stopped) setError("Lost the connection. Retrying…");
      }
      timer = setTimeout(poll, POLL_MS);
    }

    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [id]);

  if (!batch) {
    return <p className={error ? "text-bad" : "text-muted"}>{error ?? "Loading…"}</p>;
  }

  const working = batch.status === "planning" || batch.status === "running";
  const clips = batch.tasks.flatMap((task) => task.job?.clips ?? []);
  const multi = batch.tasks.length > 1;

  return (
    <div>
      <h1 className="text-3xl font-semibold tracking-tight" aria-live="polite">
        {TITLE[batch.status]}
      </h1>
      {batch.title ? <p className="mt-1 text-muted">{batch.title}</p> : null}

      {working ? (
        <p className="mt-3 text-muted">
          {batch.stage ?? "Working on it."} This takes a few minutes. Keep the page open, clips appear here as they finish.
        </p>
      ) : null}

      {batch.status === "failed" ? (
        <div className="mt-4 space-y-4">
          <p className="text-fg/85">
            The video could not be clipped. The usual reasons: the link is private or deleted, the video is shorter than 45 seconds, or nobody speaks in it.
          </p>
          <Link href="/clip" className="inline-block rounded-full bg-accent px-5 py-2.5 font-medium text-accent-ink hover:brightness-110">
            Try another link
          </Link>
        </div>
      ) : null}

      {error && batch.status !== "failed" ? <p className="mt-3 text-sm text-warn">{error}</p> : null}

      {multi ? (
        <section className="mt-6 rounded-2xl border border-line bg-panel p-4">
          <h2 className="text-sm font-medium text-fg/85">
            {batch.tasks.length} stretches of {clock(batch.durationSec)} picked for clipping
          </h2>
          <ul className="mt-3 space-y-1.5 text-sm">
            {batch.tasks.map((task, i) => (
              <li key={i} className="flex flex-wrap justify-between gap-x-4 text-muted">
                <span>
                  <span className="tabular-nums text-fg">{clock(task.start)}–{clock(task.end)}</span> · {task.reason}
                </span>
                <span>{taskLine(task)}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {clips.length > 0 ? (
        <ul className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {clips.map((clip) => (
            <li key={clip.videoPath} className="overflow-hidden rounded-2xl border border-line bg-panel">
              <video controls preload="metadata" playsInline src={videoHref(clip)} className="aspect-[9/16] w-full bg-black" />
              <div className="space-y-3 p-4">
                <h2 className="font-medium leading-snug">{clip.title}</h2>
                {clip.hook ? <p className="text-sm text-fg/85">Hook: &ldquo;{clip.hook}&rdquo;</p> : null}
                {clip.description ? <p className="text-sm text-muted">{clip.description}</p> : null}
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  {clip.score !== null ? (
                    <span className="rounded-full bg-accent px-2.5 py-1 font-medium text-accent-ink">score {Math.round(clip.score)}</span>
                  ) : null}
                  {clip.durationSec !== null ? (
                    <span className="rounded-full border border-line px-2.5 py-1 text-fg/85">{Math.round(clip.durationSec)}s</span>
                  ) : null}
                </div>
                <a href={videoHref(clip, true)} className="inline-block rounded-full border border-line px-4 py-2 text-sm font-medium hover:border-muted">
                  Download
                </a>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      {batch.status === "completed" && clips.length === 0 ? (
        <p className="mt-4 text-fg/85">Nothing in this video was worth a clip. Try a stretch with more going on.</p>
      ) : null}
    </div>
  );
}
