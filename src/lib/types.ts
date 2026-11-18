export type Platform = "twitch" | "kick";
export type Period = "day" | "week";

/**
 * How `startSec` is measured.
 * - "vod": seconds from the start of the stream recording (exact).
 * - "wall": unix seconds derived from the clip creation time (approximate:
 *   a viewer makes the clip some seconds after the moment happens).
 */
export type TimeBasis = "vod" | "wall";

export type Clip = {
  id: string;
  platform: Platform;
  title: string;
  url: string;
  thumbnailUrl: string | null;
  views: number;
  durationSec: number;
  createdAt: string; // ISO 8601
  /** Lowercase ISO 639-1 code ("en") when known, otherwise null. */
  language: string | null;
  streamer: { login: string; name: string };
  clipper: string | null;
  /** Clips with the same key come from the same stream and share a timeline. */
  streamKey: string;
  timeBasis: TimeBasis;
  startSec: number;
  /** Link to the full stream recording when the platform exposes one. */
  vodUrl: string | null;
};

export type Moment = {
  id: string;
  platform: Platform;
  streamer: { login: string; name: string };
  /** The most viewed version of this moment. */
  top: Clip;
  /** Every version of this moment, most viewed first. */
  clips: Clip[];
  clippedTimes: number;
  totalViews: number;
  firstClippedAt: string;
  viewsPerHour: number;
};

export type MomentSort = "views" | "clipped" | "rising";

/** What the clipping engine is asked to cut: a link, and optionally a stretch of it. */
export type ClipSource = {
  url: string;
  sourceStart?: number;
  sourceEnd?: number;
};
