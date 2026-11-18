# Clip Radar: guide for the agent setting it up

You are helping a person run Clip Radar for themselves. Read this file fully, then:
1. Explain to them in plain words how the system works (section 2), in their language.
2. Set it up with them step by step (section 4). Ask them for keys and accounts; never invent
   or print secrets, keep them in the env files only.
3. If they want more sources or platforms (Kick, TikTok, X...), follow section 7.

## 1. What it is

A self-hosted machine that turns live-stream recordings into vertical clips for clipping
campaigns (Reach, Content Rewards and similar pools that pay per view). It finds the moments
viewers already clipped, cuts a short stretch of the recording around each, lets an open-source
engine pick and caption the best 15-45 seconds, lays it out "webcam on top, game below", checks
it against the campaign's rules and posts it only when a person clicks.

Cost: the LLM that picks moments costs about $0.02 per hour of stream, and only 3-minute
stretches are sent, so a clip costs a fraction of a cent. Whisper (speech to text) and ffmpeg
run locally for free. It runs on a ~$20/month 2-core server; without a GPU one 3-minute
stretch takes 12-15 minutes to process.

## 2. How it works (the chain)

```
trigger -> radar -> stretch -> core (Whisper + LLM + crop + captions) -> score filter
        -> review queue -> stacked layout -> campaign check -> person clicks Post
        -> cover + Upload-Post -> Telegram links -> cleanup
```

0. **Trigger (autopilot, `engine/gateway/autopilot.py`).** The gateway loop wakes every
   `interval_min` (15), right after a clip is rejected or posted, or on `POST /autopilot/run`.
   It cuts new clips only into free places of the review queue: at most `queue_cap` (3) clips
   per streamer waiting or being cut (`retention.py`). A full queue means no work at all.
1. **Radar.** Twitch's public GraphQL returns the clips viewers made of the streamer in the last
   day. Clips of the same minute of the same recording merge into one moment, weighted by their
   views (`planner.viewer_hotspots`). Recordings started before `since` (e.g. a marathon start)
   are ignored; moments already cut are skipped (`seen`). Idea: where many viewers clipped,
   something happened.
2. **Stretch.** For the hottest new moment the gateway fetches 3 minutes of the recording
   (1 min before, 2 after) by downloading only the HLS segments that cover it (`hls.py`;
   yt-dlp fallback for non-HLS sources) and uploads that file to the core.
3. **Core = OpenShorts** (github.com/mutonby/openshorts, unmodified, in Docker):
   Whisper transcribes locally; the LLM (our prompts, `engine/prompts.py`) picks the best
   segments, scores them 0-100 and writes hook, title and description; the frame is cropped
   to vertical; word-by-word captions are burned in.
4. **Score filter.** Clips scoring at least `min_score` (70) join the review queue; Telegram ping.
5. **Gateway post-processing (ffmpeg):**
   - `stacked.py`: re-cuts the same stretch from the 1080p source with fixed boxes: the
     streamer's webcam (per-streamer `layout.cam`) fills the top band, the game the rest,
     captions sit on the seam. Done automatically, one clip per loop pass.
   - `headline.py`: optional, replaces captions with a big headline when Whisper failed
     (music, shouting).
6. **Campaign check (`campaigns.py`, `clip_campaigns.py`).** Each campaign brief (built in, or
   imported on the Campaigns page from a reachclipping.com / contentrewards.com link or pasted
   text, parsed by an LLM for ~$0.01) is checked automatically: campaign open, footage from the
   right channel and date, allowed platforms, streamer's name and hashtag in the caption,
   length, no CJK captions. A broken rule blocks posting. The rest (main focus, no logos, no
   negative framing) is a human checklist on the clip.
7. **Post, only by a click.** "Post to <channel>" on a clip: a cover is made (`thumbnail.py`:
   frame at the loudest half-second + the hook), the clip goes out through Upload-Post to that
   channel's platforms, and Telegram gets the links plus "submit within N minutes" (Reach wants
   links in Content Rewards within 30 minutes of posting).
