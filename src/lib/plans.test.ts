import { describe, expect, it } from "vitest";
import { PLANS, TOP_UP, creditsFor, planById } from "./plans";

describe("plans", () => {
  it("matches the approved prices and minutes", () => {
    expect(PLANS.map((p) => [p.id, p.priceUsdMonthly, p.minutesPerMonth])).toEqual([
      ["free", 0, 30],
      ["clipper", 19, 150],
      ["pro", 39, 400],
      ["team", 79, 1000],
    ]);
    expect(TOP_UP).toEqual({ priceUsd: 10, minutes: 100 });
  });

  it("keeps X and campaigns off the free plan", () => {
    const free = planById("free");
    expect(free.watermark).toBe(true);
    expect(free.postToX).toBe(false);
    expect(free.campaigns).toBe(false);
    expect(free.postingChannels).toBe(0);
  });

  it("only gets more generous going up", () => {
    for (let i = 1; i < PLANS.length; i++) {
      expect(PLANS[i].priceUsdMonthly).toBeGreaterThan(PLANS[i - 1].priceUsdMonthly);
      expect(PLANS[i].minutesPerMonth).toBeGreaterThan(PLANS[i - 1].minutesPerMonth);
    }
  });
});

describe("creditsFor", () => {
  it("charges whole minutes of source, rounding up", () => {
    expect(creditsFor(180)).toBe(3);
    expect(creditsFor(181)).toBe(4);
    expect(creditsFor(30)).toBe(1);
  });

  it("charges nothing for empty or broken durations", () => {
    expect(creditsFor(0)).toBe(0);
    expect(creditsFor(-5)).toBe(0);
    expect(creditsFor(Number.NaN)).toBe(0);
  });
});
