/**
 * Plans (set 2026-11-18). One credit = one minute of source
 * video processed; the price of a job is shown before it starts.
 * Source of truth for billing, the pricing page and limits in the app.
 */
export type PlanId = "free" | "clipper" | "pro" | "team";

export type Plan = {
  id: PlanId;
  name: string;
  priceUsdMonthly: number;
  minutesPerMonth: number;
  watermark: boolean;
  /** Connected posting channels; null = no limit. Free posts nothing. */
  postingChannels: number | null;
  postToX: boolean;
  campaigns: boolean;
  priorityQueue: boolean;
  seats: number;
};

export const PLANS: readonly Plan[] = [
  { id: "free", name: "Free", priceUsdMonthly: 0, minutesPerMonth: 30, watermark: true, postingChannels: 0, postToX: false, campaigns: false, priorityQueue: false, seats: 1 },
  { id: "clipper", name: "Clipper", priceUsdMonthly: 19, minutesPerMonth: 150, watermark: false, postingChannels: 3, postToX: true, campaigns: false, priorityQueue: false, seats: 1 },
  { id: "pro", name: "Pro", priceUsdMonthly: 39, minutesPerMonth: 400, watermark: false, postingChannels: null, postToX: true, campaigns: true, priorityQueue: true, seats: 1 },
  { id: "team", name: "Team", priceUsdMonthly: 79, minutesPerMonth: 1000, watermark: false, postingChannels: null, postToX: true, campaigns: true, priorityQueue: true, seats: 5 },
];

/** Extra minutes on any paid plan. */
export const TOP_UP = { priceUsd: 10, minutes: 100 } as const;

export function planById(id: PlanId): Plan {
  const plan = PLANS.find((p) => p.id === id);
  if (!plan) throw new Error(`Unknown plan: ${id}`);
  return plan;
}

/** Credits a job costs: whole minutes of source video, at least 1. */
export function creditsFor(sourceSeconds: number): number {
  if (!Number.isFinite(sourceSeconds) || sourceSeconds <= 0) return 0;
  return Math.max(1, Math.ceil(sourceSeconds / 60));
}
