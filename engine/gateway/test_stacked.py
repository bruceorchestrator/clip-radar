import json
import os
import shutil
import subprocess
import tempfile
import unittest

import stacked

LACY_CAM = [0, 0, 0.255, 0.256]
JOB = "4463994c-cd55-41c3-b7df-d853c1fad95d"

ENGINE_ASS = """﻿[Script Info]
ScriptType: v4.00+
PlayResY: 288
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Anton,34,&H00FFFFFF,&H00FFFFFF,&H00000000,&HFF000000,1,0,0,0,100,100,0,0,1,2,0,2,10,10,43,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.35,0:00:00.85,Default,,0,0,0,,{\\c&H00E5FF&}WELL,{\\r} THAT
"""


class TestGeometry(unittest.TestCase):
    def test_webcam_band_on_top_and_game_clear_of_the_corner_cam(self):
        g = stacked.geometry(1920, 1080, LACY_CAM, game_center=0.495)
        cx, cy, cw, ch = g["cam"]
        gx, gy, gw, gh = g["game"]
        self.assertEqual((cx, cy), (0, 0))
        self.assertEqual(g["top_h"] + g["game_h"], 1920)
        self.assertGreaterEqual(gx, cx + cw)              # no second, small streamer
        self.assertLessEqual(gx + gw, 1920)
        self.assertEqual(gh, 1080)
        # Each band keeps the source aspect (no stretching), within rounding.
        self.assertAlmostEqual(cw / ch, 1080 / g["top_h"], delta=0.02)
        self.assertAlmostEqual(gw / gh, 1080 / g["game_h"], delta=0.02)

    def test_webcam_on_the_right_keeps_the_game_left_of_it(self):
        g = stacked.geometry(1920, 1080, [0.75, 0.0, 1.0, 0.25])
        gx, _, gw, _ = g["game"]
        self.assertLessEqual(gx + gw, g["cam"][0])

    def test_empty_box_is_refused(self):
        with self.assertRaises(ValueError):
            stacked.geometry(1920, 1080, [0.3, 0.3, 0.3, 0.5])


class TestCaptions(unittest.TestCase):
    def test_restyle_moves_captions_to_the_seam_and_keeps_the_words(self):
        out = stacked.restyle_ass(ENGINE_ASS, top_h=608)
        self.assertIn("PlayResX: 1080", out)
        self.assertIn("PlayResY: 1920", out)
        self.assertNotIn("PlayResY: 288", out)
        style = next(line for line in out.splitlines() if line.startswith("Style:")).split(",")
        self.assertEqual(style[2], str(stacked.CAPTION_SIZE))
        self.assertEqual(style[18], "8")                          # top-centre anchor
        self.assertEqual(int(style[21]), 608 - int(stacked.CAPTION_SIZE * 0.6))
        self.assertIn("{\\c&H00E5FF&}WELL,{\\r} THAT", out)


class TestSources(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.out = os.path.join(self.root, "output")
        self.up = os.path.join(self.root, "uploads")
        os.makedirs(os.path.join(self.out, JOB))
        os.makedirs(self.up)
        meta = {"shorts": [{"start": 11.64, "end": 36.2}, {"start": 50.0, "end": 70.0}],
                "source_video": f"{JOB}_stretch.mp4"}
        with open(os.path.join(self.out, JOB, f"{JOB}_stretch_metadata.json"), "w") as fh:
            json.dump(meta, fh)
        with open(os.path.join(self.out, JOB, f"{JOB}_stretch_clip_1.mp4.layout.json"), "w") as fh:
            json.dump({"ranges": [{"start": 0, "end": 24.583}]}, fh)
        with open(os.path.join(self.out, JOB, f"{JOB}_stretch_clip_2.mp4.layout.json"), "w") as fh:
            json.dump({"ranges": [{"start": 0, "end": 12.0}]}, fh)   # cut down: not one straight piece
        open(os.path.join(self.out, JOB, "autosubs_1795015279_d2fcbd7e.ass"), "w").close()
        open(os.path.join(self.up, f"{JOB}_stretch.mp4"), "w").close()

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_parse_clip(self):
        self.assertEqual(stacked.parse_clip(f"/videos/{JOB}/subtitled_1795015279_{JOB}_stretch_clip_1.mp4"),
                         {"job": JOB, "n": 1, "ts": "1795015279"})
        self.assertEqual(stacked.parse_clip(f"/videos/{JOB}/{JOB}_stretch_clip_3.mp4")["ts"], None)
        self.assertIsNone(stacked.parse_clip("/videos/headline/abc.mp4"))
        self.assertIsNone(stacked.parse_clip(f"/videos/{JOB}/../{JOB}_stretch_clip_1.mp4"))

    def test_sources_finds_the_stretch_times_and_captions(self):
        src = stacked.sources(f"/videos/{JOB}/subtitled_1795015279_{JOB}_stretch_clip_1.mp4", self.out, self.up)
        self.assertEqual((src["start"], src["end"]), (11.64, 36.2))
        self.assertTrue(src["ass"].endswith("autosubs_1795015279_d2fcbd7e.ass"))
        self.assertTrue(src["stretch"].endswith(f"{JOB}_stretch.mp4"))

    def test_sources_refuses_a_clip_that_is_not_one_straight_cut(self):
        with self.assertRaises(ValueError):
            stacked.sources(f"/videos/{JOB}/{JOB}_stretch_clip_2.mp4", self.out, self.up)

    def test_paths(self):
        self.assertTrue(stacked.is_local("/videos/stacked/" + "a" * 32 + "-0123abcd.mp4"))
        self.assertFalse(stacked.is_local("/videos/stacked/../x.mp4"))


def has_libass() -> bool:
    if not shutil.which("ffmpeg"):
        return False
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return " subtitles " in out


@unittest.skipUnless(has_libass(), "ffmpeg here has no libass (the gateway image has it)")
class TestRender(unittest.TestCase):
    def test_renders_a_1080x1920_clip_of_the_right_length(self):
        root = tempfile.mkdtemp()
        try:
            out_dir, up_dir, data = (os.path.join(root, d) for d in ("output", "uploads", "data"))
            for d in (os.path.join(out_dir, JOB), up_dir, data):
                os.makedirs(d)
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=60:d=6",
                            "-f", "lavfi", "-i", "sine=d=6", "-shortest", "-c:v", "libx264", "-preset", "ultrafast",
                            os.path.join(up_dir, f"{JOB}_stretch.mp4")], check=True)
            with open(os.path.join(out_dir, JOB, f"{JOB}_stretch_metadata.json"), "w") as fh:
                json.dump({"shorts": [{"start": 1.0, "end": 4.0}]}, fh)
            with open(os.path.join(out_dir, JOB, "autosubs_17_x.ass"), "w") as fh:
                fh.write(ENGINE_ASS)
            path = stacked.render(f"/videos/{JOB}/subtitled_17_{JOB}_stretch_clip_1.mp4", {"cam": LACY_CAM},
                                  stacked.folder(data), "a" * 32, output_dir=out_dir, uploads_dir=up_dir)
            local = stacked.local_file(data, path)
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height:format=duration",
                                    "-of", "json", local], capture_output=True, text=True, check=True).stdout
            info = json.loads(probe)
            video = next(s for s in info["streams"] if s.get("width"))
            self.assertEqual((video["width"], video["height"]), (1080, 1920))
            self.assertAlmostEqual(float(info["format"]["duration"]), 3.0, delta=0.2)
        finally:
            shutil.rmtree(root)


if __name__ == "__main__":
    unittest.main()
