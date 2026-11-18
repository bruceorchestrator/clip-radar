import json
import os
import shutil
import tempfile
import unittest

import retention

JOB = "4463994c-cd55-41c3-b7df-d853c1fad95d"
OTHER = "6deb26a1-a0db-43c4-9690-78389694bb70"


def clip(job, n=1):
    return f"/videos/{job}/subtitled_17_{job}_stretch_clip_{n}.mp4"


class TestSlots(unittest.TestCase):
    STATE = {"items": [{"streamer": "lacy", "status": "review"}, {"streamer": "lacy", "status": "approved"},
                       {"streamer": "lacy", "status": "rejected"}, {"streamer": "clix", "status": "review"}],
             "pending": [{"streamer": "lacy"}]}

    def test_waiting_and_cooking_clips_fill_the_queue(self):
        self.assertEqual(retention.open_slots(self.STATE, "lacy", 3, 1), 0)
        self.assertEqual(retention.open_slots(self.STATE, "lacy", 5, 1), 2)
        self.assertEqual(retention.open_slots(self.STATE, "lacy", 5, 2), 1)   # the pending batch makes 2
        self.assertEqual(retention.open_slots(self.STATE, "clix", 3, 1), 2)

    def test_spots_for_free_slots(self):
        self.assertEqual(retention.spots_for(0, 1, 2), 0)
        self.assertEqual(retention.spots_for(3, 1, 2), 2)       # never more than max_spots_per_run
        self.assertEqual(retention.spots_for(1, 2, 2), 1)
        self.assertEqual(retention.spots_for(3, 2, 5), 2)


class TestExpire(unittest.TestCase):
    def test_only_long_waiting_review_clips_expire(self):
        now = 100_000.0
        state = {"items": [{"id": "old", "status": "review", "created": now - 13 * 3600},
                           {"id": "new", "status": "review", "created": now - 3600},
                           {"id": "clicked", "status": "approved", "created": now - 20 * 3600}]}
        self.assertEqual(retention.expire_stale(state, 12, now), ["old"])
        by_id = {i["id"]: i for i in state["items"]}
        self.assertEqual((by_id["old"]["status"], by_id["old"]["expired"]), ("rejected", True))
        self.assertEqual(by_id["new"]["status"], "review")
        self.assertEqual(by_id["clicked"]["status"], "approved")


