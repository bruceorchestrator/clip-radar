"""Clip Radar gateway: the only door to the clipping engine.

Runs next to the unmodified OpenShorts core on a private network. It turns
"clip this link" into one or more engine jobs:

- a short video goes to the engine whole;
- a chosen stretch, or the hot stretches of a long stream (see planner.py),
  is cut here with yt-dlp and handed to the engine as a file.

HTTP API (JSON, no auth: bind it to localhost or a private network only):
  POST /batches  {"url", "start"?, "end"?}      -> {"id"}
  GET  /batches/<id>                            -> batch with tasks and engine status
  GET  /videos/<engine job>/<file>              -> the clip, Range supported
  GET  /health
"""
from __future__ import annotations

import http.client
import json
import os
import queue
import re
import subprocess
import threading
import time
import traceback
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import autopilot
import campaign_api
import headline
import stacked
import campaigns
import hls
import planner

ENGINE = urlparse(os.environ.get("ENGINE_URL", "http://backend:8000"))
DATA_DIR = os.environ.get("DATA_DIR", "/data")
PORT = int(os.environ.get("PORT", "8100"))
MIN_STRETCH_SEC = 45
MAX_STRETCH_SEC = 600
LENGTHS = {"short": (15, 30), "medium": (15, 45), "long": (30, 60)}
# vertical: 9:16 reframe (Shorts, TikTok, Reels). horizontal: the stream frame as is (X).
FORMATS = ("vertical", "horizontal")
MAX_CLIPS = 30
ALLOWED_HOSTS = ("twitch.tv", "kick.com", "youtube.com", "youtu.be")
BATCH_ID = re.compile(r"^[0-9a-f]{32}$")
TWITCH_GQL = "https://gql.twitch.tv/gql"
TWITCH_WEB_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"  # public, the one twitch.tv uses
VOD_PATH = re.compile(r"^/(?:[^/]+/)?videos?/(\d+)/?$")

_lock = threading.Lock()
_work: "queue.Queue[str]" = queue.Queue()


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
def _path(batch_id: str) -> str:
    return os.path.join(DATA_DIR, "batches", f"{batch_id}.json")


