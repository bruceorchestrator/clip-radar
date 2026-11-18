"use client";

import Link from "next/link";
import { useState } from "react";

type Props = {
  /** Streamers the autopilot knows (their name, hashtags and channels are used). */
  streamers: { login: string; name: string }[];
};

const FIELD =
  "w-full rounded-lg border border-line bg-panel px-3 py-2.5 text-fg placeholder:text-muted focus:border-accent focus:outline-none";
const OTHER = "__other__";

/**
 * A moment someone already picked (a clip from a community library, a Kick or
 * Twitch clip, their own recording): no moment search, just captions, hook,
 * webcam-on-top layout, the campaign check, and the review queue.
 */
export function ReadyClipForm({ streamers }: Props) {
  const [streamer, setStreamer] = useState(streamers[0]?.login ?? OTHER);
  const [otherName, setOtherName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [hook, setHook] = useState("");
  const [rights, setRights] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [queued, setQueued] = useState<string | null>(null);

  const name = streamer === OTHER ? otherName.trim() : streamer;
  const problem = !name
    ? "Name the streamer in the clip."
    : !file && !url.trim()
      ? "Upload the video or paste a clip link."
      : null;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (problem || pending) return;
    setPending(true);
    setError(null);
    const form = new FormData();
    form.set("streamer", name);
    if (streamer === OTHER) form.set("name", otherName.trim());
    if (hook.trim()) form.set("hook", hook.trim());
    if (file) form.set("file", file);
    else form.set("url", url.trim());
    form.set("rightsConfirmed", String(rights));
    try {
      const response = await fetch("/api/ready", { method: "POST", body: form });
      const body = (await response.json().catch(() => ({}))) as { streamer?: string; error?: string };
      if (!response.ok) throw new Error(body.error ?? "Could not start the clip.");
      setQueued(body.streamer ?? name);
      setFile(null);
      setUrl("");
      setHook("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the clip.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <div>
        <label htmlFor="ready-streamer" className="mb-1.5 block text-sm font-medium">Streamer in the clip</label>
        <select id="ready-streamer" value={streamer} onChange={(e) => setStreamer(e.target.value)} className={FIELD}>
          {streamers.map((s) => (
            <option key={s.login} value={s.login}>{s.name || s.login}</option>
          ))}
          <option value={OTHER}>Someone else…</option>
        </select>
        {streamer === OTHER ? (
          <input
            value={otherName}
            onChange={(e) => setOtherName(e.target.value)}
            placeholder="N3on"
            aria-label="Streamer name"
            className={`${FIELD} mt-2`}
          />
        ) : null}
        <p className="mt-1.5 text-sm text-muted">Their name and hashtag go in the caption; the webcam is found in the clip.</p>
      </div>

      <div>
        <label htmlFor="ready-file" className="mb-1.5 block text-sm font-medium">The clip</label>
        <input
          id="ready-file"
          type="file"
          accept="video/mp4,video/quicktime,video/webm"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="block w-full text-sm text-muted file:mr-3 file:rounded-full file:border-0 file:bg-panel-2 file:px-4 file:py-2 file:text-fg"
        />
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={!!file}
          placeholder="…or a Kick, Twitch or YouTube clip link"
          aria-label="Clip link"
          className={`${FIELD} mt-2 disabled:opacity-50`}
        />
        <p className="mt-1.5 text-sm text-muted">Up to 3 minutes. It is used as is: no moment search, no cutting.</p>
      </div>

      <div>
        <label htmlFor="ready-hook" className="mb-1.5 block text-sm font-medium">Hook <span className="font-normal text-muted">(optional)</span></label>
        <input
          id="ready-hook"
          value={hook}
          onChange={(e) => setHook(e.target.value)}
          maxLength={120}
          placeholder="Leave empty to have one written from what is said"
          className={FIELD}
        />
      </div>

      <label className="flex items-start gap-3 text-sm text-fg/85">
        <input type="checkbox" checked={rights} onChange={(e) => setRights(e.target.checked)} className="mt-0.5 size-4 accent-accent" />
        <span>I have the right to post this clip, for example through a campaign that allows clipping.</span>
      </label>

      <button
        type="submit"
        disabled={pending || !!problem || !rights}
        className="rounded-full bg-accent px-6 py-3 font-medium text-accent-ink hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? "Sending…" : "Finish this clip"}
      </button>

      {queued ? (
        <p role="status" className="rounded-lg border border-line bg-panel px-4 py-3 text-sm">
          Queued for {queued}. It shows up on <Link href="/autopilot" className="text-accent underline">Autopilot</Link> with
          captions, hook and layout in about 10–15 minutes.
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="rounded-lg border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">{error}</p>
      ) : null}
    </form>
  );
}
