import unittest

from autopilot import apply_action, build_post_text, clips_from_view, due, pick_spots, posting_accounts, spot_key


def node(slug, vod, offset, views=10, game="Grand Theft Auto VI", duration=30, created="2026-11-18T12:00:00Z",
         vod_created="2026-11-18T10:11:00Z"):
    return {"slug": slug, "viewCount": views, "durationSeconds": duration, "videoOffsetSeconds": offset,
            "createdAt": created, "game": {"name": game},
            "video": {"id": vod, "createdAt": vod_created} if vod else None}


LACY = {"login": "lacy", "name": "LACY", "hashtags": ["#LACY", "#gta6"]}


class TestPickSpots(unittest.TestCase):
    def test_groups_clips_and_ranks_hottest_first(self):
        nodes = [node("a", "1", 1000, 50), node("b", "1", 1010, 500), node("c", "1", 5000, 5)]
        spots = pick_spots(nodes, "Grand Theft Auto VI", set(), 5)
        self.assertEqual([(s["vod"], int(s["t"])) for s in spots], [("1", 1000), ("1", 5000)])

    def test_skips_moments_already_done(self):
        nodes = [node("a", "1", 1000), node("b", "1", 5000)]
        spots = pick_spots(nodes, None, {spot_key("1", 1000)}, 5)
        self.assertEqual([int(s["t"]) for s in spots], [5000])

    def test_filters_game_and_clips_without_recording(self):
        nodes = [node("a", "1", 1000, game="Just Chatting"), node("b", None, 2000), node("c", "1", None)]
        self.assertEqual(pick_spots(nodes, "Grand Theft Auto VI", set(), 5), [])
        self.assertEqual(len(pick_spots(nodes, None, set(), 5)), 1)

    def test_ignores_clips_from_before_the_campaign(self):
        nodes = [node("old", "1", 1000, created="2026-11-17T23:00:00Z", vod_created="2026-11-17T20:00:00Z"),
                 node("new", "2", 500)]
        spots = pick_spots(nodes, None, set(), 5, since="2026-11-18T00:00:00Z")
        self.assertEqual([s["vod"] for s in spots], ["2"])

    def test_ignores_fresh_clips_of_an_old_recording(self):
        nodes = [node("late", "old", 900, created="2026-11-18T09:00:00Z", vod_created="2026-11-14T20:00:00Z"),
                 node("live", "new", 300)]
        spots = pick_spots(nodes, None, set(), 5, since="2026-11-18T00:00:00Z")
        self.assertEqual([s["vod"] for s in spots], ["new"])

    def test_respects_the_limit(self):
        nodes = [node(str(i), "1", 600 * i) for i in range(1, 10)]
        self.assertEqual(len(pick_spots(nodes, None, set(), 2)), 2)


class TestPostText(unittest.TestCase):
    def test_forces_name_and_hashtag(self):
        text = build_post_text({"hook": "He crashed the getaway car", "title": "Getaway gone wrong"}, LACY)
        self.assertTrue(text["caption"].startswith("LACY: He crashed the getaway car"))
        self.assertIn("#LACY", text["caption"])
        self.assertEqual(text["title"], "Getaway gone wrong | LACY")

    def test_keeps_name_when_already_there(self):
        text = build_post_text({"hook": "Lacy loses it", "title": "LACY vs the cops"}, LACY)
        self.assertTrue(text["caption"].startswith("Lacy loses it"))
        self.assertEqual(text["title"], "LACY vs the cops")

    def test_adds_hashtag_when_config_forgot_it(self):
        text = build_post_text({"hook": "x"}, {"login": "tomo", "name": "Tomo", "hashtags": ["#gta6"]})
        self.assertIn("#Tomo", text["caption"])

    def test_title_fits_youtube(self):
        text = build_post_text({"title": "a" * 150}, LACY)
        self.assertLessEqual(len(text["title"]), 100)


class TestClipsFromView(unittest.TestCase):
    VIEW = {"tasks": [
        {"engine": {"status": "completed", "result": {"clips": [
            {"predicted_score": 85, "video_url": "/videos/j/a.mp4", "viral_hook_text": "h", "start": 1, "end": 31},
            {"predicted_score": 60, "video_url": "/videos/j/b.mp4"},
            {"predicted_score": 90, "video_url": "https://evil/x.mp4"},
        ]}}},
        {"engine": {"status": "failed"}},
        {"engine": None},
    ]}

    def test_keeps_good_clips_only(self):
        clips = clips_from_view(self.VIEW, 70)
        self.assertEqual([c["video_path"] for c in clips], ["/videos/j/a.mp4"])
        self.assertEqual(clips[0]["duration"], 30.0)


class TestDue(unittest.TestCase):
    def test_runs_first_time_then_waits_for_the_interval(self):
        self.assertTrue(due(None, 2700, 1000.0))
        self.assertFalse(due(1000.0, 2700, 1000.0 + 600))
        self.assertTrue(due(1000.0, 2700, 1000.0 + 2700))


