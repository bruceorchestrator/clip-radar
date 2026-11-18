import unittest

from gateway import clip_settings, supported, twitch_vod_id


class TestClipSettings(unittest.TestCase):
    def test_spreads_the_clips_over_the_stretches(self):
        self.assertEqual(clip_settings({"clips": 10, "length": "medium"}, 5),
                         {"target_clips": 2, "clip_min_seconds": 15, "clip_max_seconds": 45, "output_format": "vertical"})
        self.assertEqual(clip_settings({"clips": 5, "length": "short"}, 3)["target_clips"], 2)

    def test_engine_limit_of_15_per_job(self):
        self.assertEqual(clip_settings({"clips": 30, "length": "long"}, 1),
                         {"target_clips": 15, "clip_min_seconds": 30, "clip_max_seconds": 60, "output_format": "vertical"})

    def test_defaults_when_missing(self):
        self.assertEqual(clip_settings({}, 0),
                         {"target_clips": 10, "clip_min_seconds": 15, "clip_max_seconds": 45, "output_format": "vertical"})


    def test_wide_format_for_x_and_junk_falls_back(self):
        self.assertEqual(clip_settings({"format": "horizontal"}, 1)["output_format"], "horizontal")
        self.assertEqual(clip_settings({"format": "square-ish"}, 1)["output_format"], "vertical")


class TestLinks(unittest.TestCase):
    def test_supported_hosts_only(self):
        self.assertTrue(supported("https://www.twitch.tv/videos/1"))
        self.assertTrue(supported("https://kick.com/x/videos/abc"))
        self.assertFalse(supported("http://www.twitch.tv/videos/1"))
        self.assertFalse(supported("https://twitch.tv.evil.com/videos/1"))
        self.assertFalse(supported("https://backend:8000/api/status"))

    def test_vod_id(self):
        self.assertEqual(twitch_vod_id("https://www.twitch.tv/videos/2930630566"), "2930630566")
        self.assertIsNone(twitch_vod_id("https://www.twitch.tv/lirik/clip/Abc"))
        self.assertIsNone(twitch_vod_id("https://kick.com/videos/1"))


if __name__ == "__main__":
    unittest.main()
