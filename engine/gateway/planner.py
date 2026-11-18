"""Which stretches of a long stream to send to the clipping engine.

Pure functions, standard library only, unit-tested in test_planner.py.

The engine transcribes and scores everything it is given, so a five-hour stream
costs five hours of work. We hand it only the stretches most likely to hold a
clip: where viewers clipped, then where the audio peaks (screams, crashes,
laughter), and stop at a total budget.
"""
from __future__ import annotations

from dataclasses import dataclass

SHORT_SOURCE_SEC = 20 * 60      # up to this, the whole video goes in as is
STRETCH_SEC = 180               # length of one stretch sent to the engine
LEAD_SEC = 60                   # how much comes before the hot point
MAX_STRETCHES = 6
ENOUGH_VIEWER_SPOTS = 3        # below this, also listen for loud reactions
MIN_GAP_SEC = 240               # loudness peaks closer than this are one moment
LOUD_WINDOW_SEC = 20            # loudness is averaged over this many seconds
SKIP_INTRO_SEC = 300            # a stream's first minutes are intro music, not reactions


@dataclass(frozen=True)
class Stretch:
    start: float
    end: float
    reason: str

    @property
    def length(self) -> float:
        return self.end - self.start


def _clamp(start: float, duration: float) -> tuple[float, float]:
    start = max(0.0, min(start, max(0.0, duration - STRETCH_SEC)))
    return round(start, 3), round(min(duration, start + STRETCH_SEC), 3)


def viewer_hotspots(clips: list[dict]) -> list[tuple[float, float]]:
    """(time, weight) per cluster of viewer clips; weight favours many clippers.

    clips: [{"start": seconds into the VOD, "duration": s, "views": n}, ...]
    """
    items = sorted(
        (float(c["start"]), float(c.get("duration") or 30), int(c.get("views") or 0))
        for c in clips
        if c.get("start") is not None and float(c["start"]) >= 0
    )
    clusters: list[list[tuple[float, float, int]]] = []
    for item in items:
        if clusters and item[0] <= clusters[-1][-1][0] + clusters[-1][-1][1] + 30:
            clusters[-1].append(item)
        else:
            clusters.append([item])
    return [
        (cluster[0][0], sum(views for _, _, views in cluster) + 100 * len(cluster))
        for cluster in clusters
    ]


def loudness_hotspots(levels_db: list[float], top: int) -> list[tuple[float, float]]:
    """(time, weight) for the loudest moments, one per MIN_GAP_SEC.

    levels_db: one RMS level per second, in dB (silence is very negative).
    """
    n = len(levels_db)
    if n < LOUD_WINDOW_SEC:
        return []
    floor = -90.0
    vals = [max(floor, v) for v in levels_db]
    window = LOUD_WINDOW_SEC
    running = sum(vals[:window])
    means = [running / window]
    for i in range(window, n):
        running += vals[i] - vals[i - window]
        means.append(running / window)
    start = SKIP_INTRO_SEC if n > SKIP_INTRO_SEC + window else 0
    order = sorted(range(start, len(means)), key=lambda i: means[i], reverse=True)
    picked: list[int] = []
    for i in order:
        if all(abs(i - j) >= MIN_GAP_SEC for j in picked):
            picked.append(i)
        if len(picked) >= top:
            break
    return [(float(i), means[i]) for i in picked]


def _overlaps(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


MAX_STRETCHES_HARD = 10


def stretches_for(clips_wanted: int) -> int:
    """How many 3-minute stretches to cut for the clips asked for.

    One stretch yields one to three clips; two per stretch is the planning bet.
    """
    return max(1, min(MAX_STRETCHES_HARD, -(-int(clips_wanted) // 2)))


def plan(duration: float, viewer_clips: list[dict] | None = None,
         levels_db: list[float] | None = None, max_stretches: int = MAX_STRETCHES) -> list[Stretch]:
    """Stretches to clip, in time order. Empty only for an empty source."""
    duration = max(0.0, float(duration or 0))
    if duration <= 0:
        return []
    if duration <= SHORT_SOURCE_SEC:
        return [Stretch(0.0, round(duration, 3), "whole video")]

    chosen: list[Stretch] = []

    def add(point: float, reason: str) -> None:
        start, end = _clamp(point - LEAD_SEC, duration)
        if any(_overlaps((start, end), (s.start, s.end)) for s in chosen):
            return
        chosen.append(Stretch(start, end, reason))

    for point, _ in sorted(viewer_hotspots(viewer_clips or []), key=lambda p: -p[1]):
        if len(chosen) >= max_stretches:
            break
        add(point, "viewers clipped here")

    if len(chosen) < max_stretches and levels_db:
        for point, _ in loudness_hotspots(levels_db, max_stretches * 2):
            if len(chosen) >= max_stretches:
                break
            # A loud second is the peak of a reaction: lead in a little less.
            add(point + LOUD_WINDOW_SEC / 2, "loud reaction")

    if not chosen:
        # Nothing to go on: the opening of a stream is usually setup, so take
        # stretches spread across it instead.
        step = duration / (max_stretches + 1)
        for k in range(1, max_stretches + 1):
            add(step * k, "spread across the stream")

    return sorted(chosen, key=lambda s: s.start)
