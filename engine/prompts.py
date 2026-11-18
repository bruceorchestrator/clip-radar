"""Clip Radar's moment-selection prompts for the OpenShorts core.

The core is used unmodified except for these two templates. `apply_prompts.py`
swaps them into a copy of upstream `gemini_worker.py`; the copy is mounted over
the original in the container. Placeholders and the JSON shape must match the
upstream templates exactly (the core validates replies with pydantic models
`ScoreResponse` and `DetailResponse`).

Audience: clippers posting GTA VI streamer moments to TikTok, Shorts, Reels and X.
"""

SCORE_PROMPT_TEMPLATE = """
You rank moments from a live stream for short-form clips (TikTok, YouTube Shorts,
Instagram Reels, X). The streams are mostly Grand Theft Auto gameplay with the
streamer talking to chat.

You see only the transcript of each window, so read it as a stream: a short line
like "no no no NO", "bro what", "chat look", screaming, swearing, sudden silence
after a crash, or a burst of laughter often marks the best gameplay moment even
when the words themselves say little.

Score EVERY window you are given, exactly one entry per input id. Integer score
0-100. Use the whole range: most of a stream is filler.

High scores (70+):
- Something happens: a chase that ends badly or brilliantly, a crash, a death,
  a heist going wrong, a police escape, an absurd glitch-like moment, a fight.
- A big reaction to it: shock, rage, panic, hysterical laughter.
- A clash with another person: chat, a friend, an NPC, a stranger online.
- A strong hot take about the game that a cold viewer can follow.
- Viewers clipped it: a window may carry `viewers_clipped` and
  `viewer_clip_views`. Treat that as strong evidence the moment lands, even when
  the transcript looks thin.

Low scores (under 30):
- Menus, loading, settings, queueing, "starting soon", waiting.
- Reading donations or subscriptions, thanking chat, sponsor reads, schedule talk.
- Quiet driving, walking, shopping with nothing happening.
- Anything a viewer would only get with the previous ten minutes of context.

Judge each window by the 2-second test: would the first two seconds stop a viewer
who has never seen this streamer?

Do not invent events that the transcript does not support.

TRANSCRIPT_LANGUAGE: {language}
VIDEO_DURATION_SECONDS: {video_duration}
WINDOWS_JSON:
{windows_json}

Return only valid JSON:
{{
  "windows": [
    {{
      "id": "<window id>",
      "start": <number>,
      "end": <number>,
      "score": <integer 0-100>,
      "reason": "<very short reason>"
    }}
  ]
}}
"""

DETAIL_PROMPT_TEMPLATE = """
You cut short clips from a live stream for clippers who post them to TikTok,
YouTube Shorts, Instagram Reels and X. The streams are mostly Grand Theft Auto
gameplay with the streamer talking to chat. You work from the transcript with
word timestamps, inside the shortlisted windows below.

CLIP RULES
- Each clip is {min_secs:g} to {max_secs:g} seconds, in absolute seconds from the
  start of the source video, and stays inside its candidate window.
- Open on the moment, not the build-up. The first two seconds must already show
  or say something: the crash, the scream, the "bro what", the start of the
  chase. If the setup is needed, keep it to two or three seconds before the hit.
- End right after the payoff: the reaction, the punchline, the result. Never cut
  the reaction short; it is often the best part.
- Do not start or end in the middle of a word.
- The clip must make sense to someone who has never seen this streamer. If it
  opens on "that", "so", or an answer to an earlier question, move the start back
  to where the moment begins, or skip it.
- When a window has `viewer_moments` ([start, end] stretches viewers clipped),
  the best clip of that window covers the strongest of them, opening a few
  seconds before it.
- Skip: menus, loading screens, donation and sub reading, sponsor reads,
  schedule announcements, quiet driving.
- Return {min_clips} to {max_clips} clips. Work through every window; they were
  already scored as the best of the stream. Two clips from one window are fine
  when they are different moments. Never pad with a clip you would not post.
- No two clips may show the same moment or land the same joke.

HOOK (`viral_hook_text`, max 8 words, at most one emoji)
- Name what happens in THIS clip, in plain words a viewer reads in one second.
- Good: "He tried to outrun 6 stars on a bike", "The cops did NOT expect this",
  "This GTA 6 glitch broke him", "He lost the whole heist in 3 seconds".
- Bad: anything that fits any clip ("Insane moment", "Wait for it",
  "You won't believe this"), and anything the transcript does not support.
- Do not spoil the ending of the clip in the hook.

COPY (all text in TRANSCRIPT_LANGUAGE: {language})
- `video_title_for_youtube_short`: max 80 characters, says what happens, no fake
  claims, include the streamer's name only if it is said in the transcript.
- `video_description_for_tiktok` and `video_description_for_instagram`: one
  sentence that teases the payoff, then 3-5 relevant hashtags (always #gta6 when
  the game is GTA VI). No calls to follow or comment.
- `predicted_score`: honest 0-100 estimate of how well it does with cold viewers.
- `why`: one sentence, max 20 words, naming the specific moment.

TRANSCRIPT_LANGUAGE: {language}
VIDEO_DURATION_SECONDS: {video_duration}
CANDIDATE_WINDOWS_JSON:
{windows_json}

Return only valid JSON:
{{
  "shorts": [
    {{
      "start": <number>,
      "end": <number>,
      "source_window_id": "<window id>",
      "predicted_score": <integer 0-100>,
      "video_description_for_tiktok": "<description + hashtags>",
      "video_description_for_instagram": "<description + hashtags>",
      "video_title_for_youtube_short": "<title max 80 chars>",
      "viral_hook_text": "<hook max 8 words>",
      "why": "<one sentence, max 20 words>"
    }}
  ]
}}
"""
