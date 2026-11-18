import type { ClipFormat, ClipLength, ClipCount, Mode, Preview } from "./launch";
import type { ClipSource } from "./types";
import { mapCampaigns, mapClipCheck, type Campaign, type ClipCampaignCheck } from "./campaigns";

/**
 * Client for the clipping stack: our gateway in front of an unmodified
 * OpenShorts core (MIT). The gateway cuts stretches and finds the hot moments
 * of long streams; the core makes the clips. Both are private: only this
 * server talks to them, never the browser.
 */
const GATEWAY_URL = (process.env.GATEWAY_URL ?? "http://127.0.0.1:8110").replace(/\/$/, "");
const TIMEOUT_MS = 30_000;

export type JobStatus = "queued" | "processing" | "completed" | "failed";

export type JobClip = {
  index: number;
  title: string;
  description: string | null;
  /** The opening line the engine burned in as a hook. */
  hook: string | null;
  score: number | null;
  durationSec: number | null;
  /** Path under the engine's /videos mount, for example "/videos/<job>/<file>.mp4". */
  videoPath: string;
};

export type Job = {
  id: string;
  status: JobStatus;
  /** The latest progress line that is safe and useful to show a user. */
  progress: string | null;
  clips: JobClip[];
};

type RawClip = Record<string, unknown>;
type RawStatus = {
  status?: string;
  logs?: unknown[];
  result?: { clips?: RawClip[] } | null;
};

