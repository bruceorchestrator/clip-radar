import type { Clip, Period } from "../types";
import { fetchJson } from "./http";

/**
 * kick.com's own website endpoints (unofficial, no key). They answer a
 * browser-like request; a datacenter IP may be refused, check after deploy.
 */
const API = "https://kick.com/api/v2";
const CATEGORY_SLUG = "grand-theft-auto-vi";
const MAX_PAGES = 5; // 20 clips per page
const MAX_LANGUAGE_LOOKUPS = 30; // one request per channel

const HEADERS = {
  Accept: "application/json",
  "User-Agent":
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
};

const LANGUAGE_CODES: Record<string, string> = {
  english: "en",
  spanish: "es",
  portuguese: "pt",
  french: "fr",
  german: "de",
  italian: "it",
  turkish: "tr",
  arabic: "ar",
  russian: "ru",
  polish: "pl",
  japanese: "ja",
  korean: "ko",
};

export type KickClip = {
  id: string;
  livestream_id: string;
  title: string;
  thumbnail_url: string | null;
  views: number;
  duration: number;
  created_at: string;
  creator: { username: string } | null;
  channel: { username: string; slug: string };
};

type ClipsPage = { clips: KickClip[]; nextCursor: string | null };
type KickVideo = { id: number | string; language: string | null };

export function kickLanguageCode(name: string | null | undefined): string | null {
  if (!name) return null;
  const key = name.trim().toLowerCase();
  return LANGUAGE_CODES[key] ?? key;
}

export function mapKickClip(raw: KickClip, language: string | null): Clip {
  const createdSec = Math.floor(new Date(raw.created_at).getTime() / 1000);
  return {
    id: raw.id,
    platform: "kick",
    title: raw.title,
    url: `https://kick.com/${raw.channel.slug}/clips/${raw.id}`,
    thumbnailUrl: raw.thumbnail_url,
    views: raw.views,
    durationSec: raw.duration,
    createdAt: raw.created_at,
    language,
    streamer: { login: raw.channel.slug, name: raw.channel.username },
    clipper: raw.creator?.username ?? null,
    streamKey: `kick:${raw.livestream_id}`,
    timeBasis: "wall",
    startSec: createdSec - raw.duration,
    vodUrl: null,
  };
}

async function fetchCategoryClips(period: Period): Promise<KickClip[]> {
  const clips: KickClip[] = [];
  let cursor: string | null = null;
  for (let page = 0; page < MAX_PAGES; page++) {
    const params = new URLSearchParams({ sort: "view", time: period });
    if (cursor) params.set("cursor", cursor);
    const url = `${API}/categories/${CATEGORY_SLUG}/clips?${params}`;
    const json: ClipsPage = await fetchJson<ClipsPage>(url, { headers: HEADERS });
    clips.push(...json.clips);
    cursor = json.nextCursor;
    if (!cursor || json.clips.length === 0) break;
  }
  return clips;
}

/** Maps livestream id to language for the channels with the most viewed clips. */
async function fetchStreamLanguages(clips: KickClip[]): Promise<Map<string, string | null>> {
  const slugs = [...new Set(clips.map((clip) => clip.channel.slug))].slice(
    0,
    MAX_LANGUAGE_LOOKUPS,
  );
  const languages = new Map<string, string | null>();
  const results = await Promise.allSettled(
    slugs.map((slug) =>
      fetchJson<KickVideo[]>(`${API}/channels/${slug}/videos`, { headers: HEADERS }),
    ),
  );
  for (const result of results) {
    if (result.status !== "fulfilled" || !Array.isArray(result.value)) continue;
    for (const video of result.value) {
      languages.set(String(video.id), kickLanguageCode(video.language));
    }
  }
  return languages;
}

export async function fetchKickClips(period: Period): Promise<Clip[]> {
  const raw = await fetchCategoryClips(period);
  const languages = await fetchStreamLanguages(raw);
  return raw.map((clip) => mapKickClip(clip, languages.get(clip.livestream_id) ?? null));
}
