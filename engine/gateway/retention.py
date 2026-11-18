"""Keep the review queue short and the server's disk clean.

The autopilot used to cut new moments on a timer whether or not anyone had looked
at the last ones: 44 clips in 7 hours, ~10 GB a day on a 75 GB disk. Now:

- Demand, not a timer: a streamer has at most `queue_cap` clips waiting (review,
  approved, or still being cut). New moments are cut only into free slots, and
  the hottest moment at that minute takes the slot.
- Stale clips expire: a clip nobody reviewed for `review_ttl_hours` is rejected
  (a marathon moment has cooled by then) and frees its slot.
- Closed clips leave no files: an hour after a clip is posted or rejected, its
  stacked and headline renders and the core's job (the 1080p stream stretch and
  the cut clips) are deleted, unless a waiting clip still uses that job.

Pure helpers, unit-tested in test_retention.py; the autopilot calls them.
"""
from __future__ import annotations

import glob
import os
import shutil

import stacked

QUEUE_CAP = 3
REVIEW_TTL_HOURS = 12
GRACE_SEC = 3600            # a reject clicked by mistake can still be undone for an hour
MANUAL_KEEP_SEC = 48 * 3600  # a clip to post by hand stays downloadable this long
OPEN = ("review", "approved")
CLOSED = ("posted", "rejected")


def open_slots(state: dict, login: str, cap: int, clips_per_spot: int) -> int:
    """How many more clips this streamer may have cut right now."""
    waiting = sum(1 for i in state.get("items", []) if i.get("streamer") == login and i.get("status") in OPEN)
    cooking = sum(1 for p in state.get("pending", []) if p.get("streamer") == login) * max(1, clips_per_spot)
    return max(0, cap - waiting - cooking)


def spots_for(slots: int, clips_per_spot: int, max_spots: int) -> int:
    """Moments to cut for `slots` free places (each moment makes up to clips_per_spot clips)."""
    if slots <= 0:
        return 0
    per = max(1, clips_per_spot)
    return min(max(1, max_spots), -(-slots // per))


def expire_stale(state: dict, hours: float, now: float) -> list[str]:
    """Reject clips waiting for review longer than `hours`; returns their ids."""
    limit = now - hours * 3600
    expired = []
    for item in state.get("items", []):
        if item.get("status") == "review" and float(item.get("created") or now) < limit:
            item.update(status="rejected", expired=True, updated=now)
            expired.append(item["id"])
    return expired


def _paths(item: dict) -> list[str]:
    return [p for p in (item.get(k) for k in ("video_path", "engine_video_path", "original_video_path")) if p]


def job_of(item: dict) -> str | None:
    """The core job a clip was cut by (its stream stretch and output folder)."""
    for path in _paths(item):
        clip = stacked.parse_clip(path)
        if clip:
            return clip["job"]
    return None


def due_for_cleanup(state: dict, now: float, grace: float = GRACE_SEC) -> list[dict]:
    """Closed clips whose files can go. A clip marked for posting by hand keeps its
    file for MANUAL_KEEP_SEC, to be downloaded."""
    return [i for i in state.get("items", [])
            if i.get("status") in CLOSED and not i.get("files_removed")
            and now - float(i.get("updated") or now) >= (MANUAL_KEEP_SEC if i.get("posted_via") == "manual"
                                                         else grace)]


def jobs_in_use(state: dict) -> set[str]:
    return {job for i in state.get("items", []) if i.get("status") in OPEN for job in [job_of(i)] if job}


def _remove(path: str) -> int:
    try:
        if os.path.isdir(path):
            size = sum(os.path.getsize(os.path.join(root, f)) for root, _, files in os.walk(path) for f in files)
            shutil.rmtree(path)
            return size
        size = os.path.getsize(path)
        os.remove(path)
        return size
    except FileNotFoundError:
        return 0


def remove_files(item: dict, data_dir: str, in_use: set[str], output_dir: str = stacked.ENGINE_OUTPUT,
                 uploads_dir: str = stacked.ENGINE_UPLOADS) -> int:
    """Delete a closed clip's renders and, if no waiting clip shares it, its core job.
    Returns bytes freed and marks the item."""
    freed = 0
    item_id = str(item.get("id") or "")
    if len(item_id) == 32 and item_id.isalnum():
        for sub in ("stacked", "headlines"):
            for path in glob.glob(os.path.join(data_dir, sub, f"{item_id}-*.mp4")):
                freed += _remove(path)
    job = job_of(item)
    if job and job not in in_use:
        freed += _remove(os.path.join(output_dir, job))
        for path in glob.glob(os.path.join(uploads_dir, f"{job}_*")):
            freed += _remove(path)
    item["files_removed"] = True
    return freed
