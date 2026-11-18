import type { Clip, Period } from "../types";
import { fetchJson } from "./http";

const GQL_URL = "https://gql.twitch.tv/gql";
/**
 * The public client id twitch.tv itself uses. Unofficial access: only the
 * first page (100 clips) is available, page two fails an integrity check.
 * Replace with official Helix app credentials before launch.
 */
const WEB_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko";
const GAME_NAME = "Grand Theft Auto VI";
const PAGE_SIZE = 100;

const QUERY = `query($name:String!,$first:Int!,$period:ClipsPeriod!){
  game(name:$name){
    clips(first:$first, criteria:{period:$period, sort:VIEWS_DESC}){
      edges{ node{
        slug title viewCount createdAt durationSeconds videoOffsetSeconds
        url thumbnailURL language
        broadcaster{ login displayName }
        curator{ login }
        video{ id }
      } }
    }
  }
}`;

export type TwitchClipNode = {
  slug: string;
  title: string;
  viewCount: number;
  createdAt: string;
  durationSeconds: number;
  videoOffsetSeconds: number | null;
  url: string;
  thumbnailURL: string | null;
  language: string | null;
  broadcaster: { login: string; displayName: string } | null;
  curator: { login: string } | null;
  video: { id: string } | null;
};

type GqlResponse = {
  data?: { game: { clips: { edges: { node: TwitchClipNode }[] } | null } | null };
  errors?: { message: string }[];
};

export function mapTwitchClip(node: TwitchClipNode): Clip | null {
  if (!node.broadcaster) return null;
  const hasVodPosition = node.video !== null && node.videoOffsetSeconds !== null;
  const createdSec = Math.floor(new Date(node.createdAt).getTime() / 1000);
  return {
    id: node.slug,
    platform: "twitch",
    title: node.title,
    url: node.url,
    thumbnailUrl: node.thumbnailURL,
    views: node.viewCount,
    durationSec: node.durationSeconds,
    createdAt: node.createdAt,
    language: node.language ? node.language.toLowerCase() : null,
    streamer: { login: node.broadcaster.login, name: node.broadcaster.displayName },
    clipper: node.curator?.login ?? null,
    streamKey: hasVodPosition
      ? `twitch:vod:${node.video!.id}`
      : `twitch:live:${node.broadcaster.login}`,
    timeBasis: hasVodPosition ? "vod" : "wall",
    startSec: hasVodPosition
      ? node.videoOffsetSeconds!
      : createdSec - node.durationSeconds,
    vodUrl: hasVodPosition ? `https://www.twitch.tv/videos/${node.video!.id}` : null,
  };
}

export async function fetchTwitchClips(period: Period): Promise<Clip[]> {
  const body = JSON.stringify({
    query: QUERY,
    variables: {
      name: GAME_NAME,
      first: PAGE_SIZE,
      period: period === "day" ? "LAST_DAY" : "LAST_WEEK",
    },
  });
  const json = await fetchJson<GqlResponse>(GQL_URL, {
    method: "POST",
    headers: { "Client-ID": WEB_CLIENT_ID, "Content-Type": "application/json" },
    body,
  });
  if (json.errors?.length) throw new Error(`Twitch: ${json.errors[0].message}`);
  const edges = json.data?.game?.clips?.edges ?? [];
  return edges
    .map((edge) => mapTwitchClip(edge.node))
    .filter((clip): clip is Clip => clip !== null);
}