class TestApplyAction(unittest.TestCase):
    def test_review_flow(self):
        item = {"status": "review"}
        self.assertIsNone(apply_action(item, "approve"))
        self.assertEqual(item["status"], "approved")
        self.assertIsNone(apply_action(item, "reject"))
        self.assertEqual(item["status"], "rejected")
        self.assertIsNone(apply_action(item, "unreject"))
        self.assertEqual(item["status"], "review")

    def test_refuses_illegal_moves(self):
        self.assertIsNotNone(apply_action({"status": "posted"}, "reject"))
        self.assertIsNotNone(apply_action({"status": "review"}, "delete"))


class TestPostingAccounts(unittest.TestCase):
    TWO = {"login": "lacy", "accounts": [{"user": "default", "platforms": ["youtube"], "name": "Main Clips"},
                                         {"user": "second", "platforms": ["youtube"], "name": "Second"},
                                         {"user": "broken", "platforms": []}]}

    def test_accounts_list_or_old_single_account(self):
        self.assertEqual([a["user"] for a in posting_accounts(self.TWO)], ["default", "second"])
        self.assertEqual(posting_accounts({"login": "x", "upload_post_user": "u", "platforms": ["youtube"]}),
                         [{"user": "u", "platforms": ["youtube"]}])
        self.assertEqual(posting_accounts({"login": "x"}), [])



class TestPostAction(unittest.TestCase):
    def setUp(self):
        import json, tempfile
        from autopilot import Autopilot, save_state
        self.dir = tempfile.mkdtemp()
        with open(f"{self.dir}/autopilot.json", "w") as fh:
            json.dump({"streamers": [{"login": "lacy", "name": "LACY", "hashtags": ["#LACY"],
                                      "accounts": [{"user": "default", "platforms": ["youtube"], "name": "Main Clips"}]}]}, fh)
        save_state(self.dir, {"items": [{"id": "x1", "streamer": "lacy", "status": "review", "hook": "hi",
                                         "vod_started": "2026-11-18T10:00:00Z", "duration": 30}], "log": []})
        self.pilot = Autopilot(self.dir, None, None, None, None, None)

    def item(self):
        from autopilot import load_state
        return load_state(self.dir)["items"][0]

    def test_post_to_a_connected_channel_queues_it_right_away(self):
        self.assertIsNone(self.pilot.act("x1", "post", "default"))
        self.assertEqual((self.item()["status"], self.item()["post_to"]), ("approved", "default"))
        self.assertTrue(self.pilot.wake.is_set())

    def test_nothing_goes_out_without_a_channel(self):
        self.assertIsNotNone(self.pilot.act("x1", "post", "nope"))
        self.assertIsNotNone(self.pilot.act("x1", "approve"))
        self.assertEqual(self.item()["status"], "review")


if __name__ == "__main__":
    unittest.main()


