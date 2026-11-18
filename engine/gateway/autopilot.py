"""Autopilot: watch streamers, clip their hot moments, queue for review, post.

Loop (every `interval_min`, and at once when a clip is rejected or posted):
1. For each streamer with a free place in the review queue (`queue_cap`, see
   retention.py), take the clips Twitch viewers made in the last day, group
   them by moment (planner.viewer_hotspots), skip moments already done, and
   start a gateway batch on a 3-minute stretch around the hottest new ones.
   Clips unreviewed for `review_ttl_hours` expire; files of closed clips are deleted.
2. When a batch finishes, its clips scoring at least `min_score` join the review
   queue.
3. Nothing is posted on its own: a person presses "Post to <channel>" on a clip,
   it goes out through Upload-Post to that channel right away, and the links go
   to Telegram so they can be submitted to the campaign within 30 minutes.

Config: <DATA_DIR>/autopilot.json (see DEFAULT_CONFIG). State: autopilot_state.json.
Secrets come from the environment: UPLOAD_POST_API_KEY, TELEGRAM_BOT_TOKEN,
TELEGRAM_CHAT_ID. Without the Upload-Post key nothing is posted; approved clips wait.

Pure helpers (pick_spots, build_post_text, clips_from_view, apply_action) are
unit-tested in test_autopilot.py.
"""
from __future__ import annotations

import json
import os
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

import campaigns as campaign_rules
import headline
import clip_campaigns
from clip_campaigns import build_post_text, campaign_for, item_checks  # noqa: F401 (re-exported)
import planner
import retention
import stacked
import thumbnail

STATE_LOCK = threading.Lock()
CAMPAIGN_SUBMIT_MINUTES = 30

DEFAULT_CONFIG = {
    "enabled": True,
    "interval_min": 15,
    "min_score": 70,
    "review_ttl_hours": 12,
    "streamers": [
        {
            "login": "lacy",
            "name": "LACY",
            "game": None,
            "since": "2026-11-18T00:00:00Z",
            "queue_cap": 3,
            "max_spots_per_run": 2,
            "clips_per_spot": 1,
            "length": "medium",
            "upload_post_user": None,
            "platforms": ["tiktok", "instagram", "youtube"],
            "hashtags": ["#LACY", "#gta6", "#gtavi"],
            "campaign": "reach-lacy-gta",
        }
    ],
}

CLIPS_QUERY = """query($login:String!,$first:Int!){ user(login:$login){
  clips(first:$first, criteria:{period:LAST_DAY, sort:VIEWS_DESC}){ edges{ node{
    slug viewCount durationSeconds videoOffsetSeconds createdAt game{ name } video{ id createdAt } } } } } }"""


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def spot_key(vod_id: str, t: float) -> str:
    """One key per minute of a recording, so the same moment is clipped once."""
    return f"{vod_id}:{int(t // 60)}"


def pick_spots(nodes: list[dict], game: str | None, seen: set[str], limit: int,
               since: str | None = None) -> list[dict]:
    """New hot moments from viewer clips, hottest first.

    nodes: Twitch clip nodes (slug, viewCount, durationSeconds, videoOffsetSeconds,
    createdAt, game{name}, video{id}). `since` (ISO 8601): ignore clips made
    earlier, e.g. before a campaign's marathon started.
    """
    by_vod: dict[str, list[dict]] = {}
    for node in nodes:
        vod = (node.get("video") or {}).get("id")
        offset = node.get("videoOffsetSeconds")
        if not vod or offset is None:
            continue
        if game and ((node.get("game") or {}).get("name") or "").lower() != game.lower():
            continue
        # The recording itself must start after `since` (a campaign counts only
        # its marathon), not just the clip: viewers also clip old VODs.
        vod_started = str((node.get("video") or {}).get("createdAt") or node.get("createdAt") or "")
        if since and vod_started < since:
            continue
        by_vod.setdefault(vod, []).append({"start": offset, "duration": node.get("durationSeconds"),
                                           "views": node.get("viewCount"), "vod_started": vod_started})
    spots = []
    for vod, clips in by_vod.items():
        vod_started = clips[0]["vod_started"] or None
        for t, weight in planner.viewer_hotspots(clips):
            key = spot_key(vod, t)
            if key in seen:
                continue
            spots.append({"vod": vod, "t": t, "weight": weight, "key": key, "vod_started": vod_started})
    spots.sort(key=lambda s: -s["weight"])
    out, taken = [], set()
    for spot in spots:
        if spot["key"] in taken:
            continue
        taken.add(spot["key"])
        out.append(spot)
        if len(out) >= limit:
            break
    return out


