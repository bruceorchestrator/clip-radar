"""Cut a stretch out of a stream recording by fetching only its HLS segments.

yt-dlp's --download-sections hands the whole playlist to ffmpeg, which on a
six-hour Twitch VOD sat for 20+ minutes at 48 bytes (18.11). Stream recordings
are HLS playlists of ~10-second segments, so the stretch is just the few
segments that overlap it: fetch those, join them, trim with ffmpeg.

`segments_for` is pure and unit-tested in test_hls.py.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from urllib.parse import urljoin

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
EDGE_SEC = 2.0  # fetch a little extra on both sides so the trim has room


@dataclass(frozen=True)
class Segment:
    uri: str
    start: float
    duration: float


@dataclass(frozen=True)
class Playlist:
    segments: list[Segment]
    init_uri: str | None
    variants: list[str]


def parse(text: str, base_url: str) -> Playlist:
    segments: list[Segment] = []
    variants: list[str] = []
    init_uri = None
    t = 0.0
    duration = None
    expect_variant = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-STREAM-INF"):
            expect_variant = True
        elif line.startswith("#EXTINF:"):
            duration = float(line[8:].split(",")[0])
        elif line.startswith("#EXT-X-MAP:"):
            for part in line[11:].split(","):
                if part.startswith("URI="):
                    init_uri = urljoin(base_url, part[4:].strip('"'))
        elif not line.startswith("#"):
            if expect_variant:
                variants.append(urljoin(base_url, line))
                expect_variant = False
            elif duration is not None:
                segments.append(Segment(urljoin(base_url, line), round(t, 3), duration))
                t += duration
                duration = None
    return Playlist(segments, init_uri, variants)


def segments_for(playlist: Playlist, start: float, end: float) -> list[Segment]:
    lo, hi = start - EDGE_SEC, end + EDGE_SEC
    return [s for s in playlist.segments if s.start < hi and s.start + s.duration > lo]


def _get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def load_playlist(url: str) -> Playlist:
    playlist = parse(_get(url).decode("utf-8", "replace"), url)
    if not playlist.segments and playlist.variants:
        first = playlist.variants[0]  # yt-dlp already picked the format; a master is rare
        playlist = parse(_get(first).decode("utf-8", "replace"), first)
    return playlist


def cut(playlist_url: str, start: float, end: float, dest: str) -> None:
    playlist = load_playlist(playlist_url)
    chosen = segments_for(playlist, start, end)
    if not chosen:
        raise RuntimeError("the stretch is outside the recording")
    joined = dest + ".joined"
    try:
        with open(joined, "wb") as out:
            if playlist.init_uri:
                out.write(_get(playlist.init_uri))
            for seg in chosen:
                out.write(_get(seg.uri))
        offset = max(0.0, start - chosen[0].start)
        subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-ss", f"{offset:.3f}", "-i", joined, "-t", f"{end - start:.3f}",
             "-map", "0:v:0?", "-map", "0:a:0?", "-c", "copy", "-movflags", "+faststart", dest],
            check=True, capture_output=True, timeout=600)
    finally:
        if os.path.exists(joined):
            os.remove(joined)


def cleanup(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)
