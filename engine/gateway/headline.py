"""Headline instead of captions: the clean clip with one big title on top.

Auto-captions fail when the streamer talks over music or game sound (Whisper
loses the speech), and a wrong caption is worse than none. For those clips the
reviewer swaps the captions for a headline: the engine's own clip WITHOUT burned
subtitles, plus white capitals on black boxes near the top, one box per line.

Files are rendered here in the gateway (it has ffmpeg) and kept in
<DATA_DIR>/headlines, served as /videos/headline/<name>.mp4.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import textwrap

PREFIX = "/videos/headline/"
FONT = os.environ.get("HEADLINE_FONT", "/app/fonts/Anton-Regular.ttf")
MAX_CHARS = 90
LINE_CHARS = {"vertical": 16, "horizontal": 30}
NAME = re.compile(r"[0-9a-f]{32}-[0-9a-f]{8}\.mp4")


def folder(data_dir: str) -> str:
    path = os.path.join(data_dir, "headlines")
    os.makedirs(path, exist_ok=True)
    return path


def is_local(video_path: str) -> bool:
    return video_path.startswith(PREFIX) and bool(NAME.fullmatch(video_path[len(PREFIX):]))


def local_file(data_dir: str, video_path: str) -> str | None:
    """Disk path for a /videos/headline/... path, or None when it is not one of ours."""
    if not is_local(video_path):
        return None
    return os.path.join(folder(data_dir), video_path[len(PREFIX):])


def clean_clip_path(video_path: str) -> str:
    """The engine's clip without burned subtitles: drop the 'subtitled_<ts>_' prefix."""
    head, _, name = video_path.rpartition("/")
    clean = re.sub(r"^subtitled_\d+_", "", name)
    return f"{head}/{clean}"


def lines(text: str, fmt: str = "vertical") -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()[:MAX_CHARS].upper()
    return textwrap.wrap(text, LINE_CHARS.get(fmt, 16)) or []


def _probe(path: str) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0:s=x", path],
                         capture_output=True, text=True, check=True).stdout.strip()
    w, h = out.split("x")[:2]
    return int(w), int(h)


def _metrics(width: int, height: int) -> tuple[int, int, int]:
    """Font size, box padding and line step for a frame."""
    vertical = height > width
    size = int((width if vertical else height) * (0.075 if vertical else 0.07))
    pad = int(size * 0.3)
    return size, pad, size + 2 * pad + int(size * 0.12)


def block_height(rows: int, width: int, height: int) -> int:
    _, _, step = _metrics(width, height)
    return rows * step


def filter_graph(rows: list[str], textfiles: list[str], width: int, height: int, top: int | None = None) -> str:
    """One drawtext per line, each centred on its own black box; `top` moves the block."""
    size, pad, step = _metrics(width, height)
    if top is None:
        top = int(height * (0.07 if height > width else 0.05))
    parts = []
    for i, path in enumerate(textfiles):
        parts.append(f"drawtext=fontfile={FONT}:textfile={path}:fontsize={size}:fontcolor=white"
                     f":box=1:boxcolor=black:boxborderw={pad}:x=(w-tw)/2:y={top + i * step}")
    return ",".join(parts)


def render(src: bytes, out_dir: str, item_id: str, text: str) -> str:
    """Render the headline version of a clean clip; returns its /videos/headline/ path."""
    if not FONT or not os.path.exists(FONT):
        raise RuntimeError("headline font is missing on the server")
    with tempfile.TemporaryDirectory() as tmp:
        src_path = os.path.join(tmp, "src.mp4")
        with open(src_path, "wb") as fh:
            fh.write(src)
        width, height = _probe(src_path)
        rows = lines(text, "vertical" if height > width else "horizontal")
        if not rows:
            raise ValueError("write the headline first")
        textfiles = []
        for i, row in enumerate(rows):
            path = os.path.join(tmp, f"line{i}.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(row)
            textfiles.append(path)
        digest = hashlib.sha1(f"{text}|{len(src)}".encode()).hexdigest()[:8]
        name = f"{item_id}-{digest}.mp4"
        out_path = os.path.join(out_dir, name)
        tmp_out = os.path.join(tmp, "out.mp4")
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", src_path,
                        "-vf", filter_graph(rows, textfiles, width, height),
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy",
                        "-movflags", "+faststart", tmp_out], check=True, timeout=600)
        shutil.move(tmp_out, out_path)  # tmp and /data can be different filesystems
    return PREFIX + name
