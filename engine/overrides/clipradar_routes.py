"""Extra HTTP routes on the core's FastAPI app, for the Clip Radar gateway.

Installed by sitecustomize.py right after the core's `app` module is imported, so
the core stays unmodified.

GET /api/clipradar/webcam/{job_id}
    The streamer's webcam box in the job's source video, found by the core's own
    detector (camera_inset.detect: face/person anchored to a corner, stable across
    samples). Answers {"box": [x, y, w, h] | null, "width": W, "height": H}.
    The gateway uses it for streamers whose webcam box is not configured.
"""
from __future__ import annotations

import json
import os
import re

OUTPUT = "/app/output"
UPLOADS = "/app/uploads"
JOB = re.compile(r"[0-9a-f-]{36}")


def _source(job_id: str) -> str | None:
    meta_path = os.path.join(OUTPUT, job_id, f"{job_id}_stretch_metadata.json")
    name = None
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as fh:
            name = json.load(fh).get("source_video")
    path = os.path.join(UPLOADS, name or f"{job_id}_stretch.mp4")
    return path if os.path.exists(path) else None


def find_webcam(path: str, samples: int = 12):
    """(box, width, height): the webcam inset, from faces near a corner only.

    camera_inset.detect takes the most confident face in each frame. On GTA and
    other games that is often a game character's close-up in the middle of the
    screen (measured 18.11 on a Lacy stream: 9 of 10 samples), so the stream's
    webcam was never found. Here only faces (else people) anchored to a corner
    count, and the box must stay put across samples (camera_inset.stable_box).
    """
    import cv2
    import camera_inset
    import main as core_main
    import screencast_layout
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    boxes = []
    try:
        for i in range(samples):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int((i + 0.5) * total / samples))
            ok, frame = cap.read()
            if not ok:
                continue
            faces = [f for f in screencast_layout.detect_faces_full_res(frame)
                     if camera_inset.is_cornered(f["box"], width, height)]
            if faces:
                box = max(faces, key=lambda f: f["score"])["box"]
                boxes.append(camera_inset.inset_box(box, width, height, face=True))
                continue
            person = core_main.detect_person_yolo(frame)
            if person and camera_inset.is_cornered(person, width, height):
                boxes.append(camera_inset.inset_box(person, width, height))
    finally:
        cap.release()
    if len(boxes) < 3:
        return None, width, height
    return camera_inset.stable_box(boxes, width, height), width, height


def webcam(job_id: str) -> dict:
    if not JOB.fullmatch(job_id):
        return {"box": None, "error": "bad job id"}
    path = _source(job_id)
    if not path:
        return {"box": None, "error": "source video not found"}
    box, width, height = find_webcam(path)
    return {"box": [int(v) for v in box] if box else None, "width": width, "height": height}


def install(module) -> None:
    app = getattr(module, "app", None)
    if app is None:
        return
    app.add_api_route("/api/clipradar/webcam/{job_id}", webcam, methods=["GET"])
    # Ahead of any catch-all route or static mount the core registered earlier.
    app.router.routes.insert(0, app.router.routes.pop())
