"""Where a finished clip goes: one function per posting service, picked per account.

An account in autopilot.json (per streamer, or the top-level "accounts" fallback):
  {"name": "My Clips", "via": "upload-post", "user": "<profile>", "platforms": ["youtube", "x"]}
  {"name": "My Clips", "via": "postiz", "platforms": ["youtube", "x"],
   "integrations": {"youtube": "<postiz integration id>", "x": "<id>"}}
  {"name": "By hand", "via": "manual", "platforms": ["tiktok"]}

- upload-post (default): upload-post.com, hosted, its own approved YouTube/TikTok
  apps. Env UPLOAD_POST_API_KEY. Free plan: 10 uploads a month.
- postiz: postiz.com cloud or a self-hosted Postiz (open source). Env POSTIZ_API_KEY,
  POSTIZ_URL (default https://api.postiz.com/public/v1; self-hosted:
  https://<host>/api/public/v1). Integration ids: GET <POSTIZ_URL>/integrations.
  A self-hosted Postiz needs its own platform apps; YouTube keeps uploads from an
  unverified Google API project private.
- manual: nothing is sent; the clip is marked posted and the link to download the
  finished file goes to Telegram, to post by hand anywhere.

To add a service: write post_<name>(item, account, video, text, cover) returning
{platform: url or "error: ..."}, add it to SERVICES and ENV, and a test.
`text` is {"title", "caption"} from the campaign check.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

POSTIZ_URL = "https://api.postiz.com/public/v1"
ENV = {"upload-post": "UPLOAD_POST_API_KEY", "postiz": "POSTIZ_API_KEY", "manual": None}


def service(account: dict) -> str:
    return account.get("via") or "upload-post"


def ready(account: dict) -> bool:
    """The service's key is set (manual needs none)."""
    via = service(account)
    if via not in ENV:
        return False
    return ENV[via] is None or bool(os.environ.get(ENV[via]))


def _multipart(fields: list[tuple[str, str]], files: list[tuple[str, str, str, bytes]]) -> tuple[bytes, str]:
    """files: (field, filename, content type, bytes)."""
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for field, filename, content_type, data in files:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n".encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _request(url: str, body: bytes, headers: dict, name: str) -> dict:
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            raw = resp.read()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"{name} {exc.code}: {detail}") from exc


# --------------------------------------------------------------------------- #
# Upload-Post
# --------------------------------------------------------------------------- #
def _upload_post(path: str, body: bytes, content_type: str, idempotency: str | None = None) -> dict:
    headers = {"Authorization": f"Apikey {os.environ['UPLOAD_POST_API_KEY']}", "Content-Type": content_type}
    if idempotency:
        headers["Idempotency-Key"] = idempotency
    return _request(f"https://api.upload-post.com{path}", body, headers, "Upload-Post")


def set_youtube_thumbnail(user: str, video_id: str, cover: bytes) -> dict:
    """Cover for a Short that is already on YouTube (Upload-Post queues it while YouTube processes)."""
    body, content_type = _multipart([("user", user), ("video_id", video_id)],
                                    [("thumbnail", "cover.jpg", "image/jpeg", cover)])
    return _upload_post("/api/uploadposts/youtube/thumbnail", body, content_type)


def post_upload_post(item: dict, account: dict, video: bytes, text: dict, cover: bytes | None = None) -> dict:
    """One request for all the account's platforms; YouTube also gets the cover."""
    platforms = account.get("platforms") or []
    fields = [("user", account["user"]), ("title", text["title"]),
              ("tiktok_title", text["caption"]), ("instagram_title", text["caption"]),
              ("youtube_title", text["title"]), ("description", text["caption"])]
    fields += [("platform[]", p) for p in platforms]
    files = [("video", "clip.mp4", "video/mp4", video)]
    if cover and "youtube" in platforms:
        files.append(("thumbnail", "cover.jpg", "image/jpeg", cover))
    body, content_type = _multipart(fields, files)
    reply = _upload_post("/api/upload", body, content_type, idempotency=item["id"])
    out = {}
    for platform, result in (reply.get("results") or {}).items():
        out[platform] = result.get("url") if result.get("success") else f"error: {result.get('error')}"
        problem = result.get("thumbnail_error") or (result.get("thumbnail_note") if not (
            result.get("thumbnail_set") or result.get("thumbnail_pending")) else None)
        if cover and platform == "youtube" and problem:
            out["youtube cover"] = f"error: {problem}"
    if not out and reply.get("request_id"):
        out["pending"] = f"processing in background, request {reply['request_id']}"
    return out


