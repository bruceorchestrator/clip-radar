import { creditsFor } from "./plans";

/** Mirrors the gateway: a video up to this long is clipped whole. */
export const SHORT_SOURCE_SEC = 20 * 60;
export const STRETCH_SEC = 180;
export const MIN_STRETCH_SEC = 45;
export const MAX_STRETCH_SEC = 600;

export const CLIP_COUNTS = [5, 10, 20] as const;
export type ClipCount = (typeof CLIP_COUNTS)[number];

export const CLIP_LENGTHS = {
  short: { label: "15–30 s", min: 15, max: 30 },
  medium: { label: "15–45 s", min: 15, max: 45 },
  long: { label: "30–60 s", min: 30, max: 60 },
} as const;
export type ClipLength = keyof typeof CLIP_LENGTHS;

// vertical: 9:16 for Shorts, TikTok and Reels (webcam and game stacked).
// horizontal: the stream frame as it is, 16:9, the way clips run on X.
export const CLIP_FORMATS = {
  vertical: { label: "Vertical 9:16", hint: "Shorts, TikTok, Reels" },
  horizontal: { label: "Wide 16:9", hint: "X (Twitter): the stream frame as it is" },
} as const;
export type ClipFormat = keyof typeof CLIP_FORMATS;

export type Mode = "auto" | "whole" | "stretch";

export type Preview = {
  durationSec: number;
  title: string;
  long: boolean;
  hotspots: { t: number; weight: number }[];
};

export type LaunchOptions = {
  mode: Mode;
  clips: ClipCount;
  length: ClipLength;
  start?: number;
  end?: number;
};

/** Mirrors planner.stretches_for in the gateway: two clips per 3-minute stretch. */
export function stretchesFor(clips: number): number {
  return Math.max(1, Math.min(10, Math.ceil(clips / 2)));
}

/** Credits the job will cost: minutes of video we actually process. */
export function estimateCredits(preview: Preview, options: LaunchOptions): number {
  if (options.mode === "stretch") {
    if (options.start === undefined || options.end === undefined) return 0;
    return creditsFor(options.end - options.start);
  }
  if (!preview.long || options.mode === "whole") return creditsFor(preview.durationSec);
  const processed = Math.min(preview.durationSec, stretchesFor(options.clips) * STRETCH_SEC);
  return creditsFor(processed);
}

/** "1:02:03", "12:30", "45" or "90s" to seconds; null when it is not a time. */
export function parseClock(value: string): number | null {
  const text = value.trim().replace(/s$/i, "");
  if (!/^\d+(:\d{1,2}){0,2}$/.test(text)) return null;
  const parts = text.split(":").map(Number);
  if (parts.slice(1).some((p) => p >= 60)) return null;
  return parts.reduce((total, part) => total * 60 + part, 0);
}

export function formatClock(totalSec: number): string {
  const s = Math.max(0, Math.round(totalSec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${r}` : `${m}:${r}`;
}

/** Why these options cannot start, or null when they can. */
export function launchProblem(preview: Preview, options: LaunchOptions): string | null {
  if (options.mode !== "stretch") return null;
  const { start, end } = options;
  if (start === undefined || end === undefined) return "Set where the stretch starts and ends.";
  if (end > preview.durationSec + 1) return "The end is past the end of the video.";
  const length = end - start;
  if (length < MIN_STRETCH_SEC || length > MAX_STRETCH_SEC) {
    return "A stretch must be between 45 seconds and 10 minutes.";
  }
  return null;
}
