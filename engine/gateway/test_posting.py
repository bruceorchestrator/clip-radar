import json
import os
import unittest
from unittest import mock

import posting
from autopilot import posting_accounts

TEXT = {"title": "He stole a car | LACY", "caption": "LACY: He stole a car #LACY"}


class TestAccounts(unittest.TestCase):
    def test_services_keys_and_the_config_fallback(self):
        fallback = [{"name": "My Clips", "via": "postiz", "platforms": ["x"], "integrations": {"x": "i1"}},
                    {"name": "By hand", "via": "manual", "platforms": ["tiktok"]},
                    {"name": "no profile", "platforms": ["youtube"]}]          # upload-post needs a user
        accounts = posting_accounts({"login": "n3on"}, fallback)
        self.assertEqual([a["user"] for a in accounts], ["My Clips", "By hand"])
        own = posting_accounts({"login": "lacy", "accounts": [{"user": "default", "platforms": ["youtube"]}]}, fallback)
        self.assertEqual([a["user"] for a in own], ["default"])                # a streamer's own accounts win

    def test_ready_needs_the_service_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(posting.ready({"via": "postiz"}))
            self.assertFalse(posting.ready({}))                                 # upload-post by default
            self.assertTrue(posting.ready({"via": "manual"}))
            self.assertFalse(posting.ready({"via": "nope"}))
        with mock.patch.dict(os.environ, {"POSTIZ_API_KEY": "k"}):
            self.assertTrue(posting.ready({"via": "postiz"}))


class TestPostiz(unittest.TestCase):
    def test_uploads_once_and_posts_now_to_each_integration(self):
        calls = []

        def fake(path, body, content_type):
            calls.append((path, body, content_type))
            if path == "/upload":
                return {"id": f"m{len(calls)}", "path": f"https://u/{len(calls)}"}
            return [{"postId": "p1", "integration": "yt"}, {"postId": "p2", "integration": "x"}]
        account = {"via": "postiz", "platforms": ["youtube", "x", "tiktok"],
                   "integrations": {"youtube": "yt", "x": "xid"}}
        with mock.patch.dict(os.environ, {"POSTIZ_API_KEY": "k"}), \
                mock.patch.object(posting, "_postiz", side_effect=fake):
            out = posting.post({"id": "i1", "video_path": "/v.mp4"}, account, b"VIDEO", TEXT, cover=b"JPEG")
        self.assertEqual([c[0] for c in calls], ["/upload", "/upload", "/posts"])   # video, cover, post
        payload = json.loads(calls[2][1])
        self.assertEqual(payload["type"], "now")
        self.assertEqual([p["integration"]["id"] for p in payload["posts"]], ["yt", "xid"])
        youtube = payload["posts"][0]["settings"]
        self.assertEqual((youtube["__type"], youtube["type"], youtube["title"]), ("youtube", "public", TEXT["title"]))
        self.assertEqual(youtube["thumbnail"], {"id": "m2", "path": "https://u/2"})
        self.assertEqual(payload["posts"][1]["value"][0]["image"], [{"id": "m1", "path": "https://u/1"}])
        self.assertEqual(out["youtube"], "sent to Postiz (post p1)")
        self.assertTrue(out["tiktok"].startswith("error"))                      # no integration id for it

    def test_tiktok_settings_are_complete(self):
        settings = posting.postiz_settings("tiktok", TEXT)
        for key in ("privacy_level", "duet", "stitch", "comment", "autoAddMusic", "brand_content_toggle",
                    "brand_organic_toggle", "content_posting_method"):
            self.assertIn(key, settings)


class TestManualAndErrors(unittest.TestCase):
    def test_manual_sends_nothing_and_points_at_the_file(self):
        out = posting.post({"id": "i1", "video_path": "/videos/stacked/a.mp4"},
                           {"via": "manual", "platforms": ["tiktok"]}, b"V", TEXT)
        self.assertEqual(out["download"], "/videos/stacked/a.mp4")
        self.assertFalse(posting.wants_cover({"via": "manual", "platforms": ["youtube"]}))

    def test_a_service_without_its_key_fails_loudly(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                posting.post({"id": "i1"}, {"via": "postiz", "platforms": ["x"]}, b"V", TEXT)


if __name__ == "__main__":
    unittest.main()
