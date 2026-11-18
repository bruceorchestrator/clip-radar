import { cacheLife } from "next/cache";
import { filterEnglish, groupMoments } from "./moments";
import { fetchKickClips } from "./sources/kick";
import { fetchTwitchClips } from "./sources/twitch";
import type { Clip, Moment, Period, Platform } from "./types";

export type SourceStatus = {
  platform: Platform;
  ok: boolean;
  clipCount: number;
  error: string | null;
};

export type Radar = {
  moments: Moment[];
  sources: SourceStatus[];
  fetchedAt: string;
};

/** Live clips from every source, grouped into moments. One source failing never blanks the page. */
export async function getRadar(period: Period, englishOnly: boolean): Promise<Radar> {
  "use cache";
  cacheLife("minutes");

  const fetchers: [Platform, Promise<Clip[]>][] = [
    ["twitch", fetchTwitchClips(period)],
    ["kick", fetchKickClips(period)],
  ];
  const settled = await Promise.allSettled(fetchers.map(([, promise]) => promise));

  const clips: Clip[] = [];
  const sources: SourceStatus[] = settled.map((result, index) => {
    const platform = fetchers[index][0];
    if (result.status === "rejected") {
      const error = result.reason instanceof Error ? result.reason.message : "unknown error";
      return { platform, ok: false, clipCount: 0, error };
    }
    const kept = englishOnly ? filterEnglish(result.value) : result.value;
    clips.push(...kept);
    return { platform, ok: true, clipCount: kept.length, error: null };
  });

  const now = new Date();
  return { moments: groupMoments(clips, now), sources, fetchedAt: now.toISOString() };
}
