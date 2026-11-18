import os
import shutil
import subprocess
import tempfile
import unittest

import headline

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "fonts", "Anton-Regular.ttf")


def has_drawtext() -> bool:
    if not shutil.which("ffmpeg"):
        return False
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return " drawtext " in out


class TestHelpers(unittest.TestCase):
    def test_clean_clip_drops_the_subtitled_prefix(self):
        self.assertEqual(headline.clean_clip_path("/videos/j1/subtitled_1795000014_j1_stretch_clip_2.mp4"),
                         "/videos/j1/j1_stretch_clip_2.mp4")
        self.assertEqual(headline.clean_clip_path("/videos/j1/j1_stretch_clip_2.mp4"), "/videos/j1/j1_stretch_clip_2.mp4")

    def test_lines_are_capitals_wrapped_for_the_format(self):
        self.assertEqual(headline.lines("he stole a car   for his mom"), ["HE STOLE A CAR", "FOR HIS MOM"])
        self.assertEqual(headline.lines("he stole a car for his mom", "horizontal"), ["HE STOLE A CAR FOR HIS MOM"])
        self.assertEqual(headline.lines("   "), [])

    def test_only_our_own_files_are_served(self):
        ok = "/videos/headline/" + "a" * 32 + "-0123abcd.mp4"
        self.assertTrue(headline.is_local(ok))
        for bad in ("/videos/headline/../autopilot.json", "/videos/headline/x.mp4", "/videos/job/a.mp4"):
            self.assertFalse(headline.is_local(bad))
        self.assertIsNone(headline.local_file("/data", "/videos/headline/../x"))

    def test_one_box_per_line(self):
        graph = headline.filter_graph(["A", "B"], ["/t/0", "/t/1"], 1080, 1920)
        self.assertEqual(graph.count("drawtext="), 2)
        self.assertIn("box=1:boxcolor=black", graph)


@unittest.skipUnless(has_drawtext() and os.path.exists(FONT), "needs ffmpeg with drawtext and the font")
class TestRender(unittest.TestCase):
    def test_renders_a_headline_version(self):
        tmp = tempfile.mkdtemp()
        src = os.path.join(tmp, "src.mp4")
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=540x960:d=1",
                        "-f", "lavfi", "-i", "anullsrc", "-shortest", "-c:v", "libx264", "-c:a", "aac", src], check=True)
        old = headline.FONT
        headline.FONT = FONT
        try:
            with open(src, "rb") as fh:
                path = headline.render(fh.read(), tmp, "a" * 32, "He stole a car for his mom")
        finally:
            headline.FONT = old
        self.assertTrue(headline.is_local(path))
        self.assertGreater(os.path.getsize(os.path.join(tmp, path.rsplit("/", 1)[1])), 1000)


if __name__ == "__main__":
    unittest.main()
