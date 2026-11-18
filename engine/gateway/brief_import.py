"""Turn a campaign brief (a Reach / Content Rewards link, or pasted text) into
the structured rules `campaigns.check_clip` runs on every clip.

Fetching is limited to known brief hosts (no open proxy). The rules themselves
are free text on every platform, so a model reads them into a fixed JSON shape
and `normalize` validates every field before anything is saved.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

BRIEF_HOSTS = {"reachclipping.com", "www.reachclipping.com", "contentrewards.com", "www.contentrewards.com"}
RULES_LINK = re.compile(r"https?://(?:www\.)?reachclipping\.com/[A-Za-z0-9_-]+")
PLATFORMS = {"tiktok": "tiktok", "instagram": "instagram", "instagram reels": "instagram", "reels": "instagram",
             "youtube": "youtube", "youtube shorts": "youtube", "shorts": "youtube", "x": "x", "twitter": "x",
             "facebook": "facebook", "snapchat": "snapchat"}
AI_STANCES = ("allowed", "forbidden", "unclear")
MAX_TEXT = 20_000
MODEL = os.environ.get("BRIEF_MODEL", "anthropic/claude-sonnet-5.5")


class BriefError(ValueError):
    """The brief could not be read or does not describe a campaign."""


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #
class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head"}
    BLOCK = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "tr", "section", "ul", "ol"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    lines = (re.sub(r"[ \t ]+", " ", line).strip() for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


def check_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in BRIEF_HOSTS:
        raise BriefError("Paste a reachclipping.com or contentrewards.com campaign link, or paste the rules as text.")
    return parsed.geturl()


def fetch_html(url: str) -> str:
    req = urllib.request.Request(check_url(url), headers={"User-Agent": "Mozilla/5.0 (brief reader)"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        if (urllib.parse.urlparse(resp.geturl()).hostname or "").lower() not in BRIEF_HOSTS:
            raise BriefError("The link redirected somewhere we don't read.")
        return resp.read(3_000_000).decode("utf-8", "replace")


def gather_brief(url: str, fetch=fetch_html) -> dict:
    """Text of the campaign page plus the rules page it links to (Content Rewards -> Reach)."""
    url = check_url(url)
    html = fetch(url)
    sources, texts = [url], [html_to_text(html)]
    for link in list(dict.fromkeys(RULES_LINK.findall(html)))[:2]:
        if link.rstrip("/") == url.rstrip("/"):
            continue
        try:
            texts.append(html_to_text(fetch(link)))
            sources.append(link)
        except Exception:  # the linked rules page is a bonus, the main page is enough
            continue
    return {"text": "\n\n---\n\n".join(texts)[:MAX_TEXT], "sources": sources}


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
PROMPT = """You read clipping campaign briefs (creators pay clippers per view for short clips) and
return the rules as JSON. Today is {today}. Use only what the text says; use null or [] when it is
not stated. Never invent a rule.

Return exactly one JSON object with these keys:
- "name": campaign title, short (e.g. "$12,500 LACY GTA VI Marathon Pool")
- "agency": who runs it (e.g. "Reach") or null
- "creator": the streamer/creator whose content is clipped, as written in the brief
- "source_channels": Twitch/Kick logins the footage must come from, lowercase. If the text names no login but
  the creator is a single streamer, give that streamer's login as written (e.g. "Lacy" -> "lacy"). For a group,
  team or brand (e.g. "CORE members"), return [] - a person will fill the logins in.
- "source_since": ISO date (YYYY-MM-DD) footage must be from or after, or null
- "ends": ISO date the campaign ends, or null
- "payout": one plain sentence on how it pays (pool size and split, or rate per 1K views, caps)
- "min_total_views": integer views needed to qualify (pool minimum / MVR), or null
- "max_payout_per_clip": integer USD cap per clip, or null
- "platforms": allowed platforms, from tiktok, instagram, youtube, x, facebook, snapchat
- "must_mention": name that must appear in the caption or on-screen text, or null
- "hashtags": hashtags required in the caption, with "#"
- "submit_within_min": integer minutes to submit after posting, or null
- "min_sec", "max_sec": integer clip length limits in seconds, or null
- "audience": account audience requirement in one sentence, or null
- "ai_content": "allowed", "forbidden" or "unclear"
- "manual": every other requirement a person must check by eye, one short imperative line each
  (who must be the main focus, logos, tone toward the creator, account niche, thumbnails, language,
  disclosure, no reposts/botting). Do not repeat rules already captured in the fields above.

