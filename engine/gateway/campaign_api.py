"""HTTP handlers for campaigns: list, import a brief, save, remove."""
from __future__ import annotations

import re

import brief_import
import campaigns


def handle_post(path: str, body: dict, data_dir: str) -> tuple[int, dict]:
    """(status, payload) for POST /campaigns, /campaigns/import, /campaigns/<id>/remove."""
    if path == "/campaigns/import":
        try:
            draft = brief_import.import_brief(url=str(body.get("url") or "").strip() or None,
                                              text=str(body.get("text") or "") or None)
        except brief_import.BriefError as exc:
            return 400, {"error": str(exc)}
        except Exception as exc:  # network or model failure
            return 502, {"error": f"Could not read the brief: {str(exc)[:160]}"}
        return 200, draft
    if path == "/campaigns":
        try:
            campaign = brief_import.normalize(body.get("campaign"))
        except brief_import.BriefError as exc:
            return 400, {"error": str(exc)}
        return 201, {"campaign": campaigns.save_campaign(data_dir, campaign)}
    match = re.fullmatch(r"/campaigns/([a-z0-9-]{1,60})/remove", path)
    if match:
        removed = campaigns.remove_campaign(data_dir, match.group(1))
        return (200, {"status": "removed"}) if removed else (404, {"error": "not found"})
    return 404, {"error": "not found"}
