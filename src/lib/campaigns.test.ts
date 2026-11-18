import { describe, expect, it } from "vitest";
import { mapCampaigns, mapClipCheck } from "./campaigns";

describe("mapCampaigns", () => {
  it("maps gateway briefs and drops broken ones", () => {
    const out = mapCampaigns([
      { id: "reach-lacy-gta", name: "LACY pool", hashtags: ["#LACY", 3], min_total_views: 750000, rules_url: "https://reachclipping.com/LACYGTA" },
      { name: "no id" },
      null,
    ]);
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ id: "reach-lacy-gta", hashtags: ["#LACY"], minTotalViews: 750000, rulesUrl: "https://reachclipping.com/LACYGTA" });
  });

  it("returns nothing for junk", () => {
    expect(mapCampaigns("x")).toEqual([]);
  });
});

describe("mapClipCheck", () => {
  it("maps every campaign a clip can go to", () => {
    const out = mapClipCheck({
      campaigns: [
        { campaign: { id: "lacy", name: "LACY", submit_within_min: 30 }, selected: true, primary: true, verdict: "manual",
          checks: [{ rule: "Caption has #LACY", ok: true, detail: "" }, { rule: "No logos", ok: null }, { ok: true }] },
        { campaign: { id: "core", name: "CORE" }, selected: false, primary: false, verdict: "fail",
          checks: [{ rule: "Footage date", ok: false, detail: "stream started 2026-11-17" }] },
        { campaign: { name: "no id" } },
      ],
      verdict: "manual",
      text: { caption: "LACY: hi\n\n#LACY" },
    });
    expect(out.verdict).toBe("manual");
    expect(out.caption).toBe("LACY: hi\n\n#LACY");
    expect(out.campaigns.map((c) => [c.campaign.id, c.selected, c.primary, c.verdict])).toEqual([
      ["lacy", true, true, "manual"],
      ["core", false, false, "fail"],
    ]);
    expect(out.campaigns[0].checks.map((c) => c.ok)).toEqual([true, null]);
    expect(out.campaigns[0].campaign.submitWithinMin).toBe(30);
  });

  it("treats missing data as no campaign", () => {
    expect(mapClipCheck({})).toEqual({ campaigns: [], verdict: "none", caption: null });
  });
});
