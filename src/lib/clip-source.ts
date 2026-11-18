import type { ClipSource, Moment } from "./types";

/** The engine refuses sources shorter than this. */
export const ENGINE_MIN_SOURCE_SEC = 45;
/** Lead-in and tail around a moment, so the engine can pick its own start and end. */
const PAD_BEFORE_SEC = 25;
const PAD_AFTER_SEC = 15;
const MIN_WINDOW_SEC = 75;
const MAX_WINDOW_SEC = 240;

/**
 * Turns a radar moment into something the engine can cut.
 * Prefers a stretch of the stream recording around the moment; falls back to
 * the viewer's own clip when it is long enough. Returns null when neither works.
 */
export function clipSourceFor(moment: Moment): ClipSource | null {
  const onRecording = moment.clips.filter(
    (clip) => clip.timeBasis === "vod" && clip.vodUrl !== null,
  );
  if (onRecording.length > 0) {
    const start = Math.min(...onRecording.map((clip) => clip.startSec));
    const end = Math.max(...onRecording.map((clip) => clip.startSec + clip.durationSec));
    const sourceStart = Math.max(0, Math.floor(start - PAD_BEFORE_SEC));
    const wanted = Math.ceil(end + PAD_AFTER_SEC) - sourceStart;
    const length = Math.min(MAX_WINDOW_SEC, Math.max(MIN_WINDOW_SEC, wanted));
    return { url: onRecording[0].vodUrl!, sourceStart, sourceEnd: sourceStart + length };
  }
  const longEnough = moment.clips.find((clip) => clip.durationSec >= ENGINE_MIN_SOURCE_SEC);
  return longEnough ? { url: longEnough.url } : null;
}

const ALLOWED_HOSTS = ["twitch.tv", "kick.com", "youtube.com", "youtu.be"];

/** Only links to the platforms we support may be sent to the engine. */
export function isSupportedSourceUrl(value: string): boolean {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return false;
  }
  if (url.protocol !== "https:") return false;
  const host = url.hostname.toLowerCase();
  return ALLOWED_HOSTS.some((allowed) => host === allowed || host.endsWith(`.${allowed}`));
}

/** Builds the link to the clip form, prefilled from a source. */
export function clipFormHref(source: ClipSource): string {
  const query = new URLSearchParams({ url: source.url });
  if (source.sourceStart !== undefined) query.set("start", String(source.sourceStart));
  if (source.sourceEnd !== undefined) query.set("end", String(source.sourceEnd));
  return `/clip?${query}`;
}