# --------------------------------------------------------------------------- #
# Postiz
# --------------------------------------------------------------------------- #
def postiz_settings(platform: str, text: dict, cover_media: dict | None = None) -> dict:
    """Postiz provider settings (docs.postiz.com/public-api/providers)."""
    if platform == "youtube":
        return {"__type": "youtube", "title": text["title"][:100], "type": "public",
                "selfDeclaredMadeForKids": "no", "thumbnail": cover_media, "tags": []}
    if platform == "tiktok":
        return {"__type": "tiktok", "title": text["caption"][:90], "privacy_level": "PUBLIC_TO_EVERYONE",
                "duet": False, "stitch": False, "comment": True, "autoAddMusic": "no",
                "brand_content_toggle": False, "brand_organic_toggle": False,
                "content_posting_method": "DIRECT_POST"}
    if platform in ("instagram", "instagram-standalone"):
        return {"__type": platform, "post_type": "post"}
    if platform == "x":
        return {"__type": "x", "who_can_reply_post": "everyone"}
    return {"__type": platform}


def _postiz(path: str, body: bytes, content_type: str) -> dict:
    base = (os.environ.get("POSTIZ_URL") or POSTIZ_URL).rstrip("/")
    return _request(f"{base}{path}", body, {"Authorization": os.environ["POSTIZ_API_KEY"],
                                            "Content-Type": content_type}, "Postiz")


def post_postiz(item: dict, account: dict, video: bytes, text: dict, cover: bytes | None = None) -> dict:
    """Upload the file once, then one post per platform, published now."""
    integrations = account.get("integrations") or {}
    platforms = [p for p in account.get("platforms") or [] if integrations.get(p)]
    out = {p: "error: no Postiz integration id for it" for p in account.get("platforms") or [] if p not in platforms}
    if not platforms:
        return out
    body, content_type = _multipart([], [("file", "clip.mp4", "video/mp4", video)])
    media = _postiz("/upload", body, content_type)
    media = {"id": media["id"], "path": media["path"]}
    cover_media = None
    if cover and "youtube" in platforms:
        body, content_type = _multipart([], [("file", "cover.jpg", "image/jpeg", cover)])
        uploaded = _postiz("/upload", body, content_type)
        cover_media = {"id": uploaded["id"], "path": uploaded["path"]}
    posts = [{"integration": {"id": integrations[p]},
              "value": [{"content": text["caption"], "image": [media]}],
              "settings": postiz_settings(p, text, cover_media)} for p in platforms]
    payload = {"type": "now", "date": datetime.now(timezone.utc).isoformat(), "shortLink": False,
               "tags": [], "posts": posts}
    reply = _postiz("/posts", json.dumps(payload).encode(), "application/json")
    # Postiz publishes in the background and answers with post ids, not links yet.
    ids = [r.get("postId") or r.get("id") for r in reply] if isinstance(reply, list) else []
    for n, p in enumerate(platforms):
        out[p] = f"sent to Postiz (post {ids[n]})" if n < len(ids) and ids[n] else "sent to Postiz"
    return out


# --------------------------------------------------------------------------- #
# By hand
# --------------------------------------------------------------------------- #
def post_manual(item: dict, account: dict, video: bytes, text: dict, cover: bytes | None = None) -> dict:
    return {"download": item["video_path"], "caption": text["caption"]}


SERVICES = {"upload-post": post_upload_post, "postiz": post_postiz, "manual": post_manual}


def post(item: dict, account: dict, video: bytes, text: dict, cover: bytes | None = None) -> dict:
    """Post a clip through the account's service; {platform: url or "error: ..."}."""
    via = service(account)
    if via not in SERVICES:
        raise RuntimeError(f"unknown posting service {via!r}")
    if not ready(account):
        raise RuntimeError(f"{via} is not set up: {ENV[via]} is missing on the server")
    return SERVICES[via](item, account, video, text, cover)


def wants_cover(account: dict) -> bool:
    return service(account) != "manual" and "youtube" in (account.get("platforms") or [])