class TestStackedLayout(unittest.TestCase):
    ENGINE = "/videos/4463994c-cd55-41c3-b7df-d853c1fad95d/subtitled_1_4463994c-cd55-41c3-b7df-d853c1fad95d_stretch_clip_1.mp4"

    def setUp(self):
        import json, tempfile
        from unittest import mock
        import stacked
        from autopilot import Autopilot, save_state
        self.dir = tempfile.mkdtemp()
        with open(f"{self.dir}/autopilot.json", "w") as fh:
            json.dump({"streamers": [{"login": "lacy", "layout": {"cam": [0, 0, 0.255, 0.256]}},
                                     {"login": "clix"}]}, fh)
        save_state(self.dir, {"items": [
            {"id": "a" * 32, "streamer": "lacy", "status": "review", "video_path": self.ENGINE},
            {"id": "b" * 32, "streamer": "clix", "status": "review", "video_path": self.ENGINE},
            {"id": "c" * 32, "streamer": "lacy", "status": "posted", "video_path": self.ENGINE}], "log": []})
        self.pilot = Autopilot(self.dir, None, None, None, None, None)
        self.calls, self.hooks = [], []

        def fake_render(path, layout, out_dir, item_id, captions=True, hook=None):
            self.calls.append((path, item_id, captions))
            self.hooks.append(hook)
            return f"/videos/stacked/{item_id}-0123abcd.mp4"
        patcher = mock.patch.object(stacked, "render", side_effect=fake_render)
        patcher.start()
        self.addCleanup(patcher.stop)

    def items(self):
        from autopilot import load_state
        return {i["id"][0]: i for i in load_state(self.dir)["items"]}

    def test_one_clip_per_pass_so_posting_is_not_stuck_behind_renders(self):
        from autopilot import load_state, save_state
        state = load_state(self.dir)
        state["items"].append({"id": "d" * 32, "streamer": "lacy", "status": "review", "video_path": self.ENGINE})
        save_state(self.dir, state)
        self.assertTrue(self.pilot.restack_new())       # one done, one still waiting
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(self.pilot.restack_new())      # last one
        self.assertEqual(len(self.calls), 2)
        self.assertFalse(self.pilot.restack_new())      # nothing left
        self.assertEqual(len(self.calls), 2)

    def test_new_clips_of_a_streamer_with_a_webcam_box_get_stacked_once(self):
        self.assertFalse(self.pilot.restack_new())
        items = self.items()
        self.assertEqual(items["a"]["video_path"], "/videos/stacked/" + "a" * 32 + "-0123abcd.mp4")
        self.assertEqual(items["a"]["engine_video_path"], self.ENGINE)
        self.assertEqual(items["a"]["layout"], "stacked")
        self.assertEqual(items["b"]["layout"], "engine")  # no webcam box for Clix: the core's framing
        self.assertNotIn("layout", items["c"])          # already posted
        self.pilot.restack_new()
        self.assertEqual(len(self.calls), 1)

    def test_back_to_the_core_layout_and_again(self):
        self.pilot.restack_new()
        self.assertIsNone(self.pilot.set_layout("a" * 32, "engine"))
        self.assertEqual(self.items()["a"]["video_path"], self.ENGINE)
        self.assertIsNone(self.pilot.set_layout("a" * 32, "stacked"))
        self.assertTrue(self.items()["a"]["video_path"].startswith("/videos/stacked/"))
        self.assertEqual(self.calls[-1][0], self.ENGINE)          # always re-cut from the core's clip

    def test_failed_render_keeps_the_core_layout_and_says_why(self):
        import stacked
        with __import__("unittest").mock.patch.object(stacked, "render", side_effect=RuntimeError("stretch gone")):
            self.pilot.restack_new()
        item = self.items()["a"]
        self.assertEqual(item["layout"], "engine")
        self.assertEqual(item["video_path"], self.ENGINE)
        self.assertIn("stretch gone", item["layout_error"])

    def test_stacked_clips_carry_their_hook(self):
        from autopilot import load_state, save_state
        state = load_state(self.dir)
        state["items"][0]["hook"] = "He stole a car for his mom 💀"
        save_state(self.dir, state)
        self.pilot.restack_new()
        self.assertEqual(self.hooks, ["He stole a car for his mom"])

    def test_clips_of_an_older_look_are_rendered_again_once(self):
        import stacked
        from autopilot import load_state, save_state
        self.pilot.restack_new()
        self.assertEqual(self.items()["a"]["stacked_version"], stacked.RENDER_VERSION)
        state = load_state(self.dir)
        state["items"][0]["stacked_version"] = stacked.RENDER_VERSION - 1
        save_state(self.dir, state)
        self.pilot.restack_new()
        self.pilot.restack_new()
        self.assertEqual(len(self.calls), 2)
        self.assertIsNone(self.pilot.set_layout("a" * 32, "engine"))
        self.pilot.restack_new()                         # a clip put back on the core layout stays there
        self.assertEqual(len(self.calls), 2)

    def test_no_layout_change_while_a_headline_is_on(self):
        from autopilot import load_state, save_state
        state = load_state(self.dir)
        state["items"][0]["headline"] = "HI"
        save_state(self.dir, state)
        self.assertEqual(self.pilot.set_layout("a" * 32, "stacked"), "go back to captions first")


class TestPostClipCover(unittest.TestCase):
    def test_youtube_upload_carries_the_cover_and_reports_a_refused_one(self):
        import json
        from unittest import mock
        import posting
        sent = {}

        def fake(path, body, content_type, idempotency=None):
            sent.update(path=path, body=body)
            return {"results": {"youtube": {"success": True, "url": "https://youtu.be/x",
                                            "thumbnail_error": "channel not verified"}}}
        with mock.patch.object(posting, "_upload_post", side_effect=fake):
            out = posting.post_upload_post({"id": "i1"}, {"user": "default", "platforms": ["youtube"]},
                                      b"VIDEO", {"title": "t", "caption": "c"}, cover=b"\xff\xd8JPEG")
        self.assertEqual(sent["path"], "/api/upload")
        self.assertIn(b'name="thumbnail"; filename="cover.jpg"', sent["body"])
        self.assertIn(b"\xff\xd8JPEG", sent["body"])
        self.assertEqual(out["youtube"], "https://youtu.be/x")
        self.assertEqual(out["youtube cover"], "error: channel not verified")
        json.dumps(out)

    def test_no_cover_field_without_youtube(self):
        from unittest import mock
        import posting
        sent = {}
        with mock.patch.object(posting, "_upload_post", side_effect=lambda p, b, c, idempotency=None: sent.update(body=b) or {"results": {}}):
            posting.post_upload_post({"id": "i1"}, {"user": "u", "platforms": ["tiktok"]}, b"V",
                                {"title": "t", "caption": "c"}, cover=b"JPEG")
        self.assertNotIn(b'name="thumbnail"', sent["body"])
