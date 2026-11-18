import { describe, expect, it } from "vitest";
import { isBatchId, isClipFileName, isJobId, mapAutopilot, mapBatch, mapJob, mapJobClip, pickProgress } from "./engine";

const JOB = "56549b68-baca-4d70-a27a-78897abcfb88";
const FILE = "subtitled_1794963065_GTA_6_IS_HERE!!!_!SERVER_!DISCORD_!SUB__clip_1.mp4";

// Trimmed from a real engine response (18.11, Jefe stream).
const REAL_CLIP = {
  start: 298.97,
  end: 355.6,
  predicted_score: 92,
  video_description_for_tiktok: "He actually found Grand Theft Auto 6 early on stream! #gta6",
  video_title_for_youtube_short: "He Showed GTA 6 Early on Stream!",
  viral_hook_text: "We have Grand Theft Auto 6, boom, we have it.",
  video_url: `/videos/${JOB}/${FILE}`,
};

describe("mapJobClip", () => {
  it("maps a real engine clip", () => {
    const clip = mapJobClip(REAL_CLIP, 0);
    expect(clip).toEqual({
      index: 0,
      title: "He Showed GTA 6 Early on Stream!",
      description: "He actually found Grand Theft Auto 6 early on stream! #gta6",
      hook: "We have Grand Theft Auto 6, boom, we have it.",
      score: 92,
      durationSec: expect.closeTo(56.63, 2),
      videoPath: `/videos/${JOB}/${FILE}`,
    });
  });

  it("falls back to a numbered title and empty fields", () => {
    const clip = mapJobClip({ video_url: `/videos/${JOB}/a.mp4` }, 2);
    expect(clip).toMatchObject({ title: "Clip 3", description: null, hook: null, score: null, durationSec: null });
  });

  it("drops a clip whose video is missing or points outside /videos/", () => {
    expect(mapJobClip({}, 0)).toBeNull();
    expect(mapJobClip({ video_url: "https://evil.example/x.mp4" }, 0)).toBeNull();
  });
});

describe("mapJob", () => {
  it("keeps known statuses and treats anything else as processing", () => {
    expect(mapJob(JOB, { status: "completed", result: { clips: [REAL_CLIP] } }).status).toBe("completed");
    expect(mapJob(JOB, { status: "failed" }).status).toBe("failed");
    expect(mapJob(JOB, { status: "queued" }).status).toBe("queued");
    expect(mapJob(JOB, { status: "done" }).status).toBe("processing");
    expect(mapJob(JOB, {}).clips).toEqual([]);
  });
});

describe("pickProgress", () => {
  it("returns a fixed message for the latest stage, never the raw line", () => {
    const logs = [
      "📥 Downloading video…",
      "✅ Video downloaded",
      "🎙️ Transcribing… 50% (98s)",
      "/app/scene_detection.py:123: UserWarning: something internal",
    ];
    expect(pickProgress(logs)).toBe("Transcribing… 50%");
  });

  it("counts the moments found", () => {
    expect(pickProgress(["🔥 Found 2 clips!"])).toBe("Found 2 moments. Rendering…");
    expect(pickProgress(["🔥 Found 1 clip!"])).toBe("Found 1 moment. Rendering…");
  });

  it("never surfaces tracebacks or file paths", () => {
    const logs = [
      "📝 [Job Output] yt_dlp.utils.DownloadError: ERROR: Sign in to confirm",
      "✅ Clip saved to output/abc/secret_path.mp4",
      "📊 [job-cpu] {\"wall_s\": 6.4}",
    ];
    expect(pickProgress(logs)).toBeNull();
  });

  it("ignores non-string entries and empty logs", () => {
    expect(pickProgress([null, 3, {}])).toBeNull();
    expect(pickProgress([])).toBeNull();
  });
});

describe("isJobId", () => {
  it("accepts engine job ids only", () => {
    expect(isJobId(JOB)).toBe(true);
    expect(isJobId("../etc/passwd")).toBe(false);
    expect(isJobId("abc")).toBe(false);
  });
});

describe("isClipFileName", () => {
  it("accepts the engine's real file names, including unicode titles", () => {
    expect(isClipFileName(FILE)).toBe(true);
    expect(isClipFileName("subtitled_1_Fin_de_la_misión_clip_2.mp4")).toBe(true);
  });

  it("rejects traversal, other folders, hidden files and other types", () => {
    expect(isClipFileName("../app.py")).toBe(false);
    expect(isClipFileName("a/b.mp4")).toBe(false);
    expect(isClipFileName("a\\b.mp4")).toBe(false);
    expect(isClipFileName(".hidden.mp4")).toBe(false);
    expect(isClipFileName("x..mp4")).toBe(false);
    expect(isClipFileName("clip.mov")).toBe(false);
    expect(isClipFileName("a\u0000.mp4")).toBe(false);
    expect(isClipFileName(`${"a".repeat(260)}.mp4`)).toBe(false);
  });
});

