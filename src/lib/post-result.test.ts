import { describe, expect, it } from "vitest";
import type { AutopilotItem } from "@/lib/engine";
import { postResult } from "./post-result";

const item = (over: Partial<AutopilotItem>) => ({ status: "posted", posts: {}, error: null, ...over }) as unknown as AutopilotItem;

describe("postResult", () => {
  it("links the video on the channel that was pressed", () => {
    const notice = postResult(item({ posts: { "LACY Clips youtube": "https://www.youtube.com/watch?v=abc", "GtaGeek youtube": "https://x" } }), "LACY Clips");
    expect(notice).toEqual({ kind: "ok", text: "Posted to LACY Clips.", url: "https://www.youtube.com/watch?v=abc" });
  });

  it("shows the engine's reason when posting failed", () => {
    const notice = postResult(item({ status: "failed", error: "quota exceeded" }), "GtaGeek");
    expect(notice.kind).toBe("bad");
    expect(notice.text).toContain("quota exceeded");
  });

  it("says where to look when the upload is still running", () => {
    expect(postResult(item({ status: "approved" }), "GtaGeek").text).toContain("Posted");
    expect(postResult(undefined, "GtaGeek").kind).toBe("ok");
  });
});
