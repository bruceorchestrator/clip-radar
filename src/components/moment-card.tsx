import Link from "next/link";
import { clipFormHref, clipSourceFor } from "@/lib/clip-source";
import type { Moment } from "@/lib/types";

const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

function formatDuration(totalSec: number): string {
  const sec = Math.round(totalSec);
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
}

const PLATFORM_LABEL = { twitch: "Twitch", kick: "Kick" } as const;

export function MomentCard({ moment }: { moment: Moment }) {
  const { top } = moment;
  const others = moment.clips.slice(1);
  const source = clipSourceFor(moment);

  return (
    <article className="flex h-full flex-col overflow-hidden rounded-2xl border border-line bg-panel">
      <a href={top.url} target="_blank" rel="noreferrer" className="relative block aspect-video bg-panel-2">
        {top.thumbnailUrl ? (
          // Thumbnails come from the platforms' own CDNs; no image optimization needed.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={top.thumbnailUrl} alt="" loading="lazy" className="h-full w-full object-cover" />
        ) : null}
        <span className="absolute bottom-2 right-2 rounded bg-black/75 px-1.5 py-0.5 text-xs tabular-nums text-white">
          {formatDuration(top.durationSec)}
        </span>
      </a>

      <div className="flex flex-1 flex-col gap-3 p-4">
        <h2 className="line-clamp-2 font-medium leading-snug">
          <a href={top.url} target="_blank" rel="noreferrer" className="hover:underline">
            {top.title || "Untitled clip"}
          </a>
        </h2>
        <p className="text-sm text-muted">
          {moment.streamer.name} · {PLATFORM_LABEL[moment.platform]}
        </p>

        <div className="mt-auto flex flex-wrap gap-2 text-xs">
          {moment.clippedTimes > 1 ? (
            <span className="rounded-full bg-accent px-2.5 py-1 font-medium text-accent-ink">
              clipped {moment.clippedTimes} times
            </span>
          ) : null}
          <span className="rounded-full border border-line px-2.5 py-1 text-fg/85">
            {compact.format(moment.totalViews)} views
          </span>
          <span className="rounded-full border border-line px-2.5 py-1 text-fg/85">
            {compact.format(moment.viewsPerHour)} views/hr
          </span>
        </div>

        {source ? (
          <Link
            href={clipFormHref(source)}
            className="self-start rounded-full bg-accent px-4 py-2 text-sm font-medium text-accent-ink hover:brightness-110"
          >
            Make clip
          </Link>
        ) : null}

        {others.length > 0 ? (
          <details className="text-sm text-muted">
            <summary className="cursor-pointer select-none hover:text-fg">
              {others.length} more {others.length === 1 ? "version" : "versions"}
            </summary>
            <ul className="mt-2 space-y-1">
              {others.map((clip) => (
                <li key={clip.id} className="flex justify-between gap-3">
                  <a href={clip.url} target="_blank" rel="noreferrer" className="truncate hover:underline">
                    {clip.title || "Untitled clip"}
                  </a>
                  <span className="shrink-0 tabular-nums">{compact.format(clip.views)}</span>
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </div>
    </article>
  );
}