def posting_accounts(streamer: dict) -> list[dict]:
    """Where a streamer's clips go: `accounts` [{user, platforms, name}], or the older
    single `upload_post_user` + `platforms`."""
    accounts = [a for a in streamer.get("accounts") or [] if a.get("user") and a.get("platforms")]
    if accounts:
        return accounts
    if streamer.get("upload_post_user") and streamer.get("platforms"):
        return [{"user": streamer["upload_post_user"], "platforms": streamer["platforms"]}]
    return []


def clips_from_view(batch_view: dict, min_score: int) -> list[dict]:
    """Clips of a finished batch worth reviewing, with what posting needs."""
    out = []
    for task in batch_view.get("tasks") or []:
        engine = task.get("engine") or {}
        if engine.get("status") != "completed":
            continue
        for clip in ((engine.get("result") or {}).get("clips") or []):
            score = clip.get("predicted_score")
            video = clip.get("video_url")
            if not isinstance(video, str) or not video.startswith("/videos/"):
                continue
            if not isinstance(score, (int, float)) or score < min_score:
                continue
            out.append({
                "video_path": video,
                "score": score,
                "title": clip.get("video_title_for_youtube_short") or "",
                "hook": clip.get("viral_hook_text") or "",
                "description": clip.get("video_description_for_tiktok") or "",
                "duration": round(float(clip.get("end", 0)) - float(clip.get("start", 0)), 1),
            })
    return out


def due(last: float | None, interval_sec: float, now: float) -> bool:
    """True when a periodic step should run again."""
    return last is None or now - last >= interval_sec


ALLOWED = {"approve": ("review",), "reject": ("review", "approved"), "unreject": ("rejected",)}
NEXT = {"approve": "approved", "reject": "rejected", "unreject": "review"}


def apply_action(item: dict, action: str) -> str | None:
    """Move a queue item; returns an error message or None."""
    if action not in ALLOWED:
        return "unknown action"
    if item.get("status") not in ALLOWED[action]:
        return f"cannot {action} a clip that is {item.get('status')}"
    item["status"] = NEXT[action]
    item["updated"] = time.time()
    return None


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
def _paths(data_dir: str) -> tuple[str, str]:
    return os.path.join(data_dir, "autopilot.json"), os.path.join(data_dir, "autopilot_state.json")


def load_config(data_dir: str) -> dict:
    path, _ = _paths(data_dir)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_state(data_dir: str) -> dict:
    _, path = _paths(data_dir)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"seen": [], "pending": [], "items": [], "last_run": None, "last_post": {}, "log": []}


def save_state(data_dir: str, state: dict) -> None:
    _, path = _paths(data_dir)
    state["log"] = state.get("log", [])[-200:]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, path)


def log(state: dict, message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    state.setdefault("log", []).append(f"{stamp} {message}")
    print(f"autopilot: {message}", flush=True)


# --------------------------------------------------------------------------- #
# Side effects
# --------------------------------------------------------------------------- #
def notify(text: str) -> None:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=15).read()
    except Exception as exc:
        print(f"autopilot: telegram failed: {exc}", flush=True)


