"""Campaign briefs and the check every clip must pass before it is posted.

A campaign (e.g. Reach's LACY GTA VI Marathon pool on Content Rewards) pays only
for clips that follow its brief. Rules that can be checked from data are checked
here; the rest come back as manual checks the reviewer ticks off by eye.

Brief sources (read 2026-11-18): https://reachclipping.com/LACYGTA,
https://reachclipping.com/ClixGTA and their Content Rewards pages.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime, timezone

CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")

DEFAULT_CAMPAIGNS = [
    {
        "id": "reach-lacy-gta",
        "name": "$12,500 LACY GTA VI Marathon Pool",
        "agency": "Reach",
        "marketplace": "Content Rewards",
        "url": "https://contentrewards.com/c/campaigns/a5c63fad-cd53-4b81-9305-4a2d1696872a",
        "rules_url": "https://reachclipping.com/LACYGTA",
        "payout": "$12,500 pool split by approved views, paid when the marathon ends",
        "min_total_views": 750_000,
        "creator": "LACY",
        "source_channels": ["lacy"],
        "source_since": "2026-11-18T00:00:00Z",
        "ends": None,
        "platforms": ["tiktok", "instagram", "youtube", "x"],
        "must_mention": "LACY",
        "hashtags": ["#LACY"],
        "submit_within_min": 30,
        "audience": "At least 50% of the account's audience in USA, CA, AU, UK, NZ",
        "manual": [
            "LACY is the main focus of the whole clip, not only the intro",
            "No logos of any kind; thumbnail matches the content",
            "Does not show LACY in a negative light or push a false narrative",
            "Account is a LACY / GTA clip account, audience at least 50% USA, CA, AU, UK, NZ",
            "Real stream footage only: no AI voice, faces or generated scenes (Reach bans AI-generated content)",
        ],
    },
    {
        "id": "reach-clix-gta",
        "name": "$5,000 Clix GTA VI Marathon Pool",
        "agency": "Reach",
        "marketplace": "Content Rewards",
        "url": "https://contentrewards.com/c/campaigns/985dc674-c75e-44fc-ac87-1b1506324389",
        "rules_url": "https://reachclipping.com/ClixGTA",
        "payout": "$5,000 pool split by approved views, paid when the marathon ends",
        "min_total_views": 400_000,
        "creator": "Clix",
        "source_channels": ["clix"],
        "source_since": "2026-11-18T00:00:00Z",
        "ends": None,
        "platforms": ["tiktok", "instagram", "youtube", "x"],
        "must_mention": "Clix",
        "hashtags": ["#Clix"],
        "submit_within_min": 30,
        "audience": "At least 50% of the account's audience in USA, CA, AU, UK, NZ",
        "manual": [
            "Clix is the main focus of the clip",
            "No logos of any kind",
            "Does not show Clix in a negative light or push a false narrative",
            "Account is a Clix / GTA clip account, audience at least 50% USA, CA, AU, UK, NZ",
            "Real stream footage only: AI-generated videos are not allowed",
        ],
    },
]


def load_campaigns(data_dir: str) -> list[dict]:
    """Campaigns from /data/campaigns.json, or the built-in briefs."""
    path = os.path.join(data_dir, "campaigns.json")
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    return DEFAULT_CAMPAIGNS


CAMPAIGNS_LOCK = threading.Lock()


def _write(data_dir: str, campaigns: list[dict]) -> None:
    path = os.path.join(data_dir, "campaigns.json")
    tmp = f"{path}.tmp"
    with open(tmp, "w") as fh:
        json.dump(campaigns, fh, indent=1)
    os.replace(tmp, path)


def save_campaign(data_dir: str, campaign: dict) -> dict:
    """Add or replace (by id) one validated campaign."""
    with CAMPAIGNS_LOCK:
        def same(c: dict) -> bool:
            return c.get("id") == campaign["id"] or any(
                campaign.get(k) and c.get(k) == campaign.get(k) for k in ("url", "rules_url"))
        current = [c for c in load_campaigns(data_dir) if not same(c)]
        _write(data_dir, current + [campaign])
    return campaign


def remove_campaign(data_dir: str, campaign_id: str) -> bool:
    with CAMPAIGNS_LOCK:
        current = load_campaigns(data_dir)
        kept = [c for c in current if c.get("id") != campaign_id]
        if len(kept) == len(current):
            return False
        _write(data_dir, kept)
    return True


def _ts(iso: str | None) -> float | None:
    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()


def check_clip(campaign: dict, clip: dict, now: float | None = None) -> list[dict]:
    """Rule-by-rule check of one clip against one campaign brief.

    clip: streamer (login), vod_started (ISO), duration (s), caption, overlay
    (on-screen text), platforms (where it will be posted).
    Each result: {rule, ok: True | False | None (check by eye), detail}.
    """
    now = time.time() if now is None else now
    out: list[dict] = []

    def add(rule: str, ok: bool | None, detail: str = "") -> None:
        out.append({"rule": rule, "ok": ok, "detail": detail})

    ends = _ts(campaign.get("ends"))
    add("Campaign is accepting clips", ends is None or now < ends,
        "" if ends is None or now < ends else f"ended {campaign['ends']}")

    channels = [c.lower() for c in campaign.get("source_channels") or []]
    if channels:
        streamer = (clip.get("streamer") or "").lower()
        add(f"Footage from {', '.join(channels)}", streamer in channels, f"source: {streamer or 'unknown'}")

    since = campaign.get("source_since")
    if since:
        started = clip.get("vod_started")
        if not started:
            add(f"Footage from {since[:10]} or later", None, "stream date unknown, check the source")
        else:
            add(f"Footage from {since[:10]} or later", _ts(started) >= _ts(since), f"stream started {started}")

    allowed = set(campaign.get("platforms") or [])
    targets = set(clip.get("platforms") or [])
    if allowed and targets:
        extra = sorted(targets - allowed)
        add("Posted only where the campaign pays", not extra, f"not allowed: {', '.join(extra)}" if extra else "")

    caption = clip.get("caption") or ""
    name = campaign.get("must_mention")
    if name:
        where = f"{caption}\n{clip.get('overlay') or ''}".lower()
        add(f"Caption or on-screen text names {name}", name.lower() in where)

    for tag in campaign.get("hashtags") or []:
        add(f"Caption has {tag}", tag.lower() in caption.lower())

    add("English caption, no Japanese / CJK text", not CJK.search(caption))

    duration = clip.get("duration")
    lo, hi = campaign.get("min_sec"), campaign.get("max_sec")
    if duration is not None and (lo or hi):
        ok = (lo is None or duration >= lo) and (hi is None or duration <= hi)
        add("Length within the brief", ok, f"{duration:.0f}s")

    for rule in campaign.get("manual") or []:
        add(rule, None)
    return out


def verdict(checks: list[dict]) -> str:
    """'fail' if any rule is broken, 'manual' if some need eyes, else 'pass'."""
    if any(c["ok"] is False for c in checks):
        return "fail"
    if any(c["ok"] is None for c in checks):
        return "manual"
    return "pass"


def failed(checks: list[dict]) -> list[str]:
    return [c["rule"] for c in checks if c["ok"] is False]