export class EngineError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export async function engineFetch(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${GATEWAY_URL}${path}`, {
      ...init,
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    throw new EngineError("The clipping engine is not reachable.", 502);
  }
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : null;
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function mapJobClip(raw: RawClip, index: number): JobClip | null {
  const videoPath = text(raw.video_url);
  if (!videoPath || !videoPath.startsWith("/videos/")) return null;
  const start = num(raw.start);
  const end = num(raw.end);
  return {
    index,
    title:
      text(raw.video_title_for_youtube_short) ?? text(raw.title) ?? `Clip ${index + 1}`,
    description:
      text(raw.video_description_for_tiktok) ?? text(raw.video_description_for_instagram),
    hook: text(raw.viral_hook_text),
    score: num(raw.predicted_score) ?? num(raw.viral_score),
    durationSec: num(raw.duration) ?? (start !== null && end !== null ? end - start : null),
    videoPath,
  };
}

/**
 * Engine log lines are raw tool output (paths, tracebacks, model names), so
 * users never see them. Each pipeline stage maps to a fixed message instead.
 */
const STAGES: { match: RegExp; message: (line: string) => string }[] = [
  { match: /^📥/u, message: () => "Downloading the video…" },
  { match: /^🎛/u, message: () => "Looking at the layout…" },
  {
    match: /^🎙/u,
    message: (line) => {
      const percent = line.match(/(\d{1,3})%/);
      return percent ? `Transcribing… ${percent[1]}%` : "Transcribing…";
    },
  },
  { match: /^🤖/u, message: () => "Finding the best moments…" },
  {
    match: /^🔥/u,
    message: (line) => {
      const count = line.match(/(\d+) clips?/);
      return count ? `Found ${count[1]} ${count[1] === "1" ? "moment" : "moments"}. Rendering…` : "Rendering…";
    },
  },
  { match: /^(🎬|🎞)/u, message: () => "Rendering the clips…" },
  { match: /^💬/u, message: () => "Adding captions…" },
];

export function pickProgress(logs: unknown[]): string | null {
  for (let i = logs.length - 1; i >= 0; i--) {
    const line = typeof logs[i] === "string" ? (logs[i] as string).trim() : "";
    const stage = STAGES.find((s) => s.match.test(line));
    if (stage) return stage.message(line);
  }
  return null;
}

export function mapJob(id: string, raw: RawStatus): Job {
  const status: JobStatus =
    raw.status === "completed" || raw.status === "failed" || raw.status === "queued"
      ? raw.status
      : "processing";
  const clips = (raw.result?.clips ?? [])
    .map((clip, index) => mapJobClip(clip, index))
    .filter((clip): clip is JobClip => clip !== null);
  return { id, status, progress: pickProgress(raw.logs ?? []), clips };
}

export type TaskState = "waiting" | "cutting" | "submitted" | "failed";

export type BatchTask = {
  start: number | null;
  end: number | null;
  reason: string;
  state: TaskState;
  error: string | null;
  /** The engine job for this stretch, once it was handed over. */
  job: Job | null;
};

export type BatchStatus = "planning" | "running" | "completed" | "failed";

export type Batch = {
  id: string;
  status: BatchStatus;
  /** What the gateway is doing right now, for the user. */
  stage: string | null;
  durationSec: number | null;
  title: string | null;
  error: string | null;
  tasks: BatchTask[];
};

type RawTask = {
  start?: unknown;
  end?: unknown;
  reason?: unknown;
  state?: unknown;
  error?: unknown;
  engine_job_id?: unknown;
  engine?: RawStatus | null;
};

type RawBatch = {
  id?: unknown;
  status?: unknown;
  stage?: unknown;
  duration?: unknown;
  title?: unknown;
  error?: unknown;
  tasks?: RawTask[];
};

const TASK_STATES: TaskState[] = ["waiting", "cutting", "submitted", "failed"];
const BATCH_STATUSES: BatchStatus[] = ["planning", "running", "completed", "failed"];

export function mapBatch(raw: RawBatch): Batch {
  const tasks = (raw.tasks ?? []).map((task): BatchTask => {
    const jobId = text(task.engine_job_id);
    return {
      start: num(task.start),
      end: num(task.end),
      reason: text(task.reason) ?? "",
      state: TASK_STATES.includes(task.state as TaskState) ? (task.state as TaskState) : "waiting",
      error: text(task.error),
      job: jobId && task.engine ? mapJob(jobId, task.engine) : null,
    };
  });
  return {
    id: text(raw.id) ?? "",
    status: BATCH_STATUSES.includes(raw.status as BatchStatus) ? (raw.status as BatchStatus) : "planning",
    stage: text(raw.stage),
    durationSec: num(raw.duration),
    title: text(raw.title),
    error: text(raw.error),
    tasks,
  };
}

export type BatchOptions = { mode: Mode; clips: ClipCount; length: ClipLength; format?: ClipFormat };

export async function startBatch(source: ClipSource, options: BatchOptions): Promise<string> {
  const response = await engineFetch("/batches", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: source.url,
      mode: options.mode,
      clips: options.clips,
      length: options.length,
      format: options.format ?? "vertical",
      ...(source.sourceStart !== undefined && source.sourceEnd !== undefined
        ? { start: source.sourceStart, end: source.sourceEnd }
        : {}),
    }),
  });
  const body = (await response.json().catch(() => null)) as { id?: string; error?: unknown } | null;
  if (!response.ok || !body?.id) {
    const detail = typeof body?.error === "string" ? body.error : "This video could not be started.";
    throw new EngineError(detail, response.status >= 400 && response.status < 500 ? 400 : 502);
  }
  return body.id;
}

type RawPreview = { duration?: unknown; title?: unknown; long?: unknown; hotspots?: unknown; error?: unknown };

export function mapPreview(raw: RawPreview): Preview {
  const spots = Array.isArray(raw.hotspots) ? raw.hotspots : [];
  return {
    durationSec: num(raw.duration) ?? 0,
    title: text(raw.title) ?? "",
    long: raw.long === true,
    hotspots: spots
      .map((h: { t?: unknown; weight?: unknown }) => ({ t: num(h?.t), weight: num(h?.weight) }))
      .filter((h): h is { t: number; weight: number } => h.t !== null && h.weight !== null),
  };
}

export async function previewVideo(url: string): Promise<Preview> {
  const response = await engineFetch("/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  const body = (await response.json().catch(() => ({}))) as RawPreview;
  if (!response.ok) {
    const detail = typeof body.error === "string" ? body.error : "Could not read this video.";
    throw new EngineError(detail, response.status >= 400 && response.status < 500 ? 400 : 502);
  }
  return mapPreview(body);
}

export async function getBatch(id: string): Promise<Batch | null> {
  const response = await engineFetch(`/batches/${encodeURIComponent(id)}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new EngineError("Could not read the progress.", 502);
  return mapBatch((await response.json()) as RawBatch);
}

/** Streams a finished clip from the engine, passing the browser's Range header through. */
export async function fetchVideo(videoPath: string, range: string | null): Promise<Response> {
  return engineFetch(videoPath, { headers: range ? { Range: range } : undefined });
}

const JOB_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const BATCH_ID = /^[0-9a-f]{32}$/;

export function isBatchId(value: string): boolean {
  return BATCH_ID.test(value);
}
const MAX_FILE_NAME = 255;

export function isJobId(value: string): boolean {
  return JOB_ID.test(value);
}

/** A clip file name as the engine writes it: one path segment, mp4 only. */
export function isClipFileName(value: string): boolean {
  return (
    value.length <= MAX_FILE_NAME &&
    value.toLowerCase().endsWith(".mp4") &&
    !value.startsWith(".") &&
    !/[\\/\u0000-\u001f]/.test(value) &&
    !value.includes("..")
  );
}

