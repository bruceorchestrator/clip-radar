import array
import os
import shutil
import subprocess
import tempfile
import unittest

import thumbnail
from test_headline import has_drawtext


class TestPicking(unittest.TestCase):
    def test_hook_text_drops_emoji_and_prefers_the_headline(self):
        self.assertEqual(thumbnail.hook_text({"hook": "He tried to hit the dunk 🏀"}), "He tried to hit the dunk")
        self.assertEqual(thumbnail.hook_text({"hook": "x", "headline": "LACY LOST IT"}), "LACY LOST IT")
        self.assertEqual(thumbnail.hook_text({}), "")

    def test_loudest_moment_finds_the_shout_and_skips_the_edges(self):
        rate = 100
        quiet, loud = [10] * rate, [9000] * (rate // 2)
        samples = array.array("h", quiet * 3 + loud + quiet * 3)        # shout at 3.0-3.5 s
        self.assertAlmostEqual(thumbnail.loudest_moment(samples, rate), 3.25)
        edge_shout = array.array("h", loud + quiet * 6)                  # shout in the first 0.5 s
        self.assertGreaterEqual(thumbnail.loudest_moment(edge_shout, rate), 1.0)

    def test_short_or_silent_audio_does_not_crash(self):
        self.assertEqual(thumbnail.loudest_moment(array.array("h"), 100), 0.0)
        self.assertGreaterEqual(thumbnail.loudest_moment(array.array("h", [0] * 50), 100), 0.0)


@unittest.skipUnless(has_drawtext(), "ffmpeg here has no drawtext (the gateway image has it)")
class TestRender(unittest.TestCase):
    def test_vertical_cover_is_a_small_jpeg(self):
        tmp = tempfile.mkdtemp()
        try:
            clip = os.path.join(tmp, "c.mp4")
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=4",
                            "-f", "lavfi", "-i", "sine=d=4", "-shortest", "-c:v", "libx264", "-preset", "ultrafast", clip],
                           check=True)
            with open(clip, "rb") as fh:
                jpeg = thumbnail.render(fh.read(), "He tried to hit the dunk")
            self.assertEqual(jpeg[:2], b"\xff\xd8")
            self.assertLess(len(jpeg), thumbnail.MAX_BYTES)
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
