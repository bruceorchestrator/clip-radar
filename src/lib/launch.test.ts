import { describe, expect, it } from "vitest";
import { estimateCredits, formatClock, launchProblem, parseClock, stretchesFor, type Preview } from "./launch";

const LONG: Preview = { durationSec: 22940, title: "6 h stream", long: true, hotspots: [] };
const SHORT: Preview = { durationSec: 540, title: "9 min video", long: false, hotspots: [] };

describe("estimateCredits", () => {
  it("charges only the hot stretches of a long stream", () => {
    expect(estimateCredits(LONG, { mode: "auto", clips: 10, length: "medium" })).toBe(15);
    expect(estimateCredits(LONG, { mode: "auto", clips: 5, length: "medium" })).toBe(9);
    expect(estimateCredits(LONG, { mode: "auto", clips: 20, length: "medium" })).toBe(30);
  });

  it("charges the whole stream when asked for it", () => {
    expect(estimateCredits(LONG, { mode: "whole", clips: 10, length: "medium" })).toBe(383);
  });

  it("charges a short video whole, whatever the mode", () => {
    expect(estimateCredits(SHORT, { mode: "auto", clips: 10, length: "medium" })).toBe(9);
  });

  it("charges a chosen stretch by its length", () => {
    expect(estimateCredits(LONG, { mode: "stretch", clips: 5, length: "short", start: 600, end: 750 })).toBe(3);
    expect(estimateCredits(LONG, { mode: "stretch", clips: 5, length: "short" })).toBe(0);
  });

  it("never charges more than the video when stretches would exceed it", () => {
    const halfHour: Preview = { durationSec: 1500, title: "", long: true, hotspots: [] };
    expect(estimateCredits(halfHour, { mode: "auto", clips: 20, length: "medium" })).toBe(25);
  });
});

describe("stretchesFor", () => {
  it("matches the gateway planner", () => {
    expect([1, 5, 10, 20, 50].map(stretchesFor)).toEqual([1, 3, 5, 10, 10]);
  });
});

describe("parseClock", () => {
  it("reads h:mm:ss, mm:ss, seconds", () => {
    expect(parseClock("1:02:03")).toBe(3723);
    expect(parseClock("12:30")).toBe(750);
    expect(parseClock("45")).toBe(45);
    expect(parseClock(" 90s ")).toBe(90);
  });

  it("rejects junk and impossible minutes", () => {
    expect(parseClock("")).toBeNull();
    expect(parseClock("abc")).toBeNull();
    expect(parseClock("1:75")).toBeNull();
    expect(parseClock("1:2:3:4")).toBeNull();
    expect(parseClock("-5")).toBeNull();
  });

  it("round-trips with formatClock", () => {
    expect(formatClock(3723)).toBe("1:02:03");
    expect(parseClock(formatClock(750))).toBe(750);
  });
});

describe("launchProblem", () => {
  it("accepts auto and whole without a stretch", () => {
    expect(launchProblem(LONG, { mode: "auto", clips: 10, length: "medium" })).toBeNull();
  });

  it("checks the stretch", () => {
    expect(launchProblem(LONG, { mode: "stretch", clips: 5, length: "short" })).toMatch(/Set where/);
    expect(launchProblem(LONG, { mode: "stretch", clips: 5, length: "short", start: 0, end: 30 })).toMatch(/45 seconds/);
    expect(launchProblem(LONG, { mode: "stretch", clips: 5, length: "short", start: 0, end: 700 })).toMatch(/10 minutes/);
    expect(launchProblem(SHORT, { mode: "stretch", clips: 5, length: "short", start: 500, end: 600 })).toMatch(/past the end/);
    expect(launchProblem(LONG, { mode: "stretch", clips: 5, length: "short", start: 100, end: 300 })).toBeNull();
  });
});
