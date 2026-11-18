"""Stacked layout: the streamer's webcam big on top, the game below, no corner cam.

What clippers post for stream clips: the facecam fills the top band and a crop of
the game fills the rest, captions sit on the seam. The core's own layouts decide
per scene (inset, blurred, face tracking) and switch inside one clip, and its
inset keeps the whole stream frame, so the small corner webcam shows up a second
time. This module ignores the core's framing: it cuts the same stretch of the
source stream again with fixed boxes for the whole clip.

Inputs, all left by the core in its volumes (mounted read-only into the gateway):
  <uploads>/<job>_stretch.mp4                the downloaded stream stretch (1080p)
  <output>/<job>/<job>_stretch_metadata.json clip start/end inside that stretch
  <output>/<job>/autosubs_<ts>_*.ass         the clip's word captions, clip-relative
The webcam box is per streamer (autopilot.json: layout.cam, fractions of the frame),
because a streamer's camera stays in the same corner for the whole stream.

Files go to <DATA_DIR>/stacked and are served as /videos/stacked/<name>.mp4.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile

PREFIX = "/videos/stacked/"
NAME = re.compile(r"[0-9a-f]{32}-[0-9a-f]{8}\.mp4")
ENGINE_OUTPUT = os.environ.get("ENGINE_OUTPUT", "/engine/output")
ENGINE_UPLOADS = os.environ.get("ENGINE_UPLOADS", "/engine/uploads")
FONTS_DIR = os.environ.get("FONTS_DIR", "/app/fonts")
OUT_W, OUT_H = 1080, 1920
FPS = 30
CAPTION_SIZE = 104         # px on the 1080x1920 frame
DURATION_SLACK = 0.6       # s; metadata clip length vs the core's clip

CLIP = re.compile(r"/videos/(?P<job>[0-9a-f-]{36})/(?:subtitled_(?P<ts>\d+)_)?(?P=job)_stretch_clip_(?P<n>\d+)\.mp4")


def folder(data_dir: str) -> str:
    path = os.path.join(data_dir, "stacked")
    os.makedirs(path, exist_ok=True)
    return path


def is_local(video_path: str) -> bool:
    return video_path.startswith(PREFIX) and bool(NAME.fullmatch(video_path[len(PREFIX):]))


def local_file(data_dir: str, video_path: str) -> str | None:
    if not is_local(video_path):
        return None
    return os.path.join(folder(data_dir), video_path[len(PREFIX):])


def parse_clip(video_path: str) -> dict | None:
    """Job, clip number and caption stamp from a core clip path."""
    match = CLIP.fullmatch(video_path)
    if not match:
        return None
    return {"job": match["job"], "n": int(match["n"]), "ts": match["ts"]}


def _even(v: float) -> int:
    return max(2, int(round(v / 2)) * 2)


def geometry(src_w: int, src_h: int, cam: list[float], game_center: float = 0.5,
             out_w: int = OUT_W, out_h: int = OUT_H) -> dict:
    """Crop boxes (x, y, w, h in source pixels) and band heights for the stacked frame.

    cam: [x0, y0, x1, y1] as fractions of the source frame. The top band shows the
    whole webcam at its own aspect; the game crop fills the rest at full source
    height and is kept clear of the webcam's columns, so the corner cam never shows.
    """
    x0, y0, x1, y1 = (min(max(float(v), 0.0), 1.0) for v in cam)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("webcam box is empty")
    cx, cy = int(x0 * src_w), int(y0 * src_h)
    cw, ch = _even((x1 - x0) * src_w), _even((y1 - y0) * src_h)
    top_h = min(_even(out_w * ch / cw), out_h // 2)
    game_h = out_h - top_h
    gw = min(_even(src_h * out_w / game_h), src_w)
    gx = int(game_center * src_w - gw / 2)
    if (x0 + x1) / 2 < 0.5:          # webcam on the left: start right of it
        gx = max(gx, cx + cw)
    else:                             # on the right: end left of it
        gx = min(gx, cx - gw)
    gx = min(max(gx, 0), src_w - gw)
    return {"cam": (cx, cy, cw, ch), "game": (gx, 0, gw, src_h), "top_h": top_h, "game_h": game_h,
            "out": (out_w, out_h)}


def restyle_ass(text: str, top_h: int, out_w: int = OUT_W, out_h: int = OUT_H,
                size: int = CAPTION_SIZE) -> str:
    """The core's captions moved to the seam between the webcam and the game.

    Keeps every Dialogue line (timing, highlight colours, pop animation) and
    rewrites only the canvas size and the Default style's size, outline and place.
    """
    out, fields = [], None
    for line in text.splitlines():
        stripped = line.lstrip("﻿")
        if re.match(r"PlayRes[XY]\s*:", stripped):
            continue
        if stripped.strip() == "[Script Info]":
            out += ["[Script Info]", f"PlayResX: {out_w}", f"PlayResY: {out_h}"]
            continue
        if stripped.startswith("Format:") and fields is None and "Fontsize" in stripped:
            fields = [f.strip() for f in stripped[len("Format:"):].split(",")]
        elif stripped.startswith("Style:") and fields:
            values = [v.strip() for v in stripped[len("Style:"):].split(",")]
            if len(values) == len(fields):
                style = dict(zip(fields, values))
                style.update(Fontsize=str(size), Outline=str(max(4, size // 14)), Shadow="0",
                             Alignment="8", MarginL="40", MarginR="40",
                             MarginV=str(max(0, top_h - int(size * 0.6))))
                stripped = "Style: " + ",".join(style[f] for f in fields)
        out.append(stripped)
    return "\n".join(out) + "\n"


def filter_graph(geom: dict, ass_path: str | None) -> str:
    cx, cy, cw, ch = geom["cam"]
    gx, gy, gw, gh = geom["game"]
    out_w, _ = geom["out"]
    graph = (f"[0:v]split=2[c][g];"
             f"[c]crop={cw}:{ch}:{cx}:{cy},scale={out_w}:{geom['top_h']}:flags=lanczos,setsar=1[top];"
             f"[g]crop={gw}:{gh}:{gx}:{gy},scale={out_w}:{geom['game_h']}:flags=lanczos,setsar=1[bot];"
             f"[top][bot]vstack=inputs=2,fps={FPS},format=yuv420p")
    if ass_path:
        graph += f",subtitles={ass_path}:fontsdir={FONTS_DIR}"
    return graph + "[v]"


def sources(video_path: str, output_dir: str = ENGINE_OUTPUT, uploads_dir: str = ENGINE_UPLOADS) -> dict:
    """Where the clip comes from in the stream stretch, and its captions file."""
    clip = parse_clip(video_path)
    if not clip:
        raise ValueError("not a core clip")
    job_dir = os.path.join(output_dir, clip["job"])
    with open(os.path.join(job_dir, f"{clip['job']}_stretch_metadata.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    shorts = meta.get("shorts") or []
    if not 1 <= clip["n"] <= len(shorts):
        raise ValueError("clip is missing from the core's metadata")
    short = shorts[clip["n"] - 1]
    start, end = float(short["start"]), float(short["end"])
    layout = os.path.join(job_dir, f"{clip['job']}_stretch_clip_{clip['n']}.mp4.layout.json")
    if os.path.exists(layout):
        with open(layout, encoding="utf-8") as fh:
            ranges = json.load(fh).get("ranges") or []
        if ranges and abs(float(ranges[-1]["end"]) - (end - start)) > DURATION_SLACK:
            raise ValueError("the core's clip is not one straight cut of the stream")
    stretch = os.path.join(uploads_dir, meta.get("source_video") or f"{clip['job']}_stretch.mp4")
    if not os.path.exists(stretch):
        raise FileNotFoundError("the stream stretch is gone from the core")
    ass = None
    if clip["ts"]:
        found = sorted(glob.glob(os.path.join(job_dir, f"autosubs_{clip['ts']}_*.ass")))
        ass = found[0] if found else None
    return {"stretch": stretch, "start": start, "end": end, "ass": ass}


def _probe(path: str) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0:s=x", path],
                         capture_output=True, text=True, check=True).stdout.strip()
    w, h = out.split("x")[:2]
    return int(w), int(h)


def render(video_path: str, layout: dict, out_dir: str, item_id: str, captions: bool = True,
           output_dir: str = ENGINE_OUTPUT, uploads_dir: str = ENGINE_UPLOADS) -> str:
    """Render the stacked version of a core clip; returns its /videos/stacked/ path."""
    src = sources(video_path, output_dir, uploads_dir)
    src_w, src_h = _probe(src["stretch"])
    geom = geometry(src_w, src_h, layout["cam"], float(layout.get("game_center", 0.5)))
    key = json.dumps([video_path, layout, captions, CAPTION_SIZE], sort_keys=True)
    name = f"{item_id}-{hashlib.sha1(key.encode()).hexdigest()[:8]}.mp4"
    out_path = os.path.join(out_dir, name)
    if os.path.exists(out_path):
        return PREFIX + name
    with tempfile.TemporaryDirectory() as tmp:
        ass_path = None
        if captions and src["ass"]:
            ass_path = os.path.join(tmp, "captions.ass")
            with open(src["ass"], encoding="utf-8-sig") as fh:
                styled = restyle_ass(fh.read(), geom["top_h"], *geom["out"])
            with open(ass_path, "w", encoding="utf-8") as fh:
                fh.write(styled)
        tmp_out = os.path.join(tmp, "out.mp4")
        run = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y",
                              "-ss", f"{src['start']:.3f}", "-to", f"{src['end']:.3f}", "-i", src["stretch"],
                              "-filter_complex", filter_graph(geom, ass_path), "-map", "[v]", "-map", "0:a?",
                              "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                              "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", tmp_out],
                             timeout=900, capture_output=True, text=True)
        if run.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {run.stderr.strip()[-300:]}")
        shutil.move(tmp_out, out_path)
    return PREFIX + name