class TestCleanup(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.data, self.out, self.up = (os.path.join(self.root, d) for d in ("data", "output", "uploads"))
        for job in (JOB, OTHER):
            os.makedirs(os.path.join(self.out, job))
            with open(os.path.join(self.out, job, "clip.mp4"), "wb") as fh:
                fh.write(b"x" * 100)
        os.makedirs(self.up)
        for job in (JOB, OTHER):
            with open(os.path.join(self.up, f"{job}_stretch.mp4"), "wb") as fh:
                fh.write(b"x" * 1000)
        for sub in ("stacked", "headlines"):
            os.makedirs(os.path.join(self.data, sub))
        for name in ("a" * 32 + "-0123abcd.mp4", "b" * 32 + "-0123abcd.mp4"):
            open(os.path.join(self.data, "stacked", name), "wb").close()

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_due_after_the_grace_hour_and_only_once(self):
        now = 10_000.0
        state = {"items": [{"id": "1", "status": "rejected", "updated": now - 4000},
                           {"id": "2", "status": "rejected", "updated": now - 60},
                           {"id": "3", "status": "posted", "updated": now - 4000, "files_removed": True},
                           {"id": "4", "status": "review", "updated": now - 99999}]}
        self.assertEqual([i["id"] for i in retention.due_for_cleanup(state, now)], ["1"])

    def test_removes_renders_and_the_core_job(self):
        item = {"id": "a" * 32, "status": "rejected", "video_path": "/videos/stacked/" + "a" * 32 + "-0123abcd.mp4",
                "engine_video_path": clip(JOB)}
        freed = retention.remove_files(item, self.data, set(), self.out, self.up)
        self.assertEqual(freed, 1100)
        self.assertTrue(item["files_removed"])
        self.assertFalse(os.path.exists(os.path.join(self.out, JOB)))
        self.assertFalse(os.path.exists(os.path.join(self.up, f"{JOB}_stretch.mp4")))
        self.assertEqual(os.listdir(os.path.join(self.data, "stacked")), ["b" * 32 + "-0123abcd.mp4"])
        self.assertTrue(os.path.exists(os.path.join(self.up, f"{OTHER}_stretch.mp4")))

    def test_keeps_a_job_a_waiting_clip_still_uses(self):
        closed = {"id": "a" * 32, "status": "posted", "video_path": clip(JOB, 1)}
        waiting = {"id": "b" * 32, "status": "review", "video_path": clip(JOB, 2)}
        in_use = retention.jobs_in_use({"items": [closed, waiting]})
        self.assertEqual(in_use, {JOB})
        retention.remove_files(closed, self.data, in_use, self.out, self.up)
        self.assertTrue(os.path.exists(os.path.join(self.up, f"{JOB}_stretch.mp4")))

    def test_never_touches_anything_for_a_path_that_is_not_a_core_clip(self):
        item = {"id": "../../etc", "status": "rejected", "video_path": "/videos/../../etc/passwd"}
        self.assertEqual(retention.remove_files(item, self.data, set(), self.out, self.up), 0)
        self.assertEqual(sorted(os.listdir(self.out)), sorted([JOB, OTHER]))


class TestAutopilotQueue(unittest.TestCase):
    def setUp(self):
        from autopilot import Autopilot, save_state
        self.dir = tempfile.mkdtemp()
        with open(f"{self.dir}/autopilot.json", "w") as fh:
            json.dump({"enabled": True, "streamers": [{"login": "lacy", "queue_cap": 3, "clips_per_spot": 1}]}, fh)
        self.save_state = save_state
        self.gql_calls, self.batches = [], []
        nodes = [{"slug": str(i), "viewCount": 100 - i, "durationSeconds": 30, "videoOffsetSeconds": 600 * i,
                  "createdAt": "2026-11-18T12:00:00Z", "game": None,
                  "video": {"id": "v", "createdAt": "2026-11-18T10:00:00Z"}} for i in range(1, 8)]

        def gql(query, variables):
            self.gql_calls.append(variables)
            return {"user": {"clips": {"edges": [{"node": n} for n in nodes]}}}

        def create_batch(url, start, end, clips, length):
            self.batches.append(clips)
            return f"batch{len(self.batches)}"
        self.pilot = Autopilot(self.dir, gql, create_batch, None, lambda b: None, None)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_cuts_only_into_free_places_one_clip_per_moment(self):
        from autopilot import load_config, load_state
        self.save_state(self.dir, {"items": [{"id": "x", "streamer": "lacy", "status": "review"}], "log": []})
        state = load_state(self.dir)
        self.pilot.find_new_moments(load_config(self.dir), state)
        self.assertEqual(self.batches, [1, 1])            # 2 free places, max 2 moments a run
        self.batches.clear()
        self.pilot.find_new_moments(load_config(self.dir), state)
        self.assertEqual(self.batches, [])                # full: nothing cut
        self.assertEqual(len(self.gql_calls), 1)          # and Twitch not even asked

    def test_reject_frees_a_place_and_asks_for_the_next_moment(self):
        self.save_state(self.dir, {"items": [{"id": "x", "streamer": "lacy", "status": "review"}], "log": []})
        self.assertIsNone(self.pilot.act("x", "reject"))
        self.assertTrue(self.pilot.run_requested.is_set())

    def test_no_unreject_once_the_files_are_gone(self):
        self.save_state(self.dir, {"items": [{"id": "x", "streamer": "lacy", "status": "rejected",
                                              "files_removed": True}], "log": []})
        self.assertEqual(self.pilot.act("x", "unreject"), "its files are already deleted")


if __name__ == "__main__":
    unittest.main()
