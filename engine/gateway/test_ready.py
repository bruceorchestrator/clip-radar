"""Ready clips: a finished moment someone brings (file or clip link) goes through
captions, hook, layout and the review queue without the moment search."""
import json
import shutil
import tempfile
import unittest
from unittest import mock

import autopilot
from autopilot import Autopilot, load_config, load_state, save_state

ENGINE = ("/videos/4463994c-cd55-41c3-b7df-d853c1fad95d/subtitled_1_"
          "4463994c-cd55-41c3-b7df-d853c1fad95d_stretch_clip_1.mp4")


def view(status, clips):
    return {"status": status, "tasks": [{"engine": {"status": status, "result": {"clips": clips}}}]}


class TestReadyQueue(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        with open(f"{self.dir}/autopilot.json", "w") as fh:
            json.dump({"enabled": True, "min_score": 70, "streamers": [{"login": "lacy", "name": "LACY"}]}, fh)
        save_state(self.dir, {"items": [], "log": []})
        self.views = {}
        self.pilot = Autopilot(self.dir, None, None, lambda b: self.views[b["id"]], lambda b: {"id": b}, None)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_a_new_streamer_is_added_with_the_autopilot_off(self):
        login = self.pilot.add_ready("b1", "N3on", "N3on", "He survived the crash")
        self.assertEqual(login, "n3on")
        streamer = next(s for s in load_config(self.dir)["streamers"] if s["login"] == "n3on")
        self.assertEqual((streamer["enabled"], streamer["name"], streamer["hashtags"]), (False, "N3on", ["#N3on"]))
        self.assertEqual(load_state(self.dir)["pending"][0],
                         {"batch": "b1", "streamer": "n3on", "ready": True, "hook": "He survived the crash"})
        self.pilot.add_ready("b2", "n3on")
        self.assertEqual(len(load_config(self.dir)["streamers"]), 2)       # added once

    def test_the_clip_joins_the_queue_whatever_its_score_with_the_given_hook(self):
        self.pilot.add_ready("b1", "lacy", hook="My hook")
        self.views["b1"] = view("completed", [
            {"predicted_score": 40, "video_url": ENGINE, "viral_hook_text": "engine hook", "start": 0, "end": 30},
            {"predicted_score": 90, "video_url": ENGINE.replace("clip_1", "clip_2"), "start": 0, "end": 10}])
        state = load_state(self.dir)
        self.pilot.collect_finished(load_config(self.dir), state)
        self.assertEqual(len(state["items"]), 1)
        item = state["items"][0]
        self.assertEqual((item["hook"], item["ready"], item["status"], item["streamer"]),
                         ("My hook", True, "review", "lacy"))
        self.assertEqual(state["pending"], [])

    def test_a_failed_ready_clip_leaves_the_pending_list_with_a_log_line(self):
        self.pilot.add_ready("b1", "lacy")
        self.views["b1"] = view("failed", [])
        state = load_state(self.dir)
        self.pilot.collect_finished(load_config(self.dir), state)
        self.assertEqual((state["items"], state["pending"]), ([], []))
        self.assertIn("ready clip for lacy failed", state["log"][-1])

    def test_streamer_login(self):
        self.assertEqual(autopilot.streamer_login(" IShowSpeed "), "ishowspeed")
        with self.assertRaises(ValueError):
            autopilot.streamer_login("  !! ")


class TestWebcamSearch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        with open(f"{self.dir}/autopilot.json", "w") as fh:
            json.dump({"streamers": [{"login": "n3on", "enabled": False}]}, fh)
        save_state(self.dir, {"items": [{"id": "a" * 32, "streamer": "n3on", "status": "review",
                                         "video_path": ENGINE}], "log": []})
        self.renders = []

    def tearDown(self):
        shutil.rmtree(self.dir)

    def run_with(self, found):
        import stacked
        pilot = Autopilot(self.dir, None, None, None, None, None, detect_webcam=lambda path: found)
        with mock.patch.object(stacked, "render", side_effect=lambda *a, **k: self.renders.append(a[1]) or
                               "/videos/stacked/" + "a" * 32 + "-0123abcd.mp4"):
            pilot.restack_new()
        return load_state(self.dir)["items"][0]

    def test_a_found_webcam_gives_the_stacked_layout(self):
        item = self.run_with([0.0, 0.0, 0.25, 0.25])
        self.assertEqual(item["layout"], "stacked")
        self.assertEqual(item["cam"], [0.0, 0.0, 0.25, 0.25])
        self.assertEqual(self.renders, [{"cam": [0.0, 0.0, 0.25, 0.25], "game_center": 0.5}])

    def test_no_webcam_keeps_the_core_layout_and_says_why(self):
        item = self.run_with(None)
        self.assertEqual((item["layout"], item["cam_checked"]), ("engine", True))
        self.assertIn("no webcam", item["layout_error"])
        self.assertEqual(self.renders, [])


class TestReadySettings(unittest.TestCase):
    def test_one_clip_as_long_as_the_file(self):
        import sys
        sys.modules.setdefault("campaign_api", __import__("campaign_api"))
        import gateway
        settings = gateway.ready_settings({"length": "medium"}, 31.4)
        self.assertEqual((settings["target_clips"], settings["clip_min_seconds"], settings["clip_max_seconds"]),
                         (1, 27, 32))
        short = gateway.ready_settings({}, 4.0)
        self.assertGreaterEqual(short["clip_max_seconds"] - short["clip_min_seconds"], 5)


if __name__ == "__main__":
    unittest.main()