def load(batch_id: str) -> dict | None:
    try:
        with open(_path(batch_id), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def save(batch: dict) -> None:
    with _lock:
        tmp = _path(batch["id"]) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(batch, f)
        os.replace(tmp, _path(batch["id"]))


def update(batch: dict, **fields) -> None:
    batch.update(fields)
    batch["updated"] = time.time()
    save(batch)


# --------------------------------------------------------------------------- #
# Source helpers
# --------------------------------------------------------------------------- #
def supported(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


def run(cmd: list[str], timeout: int) -> str:
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        tail = (out.stderr or out.stdout).strip().splitlines()[-1:] or ["unknown error"]
        raise RuntimeError(tail[0][:300])
    return out.stdout


def probe(url: str) -> dict:
    info = json.loads(run(["yt-dlp", "-J", "--no-warnings", "--no-playlist", url], 120))
    return {"duration": float(info.get("duration") or 0), "title": info.get("title") or ""}


def twitch_vod_id(url: str) -> str | None:
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() not in ("twitch.tv", "www.twitch.tv", "m.twitch.tv"):
        return None
    match = VOD_PATH.match(parsed.path or "")
    return match.group(1) if match else None


def _gql(query: str, variables: dict, attempts: int = 3) -> dict:
    """Twitch's web GraphQL answers "service error" now and then: retry."""
    last = "gql error"
    for attempt in range(attempts):
        req = urllib.request.Request(
            TWITCH_GQL, data=json.dumps({"query": query, "variables": variables}).encode(),
            headers={"Client-ID": TWITCH_WEB_CLIENT_ID, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = json.load(resp)
            if not body.get("errors"):
                return body["data"]
            last = body["errors"][0].get("message", "gql error")
        except OSError as exc:
            last = str(exc)
        time.sleep(1 + attempt)
    raise RuntimeError(last)


CLIPS_QUERY = """query($login:String!,$period:ClipsPeriod!,$first:Int!){ user(login:$login){
  clips(first:$first, criteria:{period:$period, sort:VIEWS_DESC}){ edges{ node{
    slug viewCount durationSeconds videoOffsetSeconds video{ id } } } } } }"""


def viewer_clips(vod_id: str) -> list[dict]:
    """Clips viewers made from this VOD, with their position in it. Best effort."""
    try:
        owner = _gql("query($id:ID!){ video(id:$id){ owner{ login } } }", {"id": vod_id})
        login = ((owner.get("video") or {}).get("owner") or {}).get("login")
        if not login:
            return []
        out = []
        for period in ("LAST_WEEK", "LAST_MONTH"):
            try:
                data = _gql(CLIPS_QUERY, {"login": login, "period": period, "first": 100})
            except RuntimeError:
                # A full page fails more often than a smaller one.
                data = _gql(CLIPS_QUERY, {"login": login, "period": period, "first": 50})
            for edge in ((data.get("user") or {}).get("clips") or {}).get("edges") or []:
                node = edge["node"]
                if (node.get("video") or {}).get("id") == vod_id and node.get("videoOffsetSeconds") is not None:
                    out.append({"slug": node["slug"], "start": node["videoOffsetSeconds"],
                                "duration": node["durationSeconds"], "views": node["viewCount"]})
        unique = {c["slug"]: c for c in out}
        return list(unique.values())
    except Exception as exc:  # the signal is optional
        print(f"viewer clips skipped: {exc}", flush=True)
        return []


LEVEL_LINE = re.compile(r"lavfi\.astats\.Overall\.RMS_level=(-?inf|-?[\d.]+)")


def audio_levels(url: str) -> list[float]:
    """RMS level in dB for every second of the source's audio. Best effort."""
    try:
        media = run(["yt-dlp", "-g", "-f", "bestaudio/worst", "--no-warnings", url], 120).split()[0]
        out = subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", media, "-vn",
             "-af", "aresample=8000,asetnsamples=n=8000,astats=metadata=1:reset=1,"
                    "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=3 * 3600)
        return [float(v) if "inf" not in v else -120.0 for v in LEVEL_LINE.findall(out.stdout)]
    except Exception as exc:
        print(f"audio levels skipped: {exc}", flush=True)
        return []


def cut(url: str, start: float, end: float, dest: str) -> None:
    """Stream recordings (Twitch, Kick) are HLS: fetch only the needed segments.
    Anything else falls back to yt-dlp's section download."""
    try:
        media = run(["yt-dlp", "-g", "--no-warnings", "--no-playlist",
                     "-f", "best[protocol^=m3u8][height<=1080]/best[protocol^=m3u8]", url], 120).split()
    except RuntimeError:
        media = []
    if media and ".m3u8" in media[0]:
        hls.cut(media[0], start, end, dest)
    else:
        _cut_with_ytdlp(url, start, end, dest)
    if not os.path.exists(dest) or os.path.getsize(dest) < 10_000:
        raise RuntimeError("the stretch could not be downloaded")


def _cut_with_ytdlp(url: str, start: float, end: float, dest: str) -> None:
    run(["yt-dlp", "--no-warnings", "--no-playlist", "--no-part",
         "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
         "--download-sections", f"*{start:.3f}-{end:.3f}",
         "--merge-output-format", "mp4", "-o", dest, url], 1800)


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
def engine_conn(timeout: int = 60) -> http.client.HTTPConnection:
    return http.client.HTTPConnection(ENGINE.hostname, ENGINE.port or 80, timeout=timeout)


def engine_json(method: str, path: str, body: dict | None = None, timeout: int = 60) -> dict:
    conn = engine_conn(timeout)
    try:
        conn.request(method, path, body=json.dumps(body) if body is not None else None,
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = json.loads(resp.read() or b"{}")
        if resp.status >= 400:
            raise RuntimeError(str(data.get("detail") or f"engine HTTP {resp.status}")[:300])
        return data
    finally:
        conn.close()


def clip_settings(batch: dict, n_tasks: int) -> dict:
    lo, hi = LENGTHS.get(batch.get("length") or "medium", LENGTHS["medium"])
    per_task = max(1, min(15, -(-int(batch.get("clips") or 10) // max(1, n_tasks))))
    fmt = batch.get("format") if batch.get("format") in FORMATS else "vertical"
    return {"target_clips": per_task, "clip_min_seconds": lo, "clip_max_seconds": hi, "output_format": fmt}


def engine_submit_file(path: str, settings: dict) -> str:
    slot = engine_json("POST", "/api/uploads", {"filename": "stretch.mp4"})
    upload_path = urlparse(slot["upload_url"]).path
    conn = engine_conn(600)
    try:
        with open(path, "rb") as f:
            conn.request("PUT", upload_path, body=f,
                         headers={"Content-Length": str(os.path.getsize(path)),
                                  "Content-Type": "application/octet-stream"})
            resp = conn.getresponse()
            resp.read()
            if resp.status >= 400:
                raise RuntimeError(f"upload refused: HTTP {resp.status}")
    finally:
        conn.close()
    job = engine_json("POST", "/api/process", {"upload_id": slot["upload_id"], "acknowledged": True,
                                               "output_format": "vertical", **settings})  # settings may override
    return job["job_id"]


def engine_submit_url(url: str, settings: dict) -> str:
    return engine_json("POST", "/api/process", {"url": url, "acknowledged": True,
                                                "output_format": "vertical", **settings})["job_id"]


def engine_status(job_id: str) -> dict:
    try:
        data = engine_json("GET", f"/api/status/{job_id}", timeout=15)
        return {"status": data.get("status"), "logs": (data.get("logs") or [])[-30:],
                "result": data.get("result")}
    except Exception as exc:
        return {"status": "unknown", "logs": [], "result": None, "error": str(exc)[:200]}


# --------------------------------------------------------------------------- #
# Worker
# --------------------------------------------------------------------------- #
def plan_batch(batch: dict) -> list[dict]:
    if batch.get("start") is not None and batch.get("end") is not None:
        return [{"start": batch["start"], "end": batch["end"], "reason": "chosen stretch"}]
    update(batch, stage="Checking the video…")
    info = probe(batch["url"])
    update(batch, duration=info["duration"], title=info["title"])
    if info["duration"] <= planner.SHORT_SOURCE_SEC or batch.get("mode") == "whole":
        return [{"start": None, "end": None, "reason": "whole video"}]
    update(batch, stage="Finding the hot moments in the stream…")
    vod = twitch_vod_id(batch["url"])
    clips = viewer_clips(vod) if vod else []
    levels = []
    if len(planner.viewer_hotspots(clips)) < planner.ENOUGH_VIEWER_SPOTS:
        update(batch, stage="Listening for the loudest reactions…")
        levels = audio_levels(batch["url"])
    stretches = planner.plan(info["duration"], clips, levels,
                             max_stretches=planner.stretches_for(batch.get("clips") or 10))
    return [{"start": s.start, "end": s.end, "reason": s.reason} for s in stretches]


def process(batch_id: str) -> None:
    batch = load(batch_id)
    if not batch:
        return
    try:
        tasks = plan_batch(batch)
        update(batch, tasks=[{**t, "state": "waiting", "engine_job_id": None, "error": None} for t in tasks],
               stage="Cutting the stretches…", status="running")
        settings = clip_settings(batch, len(tasks))
        for i, task in enumerate(batch["tasks"]):
            task["state"] = "cutting"
            update(batch)
            try:
                if task["start"] is None:
                    task["engine_job_id"] = engine_submit_url(batch["url"], settings)
                else:
                    dest = os.path.join(DATA_DIR, "tmp", f"{batch_id}_{i}.mp4")
                    try:
                        cut(batch["url"], task["start"], task["end"], dest)
                        task["engine_job_id"] = engine_submit_file(dest, settings)
                    finally:
                        if os.path.exists(dest):
                            os.remove(dest)
                task["state"] = "submitted"
            except Exception as exc:
                task["state"], task["error"] = "failed", str(exc)[:300]
            update(batch)
        update(batch, stage=None)
    except Exception as exc:
        traceback.print_exc()
        update(batch, status="failed", stage=None, error=str(exc)[:300])


def worker() -> None:
    while True:
        batch_id = _work.get()
        try:
            process(batch_id)
        finally:
            _work.task_done()


def preview(url: str) -> dict:
    """What the user sees before starting: length and where the hot moments are.

    Fast on purpose (a few seconds): no audio scan here, only viewer clips.
    """
    info = probe(url)
    spots = []
    if info["duration"] > planner.SHORT_SOURCE_SEC:
        vod = twitch_vod_id(url)
        for t, weight in planner.viewer_hotspots(viewer_clips(vod) if vod else []):
            spots.append({"t": round(t, 1), "weight": weight})
    return {"duration": info["duration"], "title": info["title"],
            "long": info["duration"] > planner.SHORT_SOURCE_SEC,
            "stretch_sec": planner.STRETCH_SEC, "hotspots": spots}


def new_batch(url: str, start, end, mode: str, clips: int, clip_length: str, fmt: str = "vertical") -> str:
    batch = {"id": uuid.uuid4().hex, "url": url, "start": start, "end": end,
             "mode": "stretch" if start is not None else mode, "clips": clips,
             "length": clip_length, "format": fmt, "status": "planning", "stage": "Waiting in line…",
             "tasks": [], "created": time.time()}
    save(batch)
    _work.put(batch["id"])
    return batch["id"]


def fetch_any_video(path: str) -> bytes:
    """Engine clips over HTTP; headline and stacked versions from the gateway's own disk."""
    local = headline.local_file(DATA_DIR, path) or stacked.local_file(DATA_DIR, path)
    if local:
        with open(local, "rb") as fh:
            return fh.read()
    return fetch_engine_video(path)


def fetch_engine_video(path: str) -> bytes:
    conn = engine_conn(300)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        data = resp.read()
        if resp.status != 200:
            raise RuntimeError(f"clip not available: HTTP {resp.status}")
        return data
    finally:
        conn.close()


def view(batch: dict) -> dict:
    tasks = []
    for task in batch.get("tasks") or []:
        engine = engine_status(task["engine_job_id"]) if task.get("engine_job_id") else None
        tasks.append({**task, "engine": engine})
    status = batch.get("status", "planning")
    if status == "running" and tasks and all(t["state"] in ("submitted", "failed") for t in tasks):
        finals = [(t["engine"] or {}).get("status") if t["state"] == "submitted" else "failed" for t in tasks]
        if all(s in ("completed", "failed") for s in finals):
            status = "completed" if "completed" in finals else "failed"
    return {"id": batch["id"], "url": batch["url"], "status": status, "stage": batch.get("stage"),
            "duration": batch.get("duration"), "title": batch.get("title"), "format": batch.get("format", "vertical"),
            "error": batch.get("error"), "tasks": tasks}


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            return self._json(200, {"status": "ok"})
        if self.path.startswith("/batches/"):
            batch_id = self.path.split("/")[2]
            batch = load(batch_id) if BATCH_ID.match(batch_id) else None
            return self._json(200, view(batch)) if batch else self._json(404, {"error": "not found"})
        bare = self.path.split("?")[0]
        if headline.is_local(bare) or stacked.is_local(bare):
            return self._send_file(headline.local_file(DATA_DIR, bare) or stacked.local_file(DATA_DIR, bare))
        if self.path.startswith("/videos/") and ".." not in self.path:
            return self._proxy_video()
        if self.path == "/campaigns":
            return self._json(200, {"campaigns": campaigns.load_campaigns(DATA_DIR)})
        if self.path == "/autopilot":
            return self._json(200, AUTOPILOT.snapshot())
        return self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path == "/autopilot/run":
            AUTOPILOT.run_requested.set()
            AUTOPILOT.wake.set()
            return self._json(202, {"status": "started"})
        if self.path == "/autopilot/purge-rejected":
            return self._json(200, {"removed": AUTOPILOT.purge("rejected")})
        if self.path.startswith("/campaigns"):
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(min(length, 60_000)) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._json(400, {"error": "Send a JSON body."})
            return self._json(*campaign_api.handle_post(self.path, body if isinstance(body, dict) else {}, DATA_DIR))
        if self.path.startswith("/autopilot/items/"):
            item_id = self.path.split("/")[3]
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(min(length, 1000)) or b"{}")
                action, campaign_id = body.get("action"), body.get("campaign")
            except (ValueError, json.JSONDecodeError, AttributeError):
                return self._json(400, {"error": "Send a JSON body."})
            if action in ("headline", "captions"):
                text = str(body.get("text") or "") if action == "headline" else None
                error = AUTOPILOT.set_headline(item_id, text)
                if error == "not found":
                    return self._json(404, {"error": error})
                return self._json(400, {"error": error}) if error else self._json(200, {"status": "ok"})
            if action == "layout":
                error = AUTOPILOT.set_layout(item_id, str(body.get("text") or ""))
                if error == "not found":
                    return self._json(404, {"error": error})
                return self._json(400, {"error": error}) if error else self._json(200, {"status": "ok"})
            error = AUTOPILOT.act(item_id, str(action or ""), str(campaign_id) if campaign_id else None)
            if error == "not found":
                return self._json(404, {"error": error})
            return self._json(400, {"error": error}) if error else self._json(200, {"status": "ok"})
        if self.path not in ("/batches", "/preview"):
            return self._json(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(length, 10_000)) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "Send a JSON body."})
        url = str(body.get("url") or "").strip()
        if not supported(url):
            return self._json(400, {"error": "Paste a Twitch, Kick or YouTube link."})
        if self.path == "/preview":
            try:
                return self._json(200, preview(url))
            except Exception as exc:
                return self._json(422, {"error": f"Could not read this video: {str(exc)[:160]}"})
        mode = body.get("mode") or "auto"
        if mode not in ("auto", "whole", "stretch"):
            return self._json(400, {"error": "Unknown mode."})
        try:
            clips = int(body.get("clips") or 10)
        except (TypeError, ValueError):
            return self._json(400, {"error": "clips must be a number."})
        if not 1 <= clips <= MAX_CLIPS:
            return self._json(400, {"error": f"Ask for 1 to {MAX_CLIPS} clips."})
        clip_length = body.get("length") or "medium"
        if clip_length not in LENGTHS:
            return self._json(400, {"error": "Unknown clip length."})
        start, end = body.get("start"), body.get("end")
        if (start is None) != (end is None):
            return self._json(400, {"error": "Send both start and end, or neither."})
        if start is not None:
            try:
                start, end = float(start), float(end)
            except (TypeError, ValueError):
                return self._json(400, {"error": "Start and end must be seconds."})
            if start < 0 or not MIN_STRETCH_SEC <= end - start <= MAX_STRETCH_SEC:
                return self._json(400, {"error": f"Pick {MIN_STRETCH_SEC} seconds to "
                                                 f"{MAX_STRETCH_SEC // 60} minutes of the video."})
        if mode == "stretch" and start is None:
            return self._json(400, {"error": "Pick the stretch to clip."})
        fmt = body.get("format") or "vertical"
        if fmt not in FORMATS:
            return self._json(400, {"error": "Unknown format."})
        return self._json(201, {"id": new_batch(url, start, end, mode, clips, clip_length, fmt)})

    def _send_file(self, path: str | None) -> None:
        """A gateway-made video (headline versions), with Range support for players."""
        if not path or not os.path.exists(path):
            return self._json(404, {"error": "not found"})
        size = os.path.getsize(path)
        start, end = 0, size - 1
        match = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        if match and (match.group(1) or match.group(2)):
            if match.group(1):
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else end
            else:
                start = max(0, size - int(match.group(2)))
            end = min(end, size - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        try:
            with open(path, "rb") as fh:
                fh.seek(start)
                left = end - start + 1
                while left > 0 and (chunk := fh.read(min(256 * 1024, left))):
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _proxy_video(self) -> None:
        conn = engine_conn(120)
        try:
            headers = {"Range": self.headers["Range"]} if self.headers.get("Range") else {}
            conn.request("GET", self.path, headers=headers)
            resp = conn.getresponse()
            self.send_response(resp.status)
            for name in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
                if resp.getheader(name):
                    self.send_header(name, resp.getheader(name))
            self.end_headers()
            while chunk := resp.read(256 * 1024):
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            conn.close()

    def log_message(self, fmt, *args):  # quieter: one line per request
        print(f"{self.command} {self.path.split('?')[0]} {args[1] if len(args) > 1 else ''}", flush=True)


def recover() -> None:
    """Batches cut off by a restart are marked failed instead of hanging."""
    folder = os.path.join(DATA_DIR, "batches")
    for name in os.listdir(folder):
        if not name.endswith(".json"):
            continue
        batch = load(name[:-5])
        if batch and batch.get("status") == "planning" or (
                batch and any(t.get("state") in ("waiting", "cutting") for t in batch.get("tasks") or [])):
            for t in batch.get("tasks") or []:
                if t.get("state") in ("waiting", "cutting"):
                    t["state"], t["error"] = "failed", "interrupted by a restart"
            if batch.get("status") == "planning":
                batch["status"], batch["error"] = "failed", "interrupted by a restart"
            batch["stage"] = None
            save(batch)


AUTOPILOT = autopilot.Autopilot(
    DATA_DIR,
    gql=lambda query, variables: _gql(query, variables),
    create_batch=lambda url, start, end, clips, length: new_batch(url, start, end, "stretch", clips, length),
    view_batch=lambda batch: view(batch),
    load_batch=lambda batch_id: load(batch_id),
    fetch_video=fetch_any_video,
)


def main() -> None:
    os.makedirs(os.path.join(DATA_DIR, "batches"), exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "tmp"), exist_ok=True)
    recover()
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=AUTOPILOT.loop, daemon=True).start()
    print(f"gateway on :{PORT}, engine {ENGINE.geturl()}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