8. **Cleanup (`retention.py`).** A clip unreviewed for `review_ttl_hours` (12) expires. An hour
   after a clip is posted or rejected, its renders and the core's job files (stream stretch,
   cut clips) are deleted unless a waiting clip still uses them.

Manual path: the web app's **Create** page takes a link plus a time range and runs steps 2-5 as
a one-off job (vertical or 16:9 for X). The **Radar** page shows the hottest viewer clips of a
category on Twitch and Kick.

## 3. Repo map

| Path | What |
|---|---|
| `src/` | Next.js web app: Radar `/`, Create `/clip`, job page `/jobs/[id]`, `/autopilot`, `/campaigns`. Talks only to the gateway (`GATEWAY_URL`). |
| `src/lib/sources/` | Radar sources: `twitch.ts`, `kick.ts` (Kick's unofficial site API, no key). |
| `engine/docker-compose.yml` | Core + gateway, both on 127.0.0.1 only. |
| `engine/gateway/` | Python stdlib HTTP gateway (port 8100): batches, autopilot, layouts, covers, campaigns, posting. Tests `test_*.py`. |
| `engine/overrides/` | Mounted into the core: `gemini_worker.py` (upstream file with our prompts, generated by `engine/apply_prompts.py`), `openrouter_vision.py` + `sitecustomize.py` (shot check through OpenRouter instead of a Gemini key). |
| `engine/prompts.py` | Our moment-selection prompts. |
| `engine/*.env.example` | Env templates. |

## 4. Setup from zero

Needs: a Linux server with Docker (2+ cores, 4+ GB RAM, 60+ GB disk), an OpenRouter key.
Optional: Upload-Post account + key (posting), a Telegram bot (pings).

```bash
git clone <this repo> clip-radar && cd clip-radar
git clone https://github.com/mutonby/openshorts.git openshorts
cd openshorts && git checkout c4b496a && cd ..     # the version our overrides were made from
cp engine/core.env.example engine/.env && chmod 600 engine/.env          # fill LLM_API_KEY
cp engine/gateway.env.example engine/gateway.env && chmod 600 engine/gateway.env
cd engine && docker compose up -d --build                                 # core :8000, gateway :8100
curl -s http://127.0.0.1:8100/health
```

If you update OpenShorts to a newer commit, regenerate the prompt override:
`python3 engine/apply_prompts.py openshorts/gemini_worker.py engine/overrides/gemini_worker.py`
(it fails loudly if upstream changed the templates). The `sitecustomize.py` mount path contains
the core image's Python version (3.11); fix it if upstream changes Python.

Web app (Node 22):

```bash
docker build -t clipradar-web .
docker run -d --name clipradar-web --network host --restart unless-stopped \
  -e HOSTNAME=127.0.0.1 -e PORT=3570 -e GATEWAY_URL=http://127.0.0.1:8100 clipradar-web
```

Keep every port private: open it through an SSH tunnel (`ssh -L 3570:127.0.0.1:3570 server`)
or a VPN such as Tailscale. There is no login in the app.

Local development of the web app: `npm ci`, `GATEWAY_URL=http://127.0.0.1:8100 npm run dev`
(tunnel the gateway port from the server).

### Configure the autopilot

The gateway writes a default `/data/autopilot.json` on first start (inside the `gw_data`
volume). Edit it (`docker exec -it clipradar-gateway sh`, or `docker cp` out and back):

```json
{
  "enabled": true, "interval_min": 15, "min_score": 70, "review_ttl_hours": 12,
  "streamers": [{
    "login": "<twitch login>", "name": "<display name used in captions>",
    "since": "2026-11-18T00:00:00Z",
    "queue_cap": 3, "max_spots_per_run": 2, "clips_per_spot": 1, "length": "medium",
    "hashtags": ["#Name", "#gta6"], "campaign": "<campaign id from the Campaigns page>",
    "accounts": [{"user": "<Upload-Post profile>", "platforms": ["youtube"], "name": "My Clips"}],
    "layout": {"cam": [0, 0, 0.255, 0.256], "game_center": 0.5}
  }]
}
```

- `layout.cam` is the webcam box as fractions of the 16:9 frame `[x0, y0, x1, y1]`. Grab a frame
  of the stream (`ffmpeg -ss 600 -i <vod url> -frames:v 1 f.jpg`) and measure. No `layout` =
  the core's own framing.
- `accounts[].user` is a profile in Upload-Post with the social accounts connected there.
  Platform ids are Upload-Post's (check their docs for X/TikTok/Instagram ids). YouTube custom
  covers need a phone-verified channel (youtube.com/verify), otherwise the post still goes out
  and the log says "youtube cover: error".
- Restart is not needed: the loop reads the file every pass.

## 5. Daily use

Open `/autopilot`: up to 3 clips wait. Watch, fix the layout or headline if needed, click
"Post to <channel>" or Reject. After a post, submit the links from Telegram to the campaign in
time. Rejecting frees a place and the next hottest moment is cut at once.

## 6. Rules that keep accounts paid

- Read each campaign's rules. Reach: streamer is the main focus, name + hashtag in caption,
  no logos, no negative framing, audience mostly from English-speaking countries, submit within
  30 minutes, botting or "AI-generated content" bans you from all their campaigns. Ask their
  Discord whether automated cutting of real stream footage is fine before scaling.
- Use a dedicated account per streamer in the same niche (e.g. "NameClips"), not a personal one.
- Accounts created outside the target country get that country's audience on TikTok/Instagram.

## 7. Extending

**Kick (or another streaming site) in the autopilot.** The Radar page already reads Kick
(`src/lib/sources/kick.ts`); the autopilot reads only Twitch (`CLIPS_QUERY` in `autopilot.py`).
To add Kick:
1. Write `kick_moments(login)` in the gateway returning nodes shaped like the Twitch ones:
   `{viewCount, durationSeconds, videoOffsetSeconds, createdAt, game: {name}, video: {id, createdAt}}`
   `kick.ts` shows the endpoints and headers (a datacenter IP may be refused). Its clips carry
   `livestream_id`, views, duration and `created_at`, but `kick.ts` reads no offset inside the
   recording: look for one in the raw clip answer, or compute it as clip `created_at` minus the
   livestream's start (`/channels/<slug>/videos` lists recordings) minus the clip duration.
2. Add `"source": "kick"` per streamer and pick the node fetcher by it in `find_new_moments`.
3. Build the recording URL for `create_batch` from the source (Twitch: `twitch.tv/videos/<id>`;
   Kick: the VOD page URL). `gateway.cut` already handles any HLS source yt-dlp understands.
4. `pick_spots`, the queue, layouts, checks and posting need no change. Add unit tests next to
   `test_autopilot.py` with recorded API answers.

**YouTube VOD sources.** yt-dlp from a datacenter IP often hits "Sign in to confirm you're not
a bot"; use cookies or a residential proxy.

**More posting platforms.** Connect them in Upload-Post and list them in the account's
`platforms`; `post_clip` sends one request per account. Add the platform to the campaign's
allowed list so the check passes.

**Other campaign sites.** `brief_import.py` downloads only from reachclipping.com and
contentrewards.com; add a host to its allow-list and a fixture under
`engine/gateway/fixtures/briefs/`, or paste the rules text on the Campaigns page.

**Speed.** A GPU server (Whisper on CUDA, `FFMPEG_ENCODER` with NVENC) cuts processing from
minutes to seconds; `CLIP_WORKERS`/`MAX_CONCURRENT_JOBS` can then go up.

## 8. Tests

```bash
cd engine/gateway && python3 -m unittest -q        # ffmpeg/libass tests skip without them
npm ci && npm test && npm run typecheck && npm run lint
```

Inside the gateway container all tests run (it has ffmpeg with libass):
`docker exec clipradar-gateway python -m unittest -q`.
