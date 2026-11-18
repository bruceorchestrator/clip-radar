"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import {
  CLIP_COUNTS,
  CLIP_FORMATS,
  CLIP_LENGTHS,
  estimateCredits,
  formatClock,
  launchProblem,
  parseClock,
  STRETCH_SEC,
  stretchesFor,
  type ClipCount,
  type ClipFormat,
  type ClipLength,
  type LaunchOptions,
  type Mode,
  type Preview,
} from "@/lib/launch";

type Props = {
  defaultUrl: string;
  defaultStart: string;
  defaultEnd: string;
  /** Read on the server when the page opened with a link (from the radar). */
  initialPreview: Preview | null;
};

const FIELD =
  "w-full rounded-lg border border-line bg-panel px-3 py-2.5 text-fg placeholder:text-muted focus:border-accent focus:outline-none";

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      className={
        on
          ? "rounded-full bg-accent px-4 py-2 text-sm font-medium text-accent-ink"
          : "rounded-full border border-line px-4 py-2 text-sm text-fg/85 hover:border-muted"
      }
    >
      {children}
    </button>
  );
}

/** A strip across the whole stream; each hot moment is a mark, stronger = brighter. */
function Heatmap({ preview, stretch }: { preview: Preview; stretch?: [number, number] }) {
  const max = Math.max(1, ...preview.hotspots.map((h) => h.weight));
  const pos = (t: number) => `${Math.min(100, (t / preview.durationSec) * 100)}%`;
  return (
    <div>
      <div className="relative h-9 overflow-hidden rounded-lg bg-panel-2" aria-hidden>
        {preview.hotspots.map((h) => (
          <span
            key={h.t}
            className="absolute top-0 h-full w-1.5 -translate-x-1/2 rounded bg-accent"
            style={{ left: pos(h.t), opacity: 0.35 + 0.65 * (h.weight / max) }}
          />
        ))}
        {stretch ? (
          <span
            className="absolute top-0 h-full border-x-2 border-fg/80 bg-fg/15"
            style={{ left: pos(stretch[0]), width: `calc(${pos(stretch[1])} - ${pos(stretch[0])})` }}
          />
        ) : null}
      </div>
      <div className="mt-1 flex justify-between text-xs tabular-nums text-muted">
        <span>0:00</span>
        <span>{formatClock(preview.durationSec)}</span>
      </div>
    </div>
  );
}