def _multipart(fields: list[tuple[str, str]], files: list[tuple[str, str, str, bytes]]) -> tuple[bytes, str]:
    """files: (field, filename, content type, bytes)."""
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for field, filename, content_type, data in files:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n".encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _upload_post(path: str, body: bytes, content_type: str, idempotency: str | None = None) -> dict:
    headers = {"Authorization": f"Apikey {os.environ['UPLOAD_POST_API_KEY']}", "Content-Type": content_type}
    if idempotency:
        headers["Idempotency-Key"] = idempotency
    req = urllib.request.Request(f"https://api.upload-post.com{path}", data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Upload-Post {exc.code}: {detail}") from exc


def set_youtube_thumbnail(user: str, video_id: str, cover: bytes) -> dict:
    """Cover for a Short that is already on YouTube (Upload-Post queues it while YouTube processes)."""
    body, content_type = _multipart([("user", user), ("video_id", video_id)],
                                    [("thumbnail", "cover.jpg", "image/jpeg", cover)])
    return _upload_post("/api/uploadposts/youtube/thumbnail", body, content_type)


def post_clip(item: dict, streamer: dict, video_bytes: bytes, text: dict, cover: bytes | None = None) -> dict:
    """Post through Upload-Post with the caption from the campaign check and, for
    YouTube, the cover image; returns {platform: url or error}."""
    fields = [("user", streamer["upload_post_user"]), ("title", text["title"]),
              ("tiktok_title", text["caption"]), ("instagram_title", text["caption"]),
              ("youtube_title", text["title"]), ("description", text["caption"])]
    fields += [("platform[]", p) for p in streamer.get("platforms") or []]
    files = [("video", "clip.mp4", "video/mp4", video_bytes)]
    if cover and "youtube" in (streamer.get("platforms") or []):
        files.append(("thumbnail", "cover.jpg", "image/jpeg", cover))
    body, content_type = _multipart(fields, files)
    reply = _upload_post("/api/upload", body, content_type, idempotency=item["id"])
    out = {}
    for platform, result in (reply.get("results") or {}).items():
        out[platform] = result.get("url") if result.get("success") else f"error: {result.get('error')}"
        problem = result.get("thumbnail_error") or (result.get("thumbnail_note") if not (
            result.get("thumbnail_set") or result.get("thumbnail_pending")) else None)
        if cover and platform == "youtube" and problem:
            out["youtube cover"] = f"error: {problem}"
    if not out and reply.get("request_id"):
        out["pending"] = f"processing in background, request {reply['request_id']}"
    return out


class Autopilot:
    def __init__(self, data_dir: str, gql, create_batch, view_batch, load_batch, fetch_video):
        self.data_dir = data_dir
        self.gql = gql                      # (query, variables) -> data
        self.create_batch = create_batch    # (url, start, end, clips, length) -> batch id
        self.view_batch = view_batch        # (batch dict) -> view with engine status
        self.load_batch = load_batch        # (batch id) -> batch dict or None
        self.fetch_video = fetch_video      # (video path) -> bytes
        self.wake = threading.Event()
        self.run_requested = threading.Event()

    # The three stages, each safe to run again.
    def find_new_moments(self, config: dict, state: dict) -> None:
        seen = set(state.get("seen", []))
        for streamer in config.get("streamers", []):
            if streamer.get("enabled") is False:
                continue
            # Cut only into free places of the review queue (retention.py).
            per_spot = int(streamer.get("clips_per_spot") or 1)
            slots = retention.open_slots(state, streamer["login"],
                                         int(streamer.get("queue_cap") or retention.QUEUE_CAP), per_spot)
            wanted = retention.spots_for(slots, per_spot, int(streamer.get("max_spots_per_run") or 2))
            if not wanted:
                continue
            try:
                data = self.gql(CLIPS_QUERY, {"login": streamer["login"], "first": 50})
                nodes = [e["node"] for e in (((data.get("user") or {}).get("clips") or {}).get("edges") or [])]
            except Exception as exc:
                log(state, f"{streamer['login']}: viewer clips unavailable ({exc})")
                continue
            spots = pick_spots(nodes, streamer.get("game"), seen, wanted, streamer.get("since"))
            for spot in spots:
                start = max(0.0, spot["t"] - planner.LEAD_SEC)
                batch_id = self.create_batch(f"https://www.twitch.tv/videos/{spot['vod']}", start,
                                             start + planner.STRETCH_SEC,
                                             per_spot, streamer.get("length") or "medium")
                seen.add(spot["key"])
                state.setdefault("pending", []).append({"batch": batch_id, "streamer": streamer["login"],
                                                        "vod": spot["vod"], "t": spot["t"],
                                                        "vod_started": spot.get("vod_started")})
                log(state, f"{streamer['login']}: new moment at {int(spot['t'])}s of VOD {spot['vod']}, batch {batch_id[:8]}")
        state["seen"] = sorted(seen)[-5000:]

    def collect_finished(self, config: dict, state: dict) -> None:
        still = []
        new_items = 0
        for entry in state.get("pending", []):
            batch = self.load_batch(entry["batch"])
            if not batch:
                continue
            view = self.view_batch(batch)
            if view["status"] not in ("completed", "failed"):
                still.append(entry)
                continue
            for clip in clips_from_view(view, int(config.get("min_score") or 0)):
                state.setdefault("items", []).append({
                    **clip, "id": uuid.uuid4().hex, "streamer": entry["streamer"], "batch": entry["batch"],
                    "vod": entry.get("vod"), "vod_started": entry.get("vod_started"),
                    "status": "review", "posts": {}, "created": time.time(), "updated": time.time()})
                new_items += 1
        state["pending"] = still
        if new_items:
            log(state, f"{new_items} new clip(s) waiting for review")
            notify(f"Clip Radar: {new_items} new clip(s) waiting for review on the Autopilot page.")

    def post_approved(self, config: dict, state: dict) -> None:
        """Post every clip a person sent to a channel (status approved + post_to), right away.
        Nothing is posted without that click."""
        if not os.environ.get("UPLOAD_POST_API_KEY"):
            return
        campaigns = campaign_rules.load_campaigns(self.data_dir)
        streamers = {s["login"]: s for s in config.get("streamers", [])}
        for item in state.get("items", []):
            streamer = streamers.get(item.get("streamer"))
            if item.get("status") != "approved" or not streamer or not item.get("post_to"):
                continue
            account = next((a for a in posting_accounts(streamer) if a["user"] == item["post_to"]), None)
            if not account:
                item.update(status="review", updated=time.time())
                log(state, f"{item['id'][:8]} sent back to review: channel {item['post_to']} is not connected")
                continue
            target = {**streamer, "upload_post_user": account["user"], "platforms": account["platforms"]}
            check = item_checks(item, target, campaigns)
            broken = clip_campaigns.broken_rules(check)
            if broken:
                item.update(status="review", updated=time.time())
                log(state, f"{item['id'][:8]} sent back to review, breaks campaign rule: {broken[0]}")
                continue
            self._post(state, item, target, account, check)

    def _post(self, state: dict, item: dict, target: dict, account: dict, check: dict) -> None:
        name = account.get("name") or account["user"]
        try:
            text = check["text"] or build_post_text(item, target)
            cover = self._cover(item) if "youtube" in (target.get("platforms") or []) else None
            links = post_clip(item, target, self.fetch_video(item["video_path"]), text, cover)
            item.update(status="posted", posts={f"{name} {p}": u for p, u in links.items()},
                        posted_to=name, posted=time.time(), updated=time.time())
            lines = "\n".join(f"{p}: {u}" for p, u in links.items())
            chosen = [r["campaign"] for r in check["campaigns"] if r["selected"]]
            minutes = min([c.get("submit_within_min") or CAMPAIGN_SUBMIT_MINUTES for c in chosen]
                          or [CAMPAIGN_SUBMIT_MINUTES])
            where = "\n".join(f"- {c['name']}: {c.get('url') or c.get('rules_url')}" for c in chosen)
            notify(f"Clip Radar posted a {target.get('name')} clip on {name}. Submit it within {minutes} minutes "
                   f"to:\n{where or '- (no campaign linked)'}\n\nLinks:\n{lines}")
            log(state, f"posted {item['id'][:8]} for {target['login']} on {name}")
            self.run_requested.set()        # its place in the queue is free: look for the next moment
            self.wake.set()
        except Exception as exc:
            item.update(status="failed", error=str(exc)[:300], updated=time.time())
            log(state, f"posting {item['id'][:8]} on {name} failed: {exc}")

    def run_once(self, force_find: bool = False) -> None:
        with STATE_LOCK:
            config = load_config(self.data_dir)
            state = load_state(self.data_dir)
            interval = float(config.get("interval_min") or 45) * 60
            now = time.time()
            expired = retention.expire_stale(state, float(config.get("review_ttl_hours") or retention.REVIEW_TTL_HOURS), now)
            if expired:
                log(state, f"{len(expired)} clip(s) waited too long for review and expired")
            if config.get("enabled") and (force_find or expired or due(state.get("last_find"), interval, now)):
                self.find_new_moments(config, state)
                state["last_find"] = now
            self.collect_finished(config, state)
            self.post_approved(config, state)
            self.clean_files(state)
            state["last_run"] = time.time()
            save_state(self.data_dir, state)

    def clean_files(self, state: dict) -> None:
        """Delete files of clips posted or rejected over an hour ago (retention.py)."""
        closed = retention.due_for_cleanup(state, time.time())
        if not closed:
            return
        in_use = retention.jobs_in_use(state)
        freed = 0
        for item in closed:
            try:
                freed += retention.remove_files(item, self.data_dir, in_use)
            except OSError as exc:
                log(state, f"{item['id'][:8]}: could not delete its files ({exc})")
        log(state, f"deleted files of {len(closed)} closed clip(s), {freed / 1e9:.2f} GB freed")

    def loop(self) -> None:
        force = False
        while True:
            more = False
            try:
                self.run_once(force_find=force)
                more = self.restack_new()
            except Exception:
                traceback.print_exc()
            # Every few minutes: collect finished clips and post on time. New
            # moments are looked for only every interval_min (or on /autopilot/run).
            # An approval wakes the loop to post sooner; /autopilot/run also forces a search.
            # Clips still waiting for the stacked layout: go round again at once
            # (posting first), one render per pass.
            self.wake.wait(timeout=0 if more else 5 * 60)
            force = self.run_requested.is_set()
            self.run_requested.clear()
            self.wake.clear()

    # API helpers
    def snapshot(self) -> dict:
        with STATE_LOCK:
            config = load_config(self.data_dir)
            state = load_state(self.data_dir)
        public = {k: v for k, v in config.items() if k != "streamers"}
        public["streamers"] = [{**{k: s.get(k) for k in ("login", "name", "enabled", "since", "platforms",
                                                         "upload_post_user", "campaign")},
                                "accounts": [{"user": a["user"], "name": a.get("name") or a["user"]} for a in posting_accounts(s)]}
                               for s in config.get("streamers", [])]
        campaigns = campaign_rules.load_campaigns(self.data_dir)
        streamers = {s["login"]: s for s in config.get("streamers", [])}
        items = sorted(state.get("items", []), key=lambda i: -i.get("created", 0))[:200]
        items = [{**i, **item_checks(i, streamers.get(i.get("streamer")), campaigns)} for i in items]
        return {"config": public, "posting_ready": bool(os.environ.get("UPLOAD_POST_API_KEY")),
                "last_run": state.get("last_run"), "pending": state.get("pending", []),
                "items": items, "campaigns": campaigns, "log": state.get("log", [])[-30:]}

    def purge(self, status: str = "rejected") -> int:
        """Drop queue items with this status for good (their clip files stay in the engine)."""
        with STATE_LOCK:
            state = load_state(self.data_dir)
            before = len(state.get("items", []))
            state["items"] = [i for i in state.get("items", []) if i.get("status") != status]
            removed = before - len(state["items"])
            if removed:
                log(state, f"removed {removed} {status} clip(s) from the queue")
            save_state(self.data_dir, state)
        return removed

    def _streamer_layout(self, login: str | None) -> dict | None:
        config = load_config(self.data_dir)
        streamer = next((s for s in config.get("streamers", []) if s.get("login") == login), None)
        layout = (streamer or {}).get("layout") or {}
        return layout if layout.get("cam") else None

    def restack_new(self) -> bool:
        """Give ONE new clip of a streamer with a webcam box the stacked layout (webcam
        on top, game below); True while more are waiting. One per call, because a
        render takes ~40 s and the loop must post a clicked clip between renders
        instead of after the whole queue. Renders outside the state lock."""
        with STATE_LOCK:
            state = load_state(self.data_dir)
            # New clips, and stacked clips rendered by an older look (stacked.RENDER_VERSION).
            todo = [(i, layout) for i in state.get("items", [])
                    if i.get("status") == "review" and not i.get("headline")
                    and ("layout" not in i or (i.get("layout") == "stacked"
                                               and i.get("stacked_version") != stacked.RENDER_VERSION))
                    for layout in [self._streamer_layout(i.get("streamer"))] if layout]
        if not todo:
            return False
        for item, layout in todo[:1]:
            error = self.set_layout(item["id"], "stacked", layout)
            if error and error != "not found":
                with STATE_LOCK:
                    state = load_state(self.data_dir)
                    current = next((i for i in state.get("items", []) if i.get("id") == item["id"]), None)
                    if current is not None and "layout" not in current:
                        current.update(layout="engine", layout_error=error[:200])
                        save_state(self.data_dir, state)
        return len(todo) > 1

    def set_layout(self, item_id: str, which: str, layout: dict | None = None) -> str | None:
        """Switch a clip between the stacked layout ("stacked") and the core's own ("engine")."""
        if which not in ("stacked", "engine"):
            return "unknown layout"
        with STATE_LOCK:
            item = next((i for i in load_state(self.data_dir).get("items", []) if i.get("id") == item_id), None)
            if item and which == "stacked" and layout is None:
                layout = self._streamer_layout(item.get("streamer"))
        if not item:
            return "not found"
        if item.get("status") not in ("review", "approved"):
            return f"cannot change a clip that is {item.get('status')}"
        if item.get("headline"):
            return "go back to captions first"
        engine_path = item.get("engine_video_path") or item["video_path"]
        engine_duration = item.get("engine_duration", item.get("duration"))
        new_path, duration = engine_path, engine_duration
        if which == "stacked":
            if not layout:
                return "this streamer has no webcam box set"
            try:
                new_path = stacked.render(engine_path, layout, stacked.folder(self.data_dir), item_id,
                                          hook=thumbnail.hook_text(item))
            except Exception as exc:
                return f"could not stack the clip: {str(exc)[:160]}"
            try:
                src = stacked.sources(engine_path)
                duration = round(src["end"] - src["start"], 1)     # a silent opening was cut
            except (OSError, ValueError):
                pass
        with STATE_LOCK:
            state = load_state(self.data_dir)
            item = next((i for i in state.get("items", []) if i.get("id") == item_id), None)
            if not item:
                return "not found"
            if item.get("headline"):
                return "go back to captions first"
            item.update(layout=which, engine_video_path=engine_path, video_path=new_path,
                        engine_duration=engine_duration, duration=duration, updated=time.time())
            if which == "stacked":
                item["stacked_version"] = stacked.RENDER_VERSION
            item.pop("layout_error", None)
            log(state, f"{item_id[:8]}: " + ("webcam-on-top layout" if which == "stacked" else "core layout"))
            save_state(self.data_dir, state)
        return None

    def _cover(self, item: dict) -> bytes | None:
        """The clip's cover image; a failed cover never blocks the post."""
        try:
            if item.get("headline"):   # the headline version already carries the title
                return thumbnail.render(self.fetch_video(item["video_path"]), "")
            return thumbnail.render(self._clean_clip(item), thumbnail.hook_text(item))
        except Exception as exc:
            print(f"autopilot: cover for {item['id'][:8]} failed: {exc}", flush=True)
            return None

    def _clean_clip(self, item: dict) -> bytes:
        """The clip without burned captions, in the layout it has now."""
        if item.get("layout") == "stacked":
            layout = self._streamer_layout(item.get("streamer"))
            if not layout:
                raise RuntimeError("this streamer has no webcam box set")
            path = stacked.render(item["engine_video_path"], layout, stacked.folder(self.data_dir),
                                  item["id"], captions=False)
            with open(stacked.local_file(self.data_dir, path), "rb") as fh:
                return fh.read()
        return self.fetch_video(headline.clean_clip_path(item.get("original_video_path") or item["video_path"]))

    def set_headline(self, item_id: str, text: str | None) -> str | None:
        """Swap a clip's captions for a headline (text) or back to the captions (None).
        The render runs outside the state lock: it takes a minute on this server."""
        with STATE_LOCK:
            item = next((i for i in load_state(self.data_dir).get("items", []) if i.get("id") == item_id), None)
        if not item:
            return "not found"
        if item.get("status") not in ("review", "approved"):
            return f"cannot change a clip that is {item.get('status')}"
        captioned = item.get("original_video_path") or item["video_path"]
        new_path = captioned
        if text is not None:
            if not headline.lines(text):
                return "write the headline first"
            try:
                src = self._clean_clip(item)
                new_path = headline.render(src, headline.folder(self.data_dir), item_id, text)
            except Exception as exc:
                return f"could not make the headline: {str(exc)[:160]}"
        with STATE_LOCK:
            state = load_state(self.data_dir)
            item = next((i for i in state.get("items", []) if i.get("id") == item_id), None)
            if not item:
                return "not found"
            if text is None:
                item.update(video_path=captioned, updated=time.time())
                for key in ("original_video_path", "overlay", "headline"):
                    item.pop(key, None)
            else:
                item.update(original_video_path=captioned, video_path=new_path, overlay=text,
                            headline=text, updated=time.time())
            log(state, f"{item_id[:8]}: " + ("headline set" if text is not None else "captions back"))
            save_state(self.data_dir, state)
        return None

    def act(self, item_id: str, action: str, campaign_id: str | None = None) -> str | None:
        with STATE_LOCK:
            state = load_state(self.data_dir)
            item = next((i for i in state.get("items", []) if i.get("id") == item_id), None)
            if not item:
                return "not found"
            config = load_config(self.data_dir)
            streamer = next((s for s in config.get("streamers", []) if s["login"] == item.get("streamer")), None)
            campaigns = campaign_rules.load_campaigns(self.data_dir)
            if action == "toggle_campaign":
                error = clip_campaigns.toggle(item, str(campaign_id or ""), clip_campaigns.matching(streamer, campaigns))
                if not error:
                    item["updated"] = time.time()
                    save_state(self.data_dir, state)
                return error
            if action == "post":
                account = next((a for a in posting_accounts(streamer or {}) if a["user"] == campaign_id), None)
                if not account:
                    return "pick a connected channel"
                target = {**streamer, "upload_post_user": account["user"], "platforms": account["platforms"]}
                broken = clip_campaigns.broken_rules(item_checks(item, target, campaigns))
                if broken:
                    return f"breaks a campaign rule: {broken[0]}"
                error = apply_action(item, "approve")
                if not error:
                    item["post_to"] = account["user"]
                    save_state(self.data_dir, state)
                    self.wake.set()
                return error
            if action == "approve":
                return "pick a channel to post to"
            if action == "unreject" and item.get("files_removed"):
                return "its files are already deleted"
            error = apply_action(item, action)
            if not error:
                save_state(self.data_dir, state)
        if not error:
            if action == "reject":          # a free place in the queue: cut the next moment now
                self.run_requested.set()
            self.wake.set()
        return error


def recent_cutoff(hours: int = 24) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
