import type { AutopilotItem } from "@/lib/engine";

/** A message shown after pressing a button on a queued clip. */
export type Notice = { kind: "wait" | "ok" | "bad"; text: string; url?: string };

/** What a finished Post press did, read from the item as the engine now reports it. */
export function postResult(item: AutopilotItem | undefined, accountName?: string): Notice {
  const where = accountName ?? "the channel";
  if (!item) return { kind: "ok", text: `Sent to ${where}. See the Posted tab.` };
  if (item.status === "failed") return { kind: "bad", text: `Posting to ${where} failed: ${item.error || "no reason given"}` };
  // Engine keys look like "<account name> <platform>", e.g. "LACY Clips youtube".
  const links = Object.entries(item.posts)
    .filter(([key]) => !accountName || key.startsWith(`${accountName} `))
    .map(([, value]) => value);
  const url = links.find((v) => v.startsWith("https://"));
  if (item.status === "posted" && url) return { kind: "ok", text: `Posted to ${where}.`, url };
  if (item.status === "posted") return { kind: "ok", text: `Posted to ${where}. ${links.join(" ")}`.trim() };
  return { kind: "ok", text: `Sent to ${where}; it shows under Posted when the upload finishes.` };
}
