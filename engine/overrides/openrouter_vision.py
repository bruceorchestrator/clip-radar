"""The core's shot check (screencast_layout.detect_content_ranges) through OpenRouter.

Upstream asks Gemini directly (google-genai, GEMINI_API_KEY) whether each shot
is a screen, camera footage or both, and whether a live webcam sits over the
screen. That answer decides where the webcam-inset layout is used: without it
the core guesses from faces, and gameplay full of game characters gets the
blurred layout with a thumbnail-sized streamer. We have no Gemini key, only
OpenRouter, so this sends the same shots and the same prompt to a vision model
there and returns exactly what upstream returns.

Installed by sitecustomize.py (patches the module after it is imported).
Model: SHOT_CHECK_MODEL, else LLM_MODEL (an OpenRouter id, e.g.
google/gemini-3.5-flash-lite).
"""
from __future__ import annotations

import base64
import json
import os
import urllib.request

TIMEOUT_SEC = 90

# Upstream's prompt is written for tutorials. Stream VODs are games with the
# streamer's webcam in a corner, so say how those shots should be answered.
GAME_NOTE = """
This video may be a live stream of a VIDEO GAME. Gameplay, game cutscenes, game
menus and loading screens count as "screen" (the game is the screen), even when
game characters are on it. The streamer's own webcam box in a corner over the
game is presenter_cam true. A shot where the streamer's webcam fills the picture
(just chatting, no game) is "camera".
"""


# Scenes (in frames) where the last shot check saw the streamer's webcam over the
# screen. camera_inset.present_in_scene looks for a person inside the webcam box
# with a local detector, which misses a small dark webcam beside bright gameplay;
# present_in_scene below also accepts the vision model's word for it.
_CAM_SCENES: list[tuple[float, float]] = []


def present_in_scene(original):
    def check(video_path, box, start_f, end_f, *args, **kwargs):
        if any(s <= start_f < e or s < end_f <= e for s, e in _CAM_SCENES):
            return True
        return original(video_path, box, start_f, end_f, *args, **kwargs)
    return check


def _model() -> str | None:
    return os.environ.get("SHOT_CHECK_MODEL") or os.environ.get("LLM_MODEL")


def ask(prompt: str, jpegs: list[bytes]) -> dict:
    """One OpenRouter chat call with numbered images; the parsed JSON reply."""
    content: list[dict] = []
    for n, jpg in enumerate(jpegs):
        content.append({"type": "text", "text": f"Shot {n}:"})
        content.append({"type": "image_url",
                        "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpg).decode()}})
    content.append({"type": "text", "text": prompt + "\n\nReturn only JSON: "
                    '{"shots": [{"shot": 0, "kind": "screen", "focus_left": 0, "focus_right": 1, '
                    '"presenter_cam": false}]}'})
    body = json.dumps({"model": _model(), "temperature": 0, "max_tokens": 2000,
                       "response_format": {"type": "json_object"},
                       "messages": [{"role": "user", "content": content}]}).encode()
    base = (os.environ.get("LLM_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
    req = urllib.request.Request(f"{base}/chat/completions", data=body, method="POST", headers={
        "Authorization": f"Bearer {os.environ['LLM_API_KEY']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        reply = json.load(resp)
    text = reply["choices"][0]["message"]["content"] or ""
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1]) if 0 <= start < end else {}


def detect_content_ranges(video_path, scenes, fps):
    """Drop-in for screencast_layout.detect_content_ranges (same contract)."""
    import gemini_worker
    import screencast_layout as sl

    if not sl.ENABLED:
        return []
    if not scenes:
        return None
    if not (os.environ.get("LLM_API_KEY") and _model()):
        print("   ⚠️ Screen check needs LLM_API_KEY and LLM_MODEL (OpenRouter).")
        return None
    asked = sl.shots_to_ask(scenes)
    print(f"   🔎 Screen check on {len(asked)} shot(s) via OpenRouter ({_model()})…")
    try:
        frames = sl._shot_frames(video_path, scenes, asked)
        keep = [(i, jpg) for i, jpg in zip(asked, frames) if jpg]
        if not keep:
            print("   ⚠️ No readable frames for the screen check.")
            return None
        raw = (ask(gemini_worker.SHOT_CONTENT_PROMPT + GAME_NOTE, [jpg for _, jpg in keep]) or {}).get("shots") or []
    except Exception as e:
        print(f"   ⚠️ Screen check failed ({e}).")
        return None
    by_position = sl._parse_shots(raw, len(keep))
    if not by_position:
        print("   ⚠️ Screen check returned nothing usable.")
        return None
    verdicts = {keep[n][0]: v for n, v in by_position.items()}
    ranges = sl.ranges_from_verdicts(scenes, fps, verdicts)
    _CAM_SCENES[:] = [(r[0] * fps, r[1] * fps) for r in ranges if r[5]]
    print("   📊 Shots: " + ", ".join(
        f"{i}={k}" + ("+cam" if c else "") for i, (k, f, c) in sorted(verdicts.items())))
    return ranges
