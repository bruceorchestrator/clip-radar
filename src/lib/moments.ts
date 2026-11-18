import type { Clip, Moment, MomentSort } from "./types";

/** Wall-clock clips are created a little after the moment, so allow a gap. */
const WALL_SLACK_SEC = 15;
/** A chain of overlapping clips never grows past this, so two moments stay apart. */
const MAX_SPAN_SEC = 240;
/** Floor for the age used in views per hour, so a brand-new clip is not infinite. */
const MIN_AGE_HOURS = 0.5;

type Cluster = { startSec: number; endSec: number; clips: Clip[] };

function dedupeById(clips: Clip[]): Clip[] {
  const seen = new Map<string, Clip>();
  for (const clip of clips) {
    const key = `${clip.platform}:${clip.id}`;
    if (!seen.has(key)) seen.set(key, clip);
  }
  return [...seen.values()];
}

function clusterStream(clips: Clip[]): Cluster[] {
  const sorted = [...clips].sort((a, b) => a.startSec - b.startSec);
  const clusters: Cluster[] = [];
  for (const clip of sorted) {
    const endSec = clip.startSec + clip.durationSec;
    const slack = clip.timeBasis === "wall" ? WALL_SLACK_SEC : 0;
    const current = clusters.at(-1);
    const overlaps = current !== undefined && clip.startSec < current.endSec + slack;
    const fits =
      current !== undefined &&
      Math.max(current.endSec, endSec) - current.startSec <= MAX_SPAN_SEC;
    if (current && overlaps && fits) {
      current.endSec = Math.max(current.endSec, endSec);
      current.clips.push(clip);
    } else {
      clusters.push({ startSec: clip.startSec, endSec, clips: [clip] });
    }
  }
  return clusters;
}

function toMoment(cluster: Cluster, now: Date): Moment {
  const clips = [...cluster.clips].sort((a, b) => b.views - a.views);
  const top = clips[0];
  const totalViews = clips.reduce((sum, clip) => sum + clip.views, 0);
  const firstClippedAt = clips
    .map((clip) => clip.createdAt)
    .reduce((min, value) => (value < min ? value : min));
  const ageHours = Math.max(
    MIN_AGE_HOURS,
    (now.getTime() - new Date(firstClippedAt).getTime()) / 3_600_000,
  );
  return {
    id: `${top.platform}:${top.id}`,
    platform: top.platform,
    streamer: top.streamer,
    top,
    clips,
    clippedTimes: clips.length,
    totalViews,
    firstClippedAt,
    viewsPerHour: Math.round(totalViews / ageHours),
  };
}

/**
 * Folds clips of the same stream moment into one Moment.
 * Two clips are the same moment when they come from the same stream and
 * their time ranges overlap.
 */
export function groupMoments(clips: Clip[], now: Date): Moment[] {
  const byStream = new Map<string, Clip[]>();
  for (const clip of dedupeById(clips)) {
    const list = byStream.get(clip.streamKey);
    if (list) list.push(clip);
    else byStream.set(clip.streamKey, [clip]);
  }
  const moments: Moment[] = [];
  for (const streamClips of byStream.values()) {
    for (const cluster of clusterStream(streamClips)) {
      moments.push(toMoment(cluster, now));
    }
  }
  return moments;
}

export function sortMoments(moments: Moment[], sort: MomentSort): Moment[] {
  const byViews = (a: Moment, b: Moment) => b.totalViews - a.totalViews;
  const compare: Record<MomentSort, (a: Moment, b: Moment) => number> = {
    views: byViews,
    clipped: (a, b) => b.clippedTimes - a.clippedTimes || byViews(a, b),
    rising: (a, b) => b.viewsPerHour - a.viewsPerHour || byViews(a, b),
  };
  return [...moments].sort(compare[sort]);
}

export function filterEnglish(clips: Clip[]): Clip[] {
  return clips.filter((clip) => clip.language === "en");
}
