"""Which campaigns a queued clip goes to, the caption that satisfies all of them,
and the rule check per campaign.

One clip can earn in several pools when it meets each brief (Reach allows the
same LACY clip in the LACY and CORE pools). The streamer's own campaign is always
a target; any other matching campaign is opt-in per clip, because e.g. CORE also
needs two members in frame, which only a person can confirm.
"""
from __future__ import annotations

import campaigns as campaign_rules

SUMMARY_KEYS = ("id", "name", "url", "rules_url", "submit_within_min", "payout")


def build_post_text(item: dict, streamer: dict, targets: list[dict] | None = None) -> dict:
    """Caption and title. Forces in the streamer's name and #NAME, plus every target
    campaign's required hashtags and name."""
    name = streamer.get("name") or streamer["login"]
    tags = list(streamer.get("hashtags") or [f"#{name}"])
    for campaign in targets or []:
        tags += campaign.get("hashtags") or []
    lowered = [t.lower() for t in tags]
    tags = [t for i, t in enumerate(tags) if t.lower() not in lowered[:i]]
    if f"#{name}".lower() not in (t.lower() for t in tags):
        tags.insert(0, f"#{name}")
    hook = (item.get("hook") or item.get("title") or "").strip()
    if name.lower() not in hook.lower():
        hook = f"{name}: {hook}" if hook else name
    tag_line = " ".join(tags)
    missing = [c["must_mention"] for c in targets or [] if c.get("must_mention")
               and c["must_mention"].lower() not in f"{hook} {tag_line}".lower()]
    if missing:
        hook = f"{hook} ({', '.join(dict.fromkeys(missing))})"
    caption = f"{hook}\n\n{tag_line}"[:2200]
    title = (item.get("title") or hook).strip()
    if name.lower() not in title.lower():
        title = f"{title} | {name}"
    return {"caption": caption, "title": title[:100]}


def matching(streamer: dict | None, campaigns: list[dict]) -> list[dict]:
    """Campaigns this streamer's clips can go to: the one named in config first (when it
    still exists), then every campaign whose footage includes this channel."""
    if not streamer:
        return []
    login = streamer.get("login", "").lower()
    named = [c for c in campaigns if streamer.get("campaign") and c.get("id") == streamer["campaign"]]
    by_channel = [c for c in campaigns if login in [x.lower() for x in c.get("source_channels") or []]]
    out, seen = [], set()
    for campaign in named + by_channel:
        if campaign.get("id") not in seen:
            seen.add(campaign.get("id"))
            out.append(campaign)
    return out


def campaign_for(streamer: dict | None, campaigns: list[dict]) -> dict | None:
    """The streamer's own (primary) campaign."""
    found = matching(streamer, campaigns)
    return found[0] if found else None


def targets(item: dict, matches: list[dict]) -> list[dict]:
    """Primary campaign plus the extra ones the reviewer opted this clip into."""
    extra = set(item.get("extra_campaigns") or [])
    return [c for i, c in enumerate(matches) if i == 0 or c.get("id") in extra]


def _overall(results: list[dict]) -> str:
    chosen = [r["verdict"] for r in results if r["selected"]]
    if not chosen:
        return "none"
    for verdict in ("fail", "manual"):
        if verdict in chosen:
            return verdict
    return "pass"


def item_checks(item: dict, streamer: dict | None, campaigns: list[dict]) -> dict:
    """Per-campaign checks of a queue item as it would be posted now.

    Selected campaigns are checked with the real caption; a not-yet-selected one with
    the caption it would get if the reviewer added it.
    """
    matches = matching(streamer, campaigns)
    if not matches:
        return {"campaigns": [], "verdict": "none", "text": None}
    chosen = targets(item, matches)
    chosen_ids = {c.get("id") for c in chosen}
    results = []
    for index, campaign in enumerate(matches):
        selected = campaign.get("id") in chosen_ids
        text = build_post_text(item, streamer, chosen if selected else chosen + [campaign])
        checks = campaign_rules.check_clip(campaign, {
            "streamer": item.get("streamer"), "vod_started": item.get("vod_started"),
            "duration": item.get("duration"), "caption": text["caption"], "overlay": item.get("overlay"),
            "platforms": streamer.get("platforms") or []})
        results.append({"campaign": {k: campaign.get(k) for k in SUMMARY_KEYS}, "checks": checks,
                        "verdict": campaign_rules.verdict(checks), "selected": selected, "primary": index == 0})
    return {"campaigns": results, "verdict": _overall(results), "text": build_post_text(item, streamer, chosen)}


def broken_rules(check: dict) -> list[str]:
    """Rules broken in any campaign the clip is going to."""
    return [f"{r['campaign']['name']}: {rule}" for r in check["campaigns"] if r["selected"]
            for rule in campaign_rules.failed(r["checks"])]


def toggle(item: dict, campaign_id: str, matches: list[dict]) -> str | None:
    """Add or remove an extra campaign for this clip; returns an error or None."""
    ids = [c.get("id") for c in matches]
    if campaign_id not in ids:
        return "this campaign does not take this streamer's clips"
    if campaign_id == ids[0]:
        return "the streamer's own campaign is always included"
    if item.get("status") not in ("review", "approved"):
        return f"cannot change campaigns of a clip that is {item.get('status')}"
    extra = [c for c in item.get("extra_campaigns") or [] if c in ids]
    item["extra_campaigns"] = [c for c in extra if c != campaign_id] if campaign_id in extra else extra + [campaign_id]
    return None