Brief:
<<<
{text}
>>>"""


def call_llm(prompt: str) -> str:
    base = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    key = os.environ.get("LLM_API_KEY")
    if not key:
        raise BriefError("The rules reader is not configured on the server.")
    body = json.dumps({"model": MODEL, "temperature": 0, "max_tokens": 1500,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(f"{base}/chat/completions", data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        reply = json.load(resp)
    return reply["choices"][0]["message"]["content"]


def parse_json(reply: str) -> dict:
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end <= start:
        raise BriefError("The rules reader returned no JSON.")
    try:
        data = json.loads(reply[start:end + 1])
    except json.JSONDecodeError as exc:
        raise BriefError(f"The rules reader returned broken JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise BriefError("The rules reader returned the wrong shape.")
    return data


def extract(text: str, llm=call_llm, today: str | None = None) -> dict:
    """Raw rules from brief text; one retry if the model's JSON does not parse."""
    if len(text.strip()) < 40:
        raise BriefError("That is too short to be a campaign brief.")
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prompt = PROMPT.format(today=today, text=text[:MAX_TEXT])
    try:
        return parse_json(llm(prompt))
    except BriefError:
        return parse_json(llm(prompt + "\n\nReturn only the JSON object, nothing else."))


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def _str(value, limit: int = 200) -> str | None:
    if not isinstance(value, str):
        return None
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit] or None


def _int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.replace(",", "").strip()
        if not value.isdigit():
            return None
    if isinstance(value, (int, float, str)):
        number = int(float(value))
        return number if number > 0 else None
    return None


def _date(value) -> str | None:
    text = _str(value, 40)
    if not text:
        return None
    try:
        day = datetime.fromisoformat(text.replace("Z", "+00:00")[:10])
    except ValueError:
        return None
    return day.strftime("%Y-%m-%dT00:00:00Z")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "campaign"


def normalize(raw: dict, sources: list[str] | None = None) -> dict:
    """Validated campaign from model output or a form; raises BriefError if unusable."""
    if not isinstance(raw, dict):
        raise BriefError("Campaign must be an object.")
    sources = sources or []
    name = _str(raw.get("name"), 120)
    if not name:
        raise BriefError("The brief has no campaign name.")
    creator = _str(raw.get("creator"), 60)
    channels = [c.lower() for c in raw.get("source_channels") or [] if isinstance(c, str)]
    channels = [c for c in dict.fromkeys(channels) if re.fullmatch(r"[a-z0-9_]{2,25}", c)]
    platforms = []
    for p in raw.get("platforms") or []:
        key = PLATFORMS.get(str(p).lower().strip())
        if key and key not in platforms:
            platforms.append(key)
    hashtags = []
    for tag in raw.get("hashtags") or []:
        tag = str(tag).strip()
        tag = tag if tag.startswith("#") else f"#{tag}"
        if re.fullmatch(r"#\w{1,40}", tag) and tag.lower() not in (h.lower() for h in hashtags):
            hashtags.append(tag)
    manual = [m for m in (_str(x) for x in raw.get("manual") or []) if m][:15]
    ai = raw.get("ai_content") if raw.get("ai_content") in AI_STANCES else "unclear"
    if ai == "forbidden" and not any("ai" in m.lower().split() or "ai-" in m.lower() for m in manual):
        manual.append("No AI-generated content: real stream footage only")
    if not (platforms or hashtags or manual or channels):
        raise BriefError("No rules found in this brief.")
    agency = _str(raw.get("agency"), 60)
    cr = next((s for s in sources if "contentrewards.com" in s), None)
    rules = next((s for s in sources if "reachclipping.com" in s), None)
    return {
        "id": _str(raw.get("id"), 60) or slug(f"{agency or ''} {name}"),
        "name": name,
        "agency": agency,
        "marketplace": "Content Rewards" if cr or "content rewards" in str(raw.get("marketplace", "")).lower() else _str(raw.get("marketplace"), 60),
        "url": _str(raw.get("url"), 300) or cr or (sources[0] if sources else None),
        "rules_url": _str(raw.get("rules_url"), 300) or rules,
        "payout": _str(raw.get("payout"), 240),
        "min_total_views": _int(raw.get("min_total_views")),
        "max_payout_per_clip": _int(raw.get("max_payout_per_clip")),
        "creator": creator,
        "source_channels": channels,
        "source_since": _date(raw.get("source_since")),
        "ends": _date(raw.get("ends")),
        "platforms": platforms,
        "must_mention": _str(raw.get("must_mention"), 60),
        "hashtags": hashtags,
        "submit_within_min": _int(raw.get("submit_within_min")),
        "min_sec": _int(raw.get("min_sec")),
        "max_sec": _int(raw.get("max_sec")),
        "audience": _str(raw.get("audience"), 240),
        "ai_content": ai,
        "manual": manual,
    }


def import_brief(url: str | None = None, text: str | None = None, fetch=fetch_html, llm=call_llm) -> dict:
    """A draft campaign (not saved) from a link or pasted text."""
    if url:
        brief = gather_brief(url, fetch)
    elif text and text.strip():
        brief = {"text": text[:MAX_TEXT], "sources": []}
    else:
        raise BriefError("Paste a campaign link or the rules text.")
    return {"campaign": normalize(extract(brief["text"], llm), brief["sources"]), "sources": brief["sources"]}
