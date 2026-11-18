import { describe, expect, it } from "vitest";
import { filterEnglish, groupMoments, sortMoments } from "./moments";
import type { Clip } from "./types";

const NOW = new Date("2026-11-18T12:00:00Z");

function clip(overrides: Partial<Clip> & { id: string }): Clip {
  return {
    platform: "twitch",
    title: overrides.id,
    url: `https://example.test/${overrides.id}`,
    thumbnailUrl: null,
    views: 100,
    durationSec: 30,
    createdAt: "2026-11-18T10:00:00Z",
    language: "en",
    streamer: { login: "streamer", name: "Streamer" },
    clipper: null,
    streamKey: "twitch:vod:1",
    timeBasis: "vod",
    startSec: 0,
    vodUrl: "https://www.twitch.tv/videos/1",
    ...overrides,
  };
}

describe("groupMoments", () => {
  it("folds overlapping clips of one stream into one moment", () => {
    const moments = groupMoments(
      [
        clip({ id: "a", startSec: 100, views: 50 }),
        clip({ id: "b", startSec: 110, views: 300 }),
        clip({ id: "c", startSec: 125, views: 10 }),
      ],
      NOW,
    );
    expect(moments).toHaveLength(1);
    expect(moments[0].clippedTimes).toBe(3);
    expect(moments[0].totalViews).toBe(360);
    expect(moments[0].top.id).toBe("b");
    expect(moments[0].clips.map((c) => c.id)).toEqual(["b", "a", "c"]);
  });

  it("keeps clips that do not overlap as separate moments", () => {
    const moments = groupMoments(
      [clip({ id: "a", startSec: 0 }), clip({ id: "b", startSec: 30 })],
      NOW,
    );
    expect(moments).toHaveLength(2);
  });

  it("never joins clips from different streams", () => {
    const moments = groupMoments(
      [
        clip({ id: "a", startSec: 100, streamKey: "twitch:vod:1" }),
        clip({ id: "b", startSec: 100, streamKey: "twitch:vod:2" }),
      ],
      NOW,
    );
    expect(moments).toHaveLength(2);
  });

  it("allows a short gap for wall-clock clips but not for exact ones", () => {
    const wall = groupMoments(
      [
        clip({ id: "a", timeBasis: "wall", streamKey: "kick:1", startSec: 1000 }),
        clip({ id: "b", timeBasis: "wall", streamKey: "kick:1", startSec: 1040 }),
      ],
      NOW,
    );
    expect(wall).toHaveLength(1);

    const exact = groupMoments(
      [clip({ id: "a", startSec: 1000 }), clip({ id: "b", startSec: 1040 })],
      NOW,
    );
    expect(exact).toHaveLength(2);
  });

  it("stops a chain of overlaps from swallowing a later moment", () => {
    const chain = Array.from({ length: 12 }, (_, i) =>
      clip({ id: `c${i}`, startSec: i * 25 }),
    );
    const moments = groupMoments(chain, NOW);
    expect(moments.length).toBeGreaterThan(1);
    for (const moment of moments) {
      const starts = moment.clips.map((c) => c.startSec);
      const ends = moment.clips.map((c) => c.startSec + c.durationSec);
      expect(Math.max(...ends) - Math.min(...starts)).toBeLessThanOrEqual(240);
    }
  });

  it("counts the same clip once when a source returns it twice", () => {
    const moments = groupMoments(
      [clip({ id: "a", startSec: 10 }), clip({ id: "a", startSec: 10 })],
      NOW,
    );
    expect(moments).toHaveLength(1);
    expect(moments[0].clippedTimes).toBe(1);
    expect(moments[0].totalViews).toBe(100);
  });

  it("returns nothing for no clips", () => {
    expect(groupMoments([], NOW)).toEqual([]);
  });

  it("computes views per hour from the first clip and floors the age", () => {
    const twoHoursOld = groupMoments(
      [clip({ id: "a", views: 1000, createdAt: "2026-11-18T10:00:00Z" })],
      NOW,
    );
    expect(twoHoursOld[0].viewsPerHour).toBe(500);

    const justNow = groupMoments(
      [clip({ id: "b", views: 1000, createdAt: "2026-11-18T11:59:00Z" })],
      NOW,
    );
    expect(justNow[0].viewsPerHour).toBe(2000);
  });
});

describe("sortMoments", () => {
  const moments = groupMoments(
    [
      clip({ id: "big", streamKey: "s1", startSec: 0, views: 5000, createdAt: "2026-11-17T12:00:00Z" }),
      clip({ id: "pop1", streamKey: "s2", startSec: 0, views: 400 }),
      clip({ id: "pop2", streamKey: "s2", startSec: 5, views: 300 }),
      clip({ id: "pop3", streamKey: "s2", startSec: 9, views: 200 }),
      clip({ id: "fresh", streamKey: "s3", startSec: 0, views: 800, createdAt: "2026-11-18T11:45:00Z" }),
    ],
    NOW,
  );

  it("orders by total views", () => {
    expect(sortMoments(moments, "views").map((m) => m.top.id)).toEqual(["big", "pop1", "fresh"]);
  });

  it("orders by how many times a moment was clipped", () => {
    expect(sortMoments(moments, "clipped")[0].top.id).toBe("pop1");
  });

  it("orders by views per hour", () => {
    expect(sortMoments(moments, "rising")[0].top.id).toBe("fresh");
  });

  it("does not mutate the input", () => {
    const before = moments.map((m) => m.id);
    sortMoments(moments, "rising");
    expect(moments.map((m) => m.id)).toEqual(before);
  });
});

describe("filterEnglish", () => {
  it("keeps only clips known to be English", () => {
    const kept = filterEnglish([
      clip({ id: "en", language: "en" }),
      clip({ id: "es", language: "es" }),
      clip({ id: "unknown", language: null }),
    ]);
    expect(kept.map((c) => c.id)).toEqual(["en"]);
  });
});
