import { describe, expect, it } from "vitest";
import { applyForm, formWarnings, toForm } from "./campaign-form";

const DRAFT = {
  id: "reach-core", name: "$20,000 CORE Pool", source_channels: [], source_since: "2026-11-18T00:00:00Z",
  platforms: ["tiktok", "youtube"], must_mention: "CORE", hashtags: ["#CORE"], submit_within_min: 30,
  min_total_views: 2000000, min_sec: null, max_sec: null, payout: "Pool", manual: ["At least 2 CORE members"],
  rules_url: "https://reachclipping.com/CORE",
};

describe("campaign form", () => {
  it("round-trips a draft and keeps fields the form does not show", () => {
    const out = applyForm(DRAFT, toForm(DRAFT));
    expect(out).toMatchObject({ id: "reach-core", rules_url: "https://reachclipping.com/CORE", source_since: "2026-11-18",
      min_total_views: 2000000, hashtags: ["#CORE"], manual: ["At least 2 CORE members"], min_sec: null });
  });

  it("parses what a person types", () => {
    const form = { ...toForm(DRAFT), channels: "Lacy, jasontheween  marlon", minTotalViews: "750,000", hashtags: "#CORE, #LACY",
      platforms: ["tiktok", "myspace"], manual: "one\n\n two \n", since: "soon" };
    const out = applyForm(DRAFT, form);
    expect(out.source_channels).toEqual(["lacy", "jasontheween", "marlon"]);
    expect(out.min_total_views).toBe(750000);
    expect(out.hashtags).toEqual(["#CORE", "#LACY"]);
    expect(out.platforms).toEqual(["tiktok"]);
    expect(out.manual).toEqual(["one", "two"]);
    expect(out.source_since).toBeNull();
  });

  it("warns when clips could not be matched to the campaign", () => {
    expect(formWarnings(toForm(DRAFT))[0]).toMatch(/No streamer channel/);
    expect(formWarnings({ ...toForm(DRAFT), channels: "lacy" })).toEqual([]);
  });
});
