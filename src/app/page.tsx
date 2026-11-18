import Link from "next/link";
import { Suspense } from "react";
import { MomentCard } from "@/components/moment-card";
import { sortMoments } from "@/lib/moments";
import { getRadar } from "@/lib/radar";
import type { MomentSort, Period } from "@/lib/types";

type Filters = { period: Period; sort: MomentSort; englishOnly: boolean };
type RawParams = { [key: string]: string | string[] | undefined };

const PERIODS: { value: Period; label: string }[] = [
  { value: "day", label: "Last 24 hours" },
  { value: "week", label: "Last 7 days" },
];
const SORTS: { value: MomentSort; label: string }[] = [
  { value: "views", label: "Most viewed" },
  { value: "clipped", label: "Most clipped" },
  { value: "rising", label: "Rising" },
];
const MAX_MOMENTS = 60;

function parseFilters(params: RawParams): Filters {
  const period = PERIODS.some((p) => p.value === params.period)
    ? (params.period as Period)
    : "day";
  const sort = SORTS.some((s) => s.value === params.sort) ? (params.sort as MomentSort) : "views";
  return { period, sort, englishOnly: params.lang !== "all" };
}

function hrefFor(filters: Filters, change: Partial<Filters>): string {
  const next = { ...filters, ...change };
  const query = new URLSearchParams();
  if (next.period !== "day") query.set("period", next.period);
  if (next.sort !== "views") query.set("sort", next.sort);
  if (!next.englishOnly) query.set("lang", "all");
  const text = query.toString();
  return text ? `/?${text}` : "/";
}

function Chip({ href, active, children }: { href: string; active: boolean; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      aria-current={active ? "true" : undefined}
      className={
        active
          ? "rounded-full bg-accent px-4 py-2 text-sm font-medium text-accent-ink"
          : "rounded-full border border-line px-4 py-2 text-sm text-fg/85 hover:border-muted"
      }
    >
      {children}
    </Link>
  );
}

async function RadarView({ searchParams }: { searchParams: Promise<RawParams> }) {
  const filters = parseFilters(await searchParams);
  const radar = await getRadar(filters.period, filters.englishOnly);
  const moments = sortMoments(radar.moments, filters.sort).slice(0, MAX_MOMENTS);
  const failed = radar.sources.filter((source) => !source.ok);

  return (
    <>
      <nav aria-label="Filters" className="flex flex-wrap items-center gap-2">
        {PERIODS.map((p) => (
          <Chip key={p.value} href={hrefFor(filters, { period: p.value })} active={filters.period === p.value}>
            {p.label}
          </Chip>
        ))}
        <span className="mx-1 h-5 w-px bg-line" aria-hidden />
        {SORTS.map((s) => (
          <Chip key={s.value} href={hrefFor(filters, { sort: s.value })} active={filters.sort === s.value}>
            {s.label}
          </Chip>
        ))}
        <span className="mx-1 h-5 w-px bg-line" aria-hidden />
        <Chip href={hrefFor(filters, { englishOnly: true })} active={filters.englishOnly}>
          English only
        </Chip>
        <Chip href={hrefFor(filters, { englishOnly: false })} active={!filters.englishOnly}>
          All languages
        </Chip>
      </nav>

      <p className="mt-4 text-sm text-muted">
        {radar.moments.length} moments from{" "}
        {radar.sources.map((s) => `${s.clipCount} ${s.platform} clips`).join(" and ")}
        {radar.moments.length > MAX_MOMENTS ? `, top ${MAX_MOMENTS} shown` : ""}
      </p>

      {failed.map((source) => (
        <p key={source.platform} role="alert" className="mt-3 rounded-lg border border-warn/40 bg-warn/10 px-4 py-3 text-sm text-warn">
          Could not load {source.platform} clips right now ({source.error}). Showing the rest.
        </p>
      ))}

      {moments.length === 0 ? (
        <p className="mt-12 text-muted">No clips match these filters yet. Try the last 7 days or all languages.</p>
      ) : (
        <ul className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {moments.map((moment) => (
            <li key={moment.id}>
              <MomentCard moment={moment} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export default function Page({ searchParams }: { searchParams: Promise<RawParams> }) {
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-6">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">GTA VI clip radar</h1>
      <p className="mt-2 max-w-2xl text-muted">
        The moments viewers are clipping right now on Twitch and Kick. When several viewers clip the same moment, it shows up once with a count.
      </p>
      <div className="mt-8">
        <Suspense fallback={<p className="text-muted">Loading clips…</p>}>
          <RadarView searchParams={searchParams} />
        </Suspense>
      </div>
    </main>
  );
}
