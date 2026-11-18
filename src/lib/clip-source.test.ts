import { describe, expect, it } from "vitest";
import { clipFormHref, clipSourceFor, isSupportedSourceUrl } from "./clip-source";
import { groupMoments } from "./moments";
import type { Clip } from "./types";

const NOW = new Date("2026-11-18T12:00:00Z");

function clip(overrides: Partial<Clip> & { id: string }): Clip {
  return {
    platform: "twitch",
    title: overrides.id,
    url: `https://www.twitch.tv/someone/clip/${overrides.id}`,
    thumbnailUrl: null,
    views: 100,
    durationSec: 30,
    createdAt: "2026-11-18T10:00:00Z",
    language: "en",
    streamer: { login: "someone", name: "Someone" },
    clipper: null,
    streamKey: "twitch:vod:9",
    timeBasis: "vod",
    startSec: 1000,
    vodUrl: "https://www.twitch.tv/videos/9",
    ...overrides,
  };
}

function momentOf(clips: Clip[]) {
  return groupMoments(clips, NOW)[0];
}

describe("clipSourceFor", () => {
  it("cuts a padded stretch of the recording around the moment", () => {
    const source = clipSourceFor(
      momentOf([clip({ id: "a", startSec: 1000 }), clip({ id: "b", startSec: 1020 })]),
    );
    expect(source).toEqual({
      url: "https://www.twitch.tv/videos/9",
      sourceStart: 975,
      sourceEnd: 975 + 90,
    });
  });

  it("never asks for less than the minimum stretch", () => {
    const source = clipSourceFor(momentOf([clip({ id: "a", startSec: 500, durationSec: 10 })]));
    expect(source!.sourceEnd! - source!.sourceStart!).toBe(75);
  });

  it("never asks for more than the maximum stretch", () => {
    const source = clipSourceFor(momentOf([clip({ id: "a", startSec: 500, durationSec: 239 })]));
    expect(source!.sourceEnd! - source!.sourceStart!).toBe(240);
  });

  it("does not start before the beginning of the recording", () => {
    const source = clipSourceFor(momentOf([clip({ id: "a", startSec: 5 })]));
    expect(source!.sourceStart).toBe(0);
  });

  it("falls back to the viewer clip when there is no recording", () => {
    const wall = clip({
      id: "k",
      platform: "kick",
      url: "https://kick.com/streamer/clips/k",
      timeBasis: "wall",
      streamKey: "kick:1",
      vodUrl: null,
      durationSec: 60,
    });
    expect(clipSourceFor(momentOf([wall]))).toEqual({ url: "https://kick.com/streamer/clips/k" });
  });

  it("returns null when the only clip is too short and has no recording", () => {
    const short = clip({ id: "s", timeBasis: "wall", streamKey: "twitch:live:x", vodUrl: null });
    expect(clipSourceFor(momentOf([short]))).toBeNull();
  });
});

describe("isSupportedSourceUrl", () => {
  it("accepts the supported platforms and their subdomains", () => {
    expect(isSupportedSourceUrl("https://www.twitch.tv/videos/9")).toBe(true);
    expect(isSupportedSourceUrl("https://kick.com/streamer/clips/k")).toBe(true);
    expect(isSupportedSourceUrl("https://youtu.be/abc")).toBe(true);
  });

  it("rejects other hosts, lookalikes, plain http and junk", () => {
    expect(isSupportedSourceUrl("https://example.com/video")).toBe(false);
    expect(isSupportedSourceUrl("https://twitch.tv.evil.com/videos/9")).toBe(false);
    expect(isSupportedSourceUrl("https://nottwitch.tv/videos/9")).toBe(false);
    expect(isSupportedSourceUrl("http://www.twitch.tv/videos/9")).toBe(false);
    expect(isSupportedSourceUrl("http://127.0.0.1:8000/health")).toBe(false);
    expect(isSupportedSourceUrl("not a link")).toBe(false);
  });
});

describe("clipFormHref", () => {
  it("carries the link and the stretch", () => {
    expect(clipFormHref({ url: "https://www.twitch.tv/videos/9", sourceStart: 10, sourceEnd: 100 })).toBe(
      "/clip?url=https%3A%2F%2Fwww.twitch.tv%2Fvideos%2F9&start=10&end=100",
    );
  });

  it("omits the stretch when there is none", () => {
    expect(clipFormHref({ url: "https://kick.com/s/clips/k" })).toBe(
      "/clip?url=https%3A%2F%2Fkick.com%2Fs%2Fclips%2Fk",
    );
  });
});