export function ClipForm({ defaultUrl, defaultStart, defaultEnd, initialPreview }: Props) {
  const router = useRouter();
  const [url, setUrl] = useState(defaultUrl);
  const [preview, setPreview] = useState<Preview | null>(initialPreview);
  const [checking, setChecking] = useState(false);
  const [mode, setMode] = useState<Mode>(defaultStart && defaultEnd ? "stretch" : "auto");
  const [clips, setClips] = useState<ClipCount>(10);
  const [length, setLength] = useState<ClipLength>("medium");
  const [format, setFormat] = useState<ClipFormat>("vertical");
  const [startText, setStartText] = useState(defaultStart ? formatClock(Number(defaultStart)) : "");
  const [endText, setEndText] = useState(defaultEnd ? formatClock(Number(defaultEnd)) : "");
  const [rights, setRights] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const checked = useRef<string | null>(initialPreview ? defaultUrl.trim() : null);

  async function check(target: string) {
    const link = target.trim();
    if (!link || checked.current === link) return;
    checked.current = link;
    setChecking(true);
    setError(null);
    setPreview(null);
    try {
      const response = await fetch("/api/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: link }),
      });
      const body = (await response.json()) as Preview & { error?: string };
      if (!response.ok) {
        setError(body.error ?? "Could not read this video.");
        checked.current = null;
      } else {
        setPreview(body);
      }
    } catch {
      setError("Could not reach the server. Try again.");
      checked.current = null;
    } finally {
      setChecking(false);
    }
  }

  const start = parseClock(startText) ?? undefined;
  const end = parseClock(endText) ?? undefined;
  const options: LaunchOptions = { mode, clips, length, start, end };
  const credits = preview ? estimateCredits(preview, options) : 0;
  const problem = preview ? launchProblem(preview, options) : null;
  const effectiveMode: Mode = preview && !preview.long && mode === "auto" ? "whole" : mode;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!preview || problem) return;
    setPending(true);
    setError(null);
    try {
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: url.trim(),
          mode: effectiveMode,
          clips,
          length,
          format,
          ...(mode === "stretch" ? { sourceStart: start, sourceEnd: end } : {}),
          rightsConfirmed: rights,
        }),
      });
      const body = (await response.json()) as { id?: string; error?: string };
      if (!response.ok || !body.id) {
        setError(body.error ?? "Something went wrong. Try again.");
        setPending(false);
        return;
      }
      router.push(`/jobs/${body.id}`);
    } catch {
      setError("Could not reach the server. Check your connection and try again.");
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      <div>
        <label htmlFor="url" className="mb-1.5 block text-sm font-medium">Stream or video link</label>
        <div className="flex gap-2">
          <input
            id="url"
            type="url"
            required
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              if (e.target.value.trim() !== checked.current) setPreview(null);
            }}
            onBlur={() => void check(url)}
            onPaste={(e) => {
              const pasted = e.clipboardData.getData("text");
              setTimeout(() => void check(pasted), 0);
            }}
            placeholder="https://www.twitch.tv/videos/…"
            className={FIELD}
          />
          <button
            type="button"
            onClick={() => {
              checked.current = null;
              void check(url);
            }}
            className="shrink-0 rounded-lg border border-line px-4 text-sm font-medium hover:border-muted"
          >
            Check
          </button>
        </div>
        <p className="mt-1.5 text-sm text-muted">Twitch or Kick recordings, YouTube videos. At least 45 seconds.</p>
      </div>

      {checking ? <p className="text-sm text-muted" aria-live="polite">Reading the video…</p> : null}

      {preview ? (
        <div className="space-y-6">
          <section className="rounded-2xl border border-line bg-panel p-4">
            <p className="font-medium">{preview.title || "Untitled"}</p>
            <p className="mb-3 text-sm text-muted">
              {formatClock(preview.durationSec)}
              {preview.long
                ? preview.hotspots.length > 0
                  ? ` · ${preview.hotspots.length} moments viewers clipped`
                  : " · no viewer clips, we will listen for the loudest reactions"
                : " · short enough to clip whole"}
            </p>
            {preview.long ? (
              <Heatmap preview={preview} stretch={mode === "stretch" && start !== undefined && end !== undefined ? [start, end] : undefined} />
            ) : null}
          </section>

          {preview.long ? (
            <fieldset>
              <legend className="mb-2 text-sm font-medium">What to clip</legend>
              <div className="flex flex-wrap gap-2">
                <Chip on={mode === "auto"} onClick={() => setMode("auto")}>Hot moments</Chip>
                <Chip on={mode === "stretch"} onClick={() => setMode("stretch")}>My stretch</Chip>
                <Chip on={mode === "whole"} onClick={() => setMode("whole")}>Whole stream</Chip>
              </div>
              <p className="mt-2 text-sm text-muted">
                {mode === "auto"
                  ? `We cut ${stretchesFor(clips)} stretches of ${STRETCH_SEC / 60} minutes around the hottest moments. You pay for those minutes only.`
                  : mode === "whole"
                    ? "Every minute of the stream is processed. Slow and costly on long streams."
                    : "Up to 10 minutes, for example 1:02:30 to 1:05:00."}
              </p>
              {mode === "stretch" ? (
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <div>
                    <label htmlFor="start" className="mb-1 block text-sm text-muted">From</label>
                    <input id="start" value={startText} onChange={(e) => setStartText(e.target.value)} placeholder="1:02:30" inputMode="numeric" className={FIELD} />
                  </div>
                  <div>
                    <label htmlFor="end" className="mb-1 block text-sm text-muted">To</label>
                    <input id="end" value={endText} onChange={(e) => setEndText(e.target.value)} placeholder="1:05:00" inputMode="numeric" className={FIELD} />
                  </div>
                </div>
              ) : null}
            </fieldset>
          ) : null}

          <fieldset>
            <legend className="mb-2 text-sm font-medium">How many clips</legend>
            <div className="flex flex-wrap gap-2">
              {CLIP_COUNTS.map((n) => (
                <Chip key={n} on={clips === n} onClick={() => setClips(n)}>{n}</Chip>
              ))}
            </div>
            <p className="mt-2 text-sm text-muted">A target: weak material gives fewer clips rather than filler.</p>
          </fieldset>

          <fieldset>
            <legend className="mb-2 text-sm font-medium">Format</legend>
            <div className="flex flex-wrap gap-2">
              {(Object.keys(CLIP_FORMATS) as ClipFormat[]).map((key) => (
                <Chip key={key} on={format === key} onClick={() => setFormat(key)}>{CLIP_FORMATS[key].label}</Chip>
              ))}
            </div>
            <p className="mt-2 text-sm text-muted">{CLIP_FORMATS[format].hint}</p>
          </fieldset>

          <fieldset>
            <legend className="mb-2 text-sm font-medium">Clip length</legend>
            <div className="flex flex-wrap gap-2">
              {(Object.keys(CLIP_LENGTHS) as ClipLength[]).map((key) => (
                <Chip key={key} on={length === key} onClick={() => setLength(key)}>{CLIP_LENGTHS[key].label}</Chip>
              ))}
            </div>
          </fieldset>

          <label className="flex items-start gap-3 text-sm text-fg/85">
            <input type="checkbox" required checked={rights} onChange={(e) => setRights(e.target.checked)} className="mt-0.5 size-4 accent-accent" />
            <span>I own this content or have the right to clip it, for example through a campaign that allows clipping.</span>
          </label>

          {problem ? <p className="text-sm text-warn">{problem}</p> : null}

          <button
            type="submit"
            disabled={pending || !!problem || !rights}
            className="rounded-full bg-accent px-6 py-3 font-medium text-accent-ink hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pending ? "Starting…" : `Make ${clips} clips · ${credits} ${credits === 1 ? "credit" : "credits"}`}
          </button>
          <p className="text-xs text-muted">1 credit = 1 minute of video we process.</p>
        </div>
      ) : null}

      {error ? (
        <p role="alert" className="rounded-lg border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
          {error}
        </p>
      ) : null}
    </form>
  );
}