describe("mapBatch", () => {
  // Shape trimmed from a real gateway reply (18.11, Lirik 6.4 h stream).
  const RAW = {
    id: "bec03c3c114c4b68a0a36b3df1ec16fa",
    status: "running",
    stage: "Cutting the stretches…",
    duration: 22940,
    title: "NEXT STREAM MONDAY",
    error: null,
    tasks: [
      { start: 450, end: 630, reason: "viewers clipped here", state: "submitted", error: null,
        engine_job_id: JOB, engine: { status: "completed", logs: ["🔥 Found 1 clips!"], result: { clips: [REAL_CLIP] } } },
      { start: 828, end: 1008, reason: "viewers clipped here", state: "cutting", error: null, engine_job_id: null, engine: null },
      { start: 1014, end: 1194, reason: "loud reaction", state: "failed", error: "the stretch could not be downloaded", engine_job_id: null },
    ],
  };

  it("maps the batch and each stretch", () => {
    const batch = mapBatch(RAW);
    expect(batch).toMatchObject({ id: RAW.id, status: "running", stage: "Cutting the stretches…", durationSec: 22940, title: "NEXT STREAM MONDAY" });
    expect(batch.tasks.map((t) => t.state)).toEqual(["submitted", "cutting", "failed"]);
    expect(batch.tasks[0].job?.clips[0].score).toBe(92);
    expect(batch.tasks[1].job).toBeNull();
    expect(batch.tasks[2].error).toBe("the stretch could not be downloaded");
  });

  it("falls back on unknown states instead of trusting them", () => {
    const batch = mapBatch({ status: "exploded", tasks: [{ state: "weird" }] });
    expect(batch.status).toBe("planning");
    expect(batch.tasks[0].state).toBe("waiting");
    expect(batch.tasks[0].start).toBeNull();
  });
});

describe("isBatchId", () => {
  it("accepts gateway batch ids only", () => {
    expect(isBatchId("bec03c3c114c4b68a0a36b3df1ec16fa")).toBe(true);
    expect(isBatchId(JOB)).toBe(false);
    expect(isBatchId("../batches")).toBe(false);
  });
});

describe("mapAutopilot", () => {
  it("maps the gateway snapshot and drops broken items", () => {
    const data = mapAutopilot({
      posting_ready: false,
      last_run: 1795000000,
      pending: [{}, {}],
      config: { streamers: [{ login: "lacy", name: "LACY", enabled: true, upload_post_user: null }, { login: "clix", name: "Clix", enabled: false }] },
      items: [
        { id: "a".repeat(32), streamer: "lacy", status: "review", score: 85, title: "t", hook: "h", video_path: "/videos/j/a.mp4", posts: {}, duration: 30 },
        { id: "b".repeat(32), status: "posted", video_path: "/videos/j/b.mp4", posts: { tiktok: "https://tiktok.com/x", bad: 5 } },
        { id: "c".repeat(32), video_path: "https://evil/x.mp4" },
        { status: "review", video_path: "/videos/j/d.mp4" },
      ],
      log: ["one", 2],
    });
    expect(data.postingReady).toBe(false);
    expect(data.pending).toBe(2);
    expect(data.streamers).toEqual([
      { login: "lacy", name: "LACY", enabled: true, since: null, hasAccounts: false, accounts: [] },
      { login: "clix", name: "Clix", enabled: false, since: null, hasAccounts: false, accounts: [] },
    ]);
    expect(data.items.map((i) => i.id[0])).toEqual(["a", "b"]);
    expect(data.items[1].posts).toEqual({ tiktok: "https://tiktok.com/x" });
    expect(data.log).toEqual(["one"]);
  });

  it("maps the channels a streamer can post to", () => {
    const data = mapAutopilot({
      config: { streamers: [{ login: "lacy", accounts: [{ user: "default", name: "Main Clips" }, { user: "second" }, { name: "no user" }, 3] }] },
    });
    expect(data.streamers[0].accounts).toEqual([{ user: "default", name: "Main Clips" }, { user: "second", name: "second" }]);
    expect(data.streamers[0].hasAccounts).toBe(true);
  });
});
