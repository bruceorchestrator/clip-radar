import { describe, expect, it } from "vitest";
import { kickLanguageCode, mapKickClip, type KickClip } from "./kick";
import { mapTwitchClip, type TwitchClipNode } from "./twitch";

function twitchNode(overrides: Partial<TwitchClipNode> = {}): TwitchClipNode {
  return {
    slug: "SmoggyFaintMeatloaf",
    title: "Five stars",
    viewCount: 272,
    createdAt: "2026-11-17T10:00:16Z",
    durationSeconds: 30,
    videoOffsetSeconds: 24526,
    url: "https://www.twitch.tv/someone/clip/SmoggyFaintMeatloaf",
    thumbnailURL: "https://static-cdn.jtvnw.net/thumb.jpg",
    language: "EN",
    broadcaster: { login: "someone", displayName: "Someone" },
    curator: { login: "viewer" },
    video: { id: "2931112992" },
    ...overrides,
  };
}

function kickClip(overrides: Partial<KickClip> = {}): KickClip {
  return {
    id: "clip_01ABC",
    livestream_id: "138202416",
    title: "SPEED GOT SCAMMED",
    thumbnail_url: "https://clips.kick.com/thumb.webp",
    views: 89,
    duration: 30,
    created_at: "2026-11-16T17:33:57.000000Z",
    creator: { username: "viewer" },
    channel: { username: "Streamer", slug: "streamer" },
    ...overrides,
  };
}

describe("mapTwitchClip", () => {
  it("uses the recording position when the clip has one", () => {
    const clip = mapTwitchClip(twitchNode());
    expect(clip).toMatchObject({
      id: "SmoggyFaintMeatloaf",
      platform: "twitch",
      views: 272,
      language: "en",
      streamKey: "twitch:vod:2931112992",
      timeBasis: "vod",
      startSec: 24526,
      clipper: "viewer",
    });
  });

  it("falls back to the creation time when the recording is gone", () => {
    const clip = mapTwitchClip(twitchNode({ video: null, videoOffsetSeconds: null }));
    const createdSec = Date.parse("2026-11-17T10:00:16Z") / 1000;
    expect(clip).toMatchObject({
      streamKey: "twitch:live:someone",
      timeBasis: "wall",
      startSec: createdSec - 30,
    });
  });

  it("treats an offset without a recording as creation-time based", () => {
    const clip = mapTwitchClip(twitchNode({ video: null }));
    expect(clip?.timeBasis).toBe("wall");
  });

  it("drops a clip whose channel is gone", () => {
    expect(mapTwitchClip(twitchNode({ broadcaster: null }))).toBeNull();
  });

  it("keeps a missing language and curator as null", () => {
    const clip = mapTwitchClip(twitchNode({ language: null, curator: null }));
    expect(clip?.language).toBeNull();
    expect(clip?.clipper).toBeNull();
  });
});

describe("mapKickClip", () => {
  it("builds the public clip link and a creation-time position", () => {
    const clip = mapKickClip(kickClip(), "en");
    const createdSec = Math.floor(Date.parse("2026-11-16T17:33:57.000000Z") / 1000);
    expect(clip).toMatchObject({
      id: "clip_01ABC",
      platform: "kick",
      url: "https://kick.com/streamer/clips/clip_01ABC",
      streamKey: "kick:138202416",
      timeBasis: "wall",
      startSec: createdSec - 30,
      language: "en",
      streamer: { login: "streamer", name: "Streamer" },
    });
  });

  it("keeps an unknown language and a missing creator as null", () => {
    const clip = mapKickClip(kickClip({ creator: null }), null);
    expect(clip.language).toBeNull();
    expect(clip.clipper).toBeNull();
  });
});

describe("kickLanguageCode", () => {
  it("maps language names to codes", () => {
    expect(kickLanguageCode("English")).toBe("en");
    expect(kickLanguageCode(" Portuguese ")).toBe("pt");
  });

  it("keeps an unlisted language as its lowercase name", () => {
    expect(kickLanguageCode("Klingon")).toBe("klingon");
  });

  it("returns null for a missing language", () => {
    expect(kickLanguageCode(null)).toBeNull();
    expect(kickLanguageCode("")).toBeNull();
  });
});