// --------------------------------------------------------------------------- //
// Autopilot (gateway /autopilot)
// --------------------------------------------------------------------------- //
export type AutopilotItem = ClipCampaignCheck & {
  id: string;
  streamer: string;
  status: "review" | "approved" | "rejected" | "posted" | "failed";
  score: number | null;
  title: string;
  hook: string;
  description: string;
  durationSec: number | null;
  videoPath: string;
  posts: Record<string, string>;
  error: string | null;
  created: number;
  /** Title shown instead of captions, when the reviewer swapped them. */
  headline: string | null;
  /** "stacked": webcam on top, game below (gateway re-cut). "engine": the core's framing. null: no choice. */
  layout: "stacked" | "engine" | null;
  layoutError: string | null;
};

export type Autopilot = {
  postingReady: boolean;
  lastRun: number | null;
  pending: number;
  streamers: { login: string; name: string; enabled: boolean; since: string | null; hasAccounts: boolean; accounts: { user: string; name: string }[] }[];
  items: AutopilotItem[];
  campaigns: Campaign[];
  log: string[];
};

const ITEM_STATUSES = ["review", "approved", "rejected", "posted", "failed"] as const;

type RawAutopilot = {
  posting_ready?: unknown;
  last_run?: unknown;
  pending?: unknown[];
  config?: { streamers?: Record<string, unknown>[] };
  items?: Record<string, unknown>[];
  campaigns?: unknown;
  log?: unknown[];
};

export function mapAutopilot(raw: RawAutopilot): Autopilot {
  return {
    postingReady: raw.posting_ready === true,
    lastRun: num(raw.last_run),
    pending: Array.isArray(raw.pending) ? raw.pending.length : 0,
    streamers: (raw.config?.streamers ?? []).map((s) => ({
      login: text(s.login) ?? "",
      name: text(s.name) ?? text(s.login) ?? "",
      enabled: s.enabled !== false,
      since: text(s.since),
      hasAccounts: !!text(s.upload_post_user) || (Array.isArray(s.accounts) && s.accounts.length > 0),
      accounts: Array.isArray(s.accounts)
        ? s.accounts
            .filter((a): a is Record<string, unknown> => !!a && typeof a === "object")
            .map((a) => ({ user: text(a.user) ?? "", name: text(a.name) ?? text(a.user) ?? "" }))
            .filter((a) => a.user)
        : [],
    })),
    items: (raw.items ?? [])
      .map((i): AutopilotItem | null => {
        const videoPath = text(i.video_path);
        const id = text(i.id);
        if (!videoPath?.startsWith("/videos/") || !id) return null;
        const status = ITEM_STATUSES.includes(i.status as AutopilotItem["status"])
          ? (i.status as AutopilotItem["status"])
          : "review";
        const posts: Record<string, string> = {};
        if (i.posts && typeof i.posts === "object") {
          for (const [k, v] of Object.entries(i.posts as Record<string, unknown>)) {
            if (typeof v === "string") posts[k] = v;
          }
        }
        return {
          id,
          streamer: text(i.streamer) ?? "",
          status,
          score: num(i.score),
          title: text(i.title) ?? "",
          hook: text(i.hook) ?? "",
          description: text(i.description) ?? "",
          durationSec: num(i.duration),
          videoPath,
          posts,
          error: text(i.error),
          created: num(i.created) ?? 0,
          headline: text(i.headline),
          layout: i.layout === "stacked" || i.layout === "engine" ? i.layout : null,
          layoutError: text(i.layout_error),
          ...mapClipCheck(i),
        };
      })
      .filter((i): i is AutopilotItem => i !== null),
    campaigns: mapCampaigns(raw.campaigns),
    log: (raw.log ?? []).filter((l): l is string => typeof l === "string"),
  };
}

export async function getCampaigns(): Promise<Campaign[]> {
  const response = await engineFetch("/campaigns");
  if (!response.ok) throw new EngineError("Could not read the campaigns.", 502);
  return mapCampaigns(((await response.json()) as { campaigns?: unknown }).campaigns);
}

export async function getAutopilot(): Promise<Autopilot> {
  const response = await engineFetch("/autopilot");
  if (!response.ok) throw new EngineError("Could not read the autopilot.", 502);
  return mapAutopilot((await response.json()) as RawAutopilot);
}

export const AUTOPILOT_ACTIONS = ["post", "reject", "unreject", "toggle_campaign", "headline", "captions", "layout"] as const;
export type AutopilotAction = (typeof AUTOPILOT_ACTIONS)[number];

/** `target`: the campaign id for toggle_campaign, the channel (Upload-Post profile) for post. */
export async function actOnAutopilotItem(id: string, action: AutopilotAction, target?: string, text?: string): Promise<void> {
  const response = await engineFetch(`/autopilot/items/${encodeURIComponent(id)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, ...(target ? { campaign: target } : {}), ...(text !== undefined ? { text } : {}) }),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { error?: unknown };
    throw new EngineError(typeof body.error === "string" ? body.error : "Could not update the clip.", response.status === 404 ? 404 : 400);
  }
}
