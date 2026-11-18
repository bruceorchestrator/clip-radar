"""Cover image for a clip: its loudest moment with the hook written on it.

YouTube shows a grey "processing" tile and then a random frame when an upload
has no thumbnail. A clip cover that works is the streamer's reaction plus the
hook in big type, so this takes the frame at the clip's loudest half-second
(usually the reaction), from the clip WITHOUT burned captions, and writes the
hook in the headline style (white capitals on black boxes).

Sent to Upload-Post as `thumbnail` with every YouTube upload.
"""
from __future__ import annotations

import array
import os
import re
import subprocess
import tempfile

import headline

SAMPLE_RATE = 8000
WINDOW_SEC = 0.5
EDGE_SEC = 1.0        # skip the first and last second: cut points, not reactions
MAX_BYTES = 2_000_000  # YouTube's own thumbnail limit
SEAM = 0.32           # webcam band / game boundary of the stacked layout, as a share of height


def hook_text(item: dict) -> str:
    """The words for the cover: the headline if the clip has one, else the hook, no emoji."""
    text = item.get("headline") or item.get("hook") or ""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s'’!?.,:&-]", "", text, flags=re.UNICODE)).strip()


def loudest_moment(samples: array.array, rate: int = SAMPLE_RATE, window: float = WINDOW_SEC,
                   edge: float = EDGE_SEC) -> float:
    """Middle of the loudest window (seconds), away from the clip's edges."""
    size = max(1, int(rate * window))
    count = len(samples) // size
    if count == 0:
        return 0.0
    first = min(int(edge / window), count - 1)
    last = max(first + 1, count - int(edge / window))
    best, best_energy = first, -1
    for n in range(first, last):
        chunk = samples[n * size:(n + 1) * size]
        energy = sum(s * s for s in chunk)
        if energy > best_energy:
            best, best_energy = n, energy
    return (best + 0.5) * window


def _audio(path: str) -> array.array:
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-vn", "-ac", "1",
                          "-ar", str(SAMPLE_RATE), "-f", "s16le", "pipe:1"],
                         capture_output=True, check=True, timeout=300).stdout
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    return samples


def render(clean_clip: bytes, text: str) -> bytes:
    """JPEG cover from a clip without captions; `text` may be empty (frame only)."""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "clip.mp4")
        with open(src, "wb") as fh:
            fh.write(clean_clip)
        try:
            at = loudest_moment(_audio(src))
        except subprocess.CalledProcessError:   # no audio track
            at = 1.0
        width, height = headline._probe(src)
        rows = headline.lines(text, "vertical" if height > width else "horizontal") if text else []
        textfiles = []
        for i, row in enumerate(rows):
            path = os.path.join(tmp, f"line{i}.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(row)
            textfiles.append(path)
        # On a vertical clip the block sits around the seam of the stacked layout
        # (a third down), clear of the streamer's face in the webcam band.
        top = None
        if rows and height > width:
            top = max(0, int(height * SEAM - headline.block_height(len(rows), width, height) / 2))
        vf = headline.filter_graph(rows, textfiles, width, height, top) if rows else "null"
        out = os.path.join(tmp, "cover.jpg")
        for quality in (3, 6, 10):
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", src,
                            "-frames:v", "1", "-vf", vf, "-q:v", str(quality), out],
                           check=True, timeout=120, capture_output=True)
            if os.path.getsize(out) <= MAX_BYTES:
                break
        with open(out, "rb") as fh:
            return fh.read()
