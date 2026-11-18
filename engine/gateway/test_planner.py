import unittest

from planner import (LOUD_WINDOW_SEC, MAX_STRETCHES, MIN_GAP_SEC, SKIP_INTRO_SEC, STRETCH_SEC,
                     loudness_hotspots, plan, stretches_for, viewer_hotspots)

HOUR = 3600.0


class TestPlan(unittest.TestCase):
    def test_short_video_goes_in_whole(self):
        self.assertEqual([(s.start, s.end) for s in plan(600)], [(0.0, 600.0)])

    def test_empty_source_gives_nothing(self):
        self.assertEqual(plan(0), [])

    def test_viewer_clips_lead_and_cluster(self):
        clips = [
            {"start": 1000, "duration": 30, "views": 50},
            {"start": 1010, "duration": 30, "views": 900},
            {"start": 7000, "duration": 30, "views": 10},
        ]
        stretches = plan(3 * HOUR, viewer_clips=clips)
        self.assertEqual([(s.start, s.end) for s in stretches],
                         [(940.0, 940.0 + STRETCH_SEC), (6940.0, 6940.0 + STRETCH_SEC)])
        self.assertTrue(all(s.reason == "viewers clipped here" for s in stretches))

    def test_loudness_fills_the_rest_without_overlap(self):
        levels = [-60.0] * int(2 * HOUR)
        for t in range(3000, 3010):
            levels[t] = -5.0
        stretches = plan(2 * HOUR, viewer_clips=[{"start": 600, "duration": 20, "views": 5}],
                         levels_db=levels)
        reasons = [s.reason for s in stretches]
        self.assertIn("viewers clipped here", reasons)
        self.assertIn("loud reaction", reasons)
        self.assertLessEqual(len(stretches), MAX_STRETCHES)
        for a, b in zip(stretches, stretches[1:]):
            self.assertLessEqual(a.end, b.start)

    def test_never_more_than_the_cap(self):
        clips = [{"start": 600 * k, "duration": 20, "views": 1} for k in range(1, 30)]
        self.assertEqual(len(plan(5 * HOUR, viewer_clips=clips)), MAX_STRETCHES)

    def test_stretch_stays_inside_the_video(self):
        stretches = plan(HOUR, viewer_clips=[{"start": HOUR - 5, "duration": 30, "views": 1},
                                             {"start": 2, "duration": 30, "views": 1}])
        for s in stretches:
            self.assertGreaterEqual(s.start, 0)
            self.assertLessEqual(s.end, HOUR)
            self.assertAlmostEqual(s.length, STRETCH_SEC)

    def test_no_signal_spreads_across_the_stream(self):
        stretches = plan(5 * HOUR)
        self.assertEqual(len(stretches), MAX_STRETCHES)
        self.assertGreater(stretches[0].start, 0)

    def test_bad_viewer_clips_are_ignored(self):
        stretches = plan(HOUR, viewer_clips=[{"start": None}, {"start": -5, "views": 3}])
        self.assertEqual(stretches[0].reason, "spread across the stream")


class TestStretchCount(unittest.TestCase):
    def test_two_clips_per_stretch_within_bounds(self):
        self.assertEqual([stretches_for(n) for n in (1, 5, 10, 20, 50)], [1, 3, 5, 10, 10])

    def test_plan_honours_the_requested_count(self):
        clips = [{"start": 600 * k, "duration": 20, "views": 1} for k in range(1, 30)]
        self.assertEqual(len(plan(5 * HOUR, viewer_clips=clips, max_stretches=10)), 10)
        self.assertEqual(len(plan(5 * HOUR, viewer_clips=clips, max_stretches=3)), 3)
        self.assertEqual(len(plan(5 * HOUR, max_stretches=4)), 4)


class TestLoudness(unittest.TestCase):
    def test_peaks_are_separated(self):
        levels = [-60.0] * 3000
        for t in (500, 520, 2000):
            for k in range(LOUD_WINDOW_SEC):
                levels[t + k] = -3.0
        peaks = loudness_hotspots(levels, top=5)
        times = sorted(t for t, _ in peaks)
        for a, b in zip(times, times[1:]):
            self.assertGreaterEqual(b - a, MIN_GAP_SEC)
        self.assertTrue(any(abs(t - 500) <= LOUD_WINDOW_SEC for t in times))
        self.assertTrue(any(abs(t - 2000) <= LOUD_WINDOW_SEC for t in times))

    def test_loud_intro_is_ignored(self):
        levels = [-60.0] * 3000
        for t in range(0, 60):
            levels[t] = -1.0          # "starting soon" music
        for t in range(1500, 1520):
            levels[t] = -6.0          # the real reaction
        peaks = loudness_hotspots(levels, top=1)
        self.assertGreaterEqual(peaks[0][0], SKIP_INTRO_SEC)
        self.assertTrue(abs(peaks[0][0] - 1500) <= LOUD_WINDOW_SEC)

    def test_too_short_gives_nothing(self):
        self.assertEqual(loudness_hotspots([-10.0] * 5, top=3), [])

    def test_silence_floor_does_not_break_means(self):
        peaks = loudness_hotspots([float("-inf")] * 100 + [-1.0] * 30, top=1)
        self.assertEqual(len(peaks), 1)


class TestViewerHotspots(unittest.TestCase):
    def test_weight_counts_clippers_and_views(self):
        spots = viewer_hotspots([{"start": 10, "duration": 30, "views": 5},
                                 {"start": 20, "duration": 30, "views": 5}])
        self.assertEqual(spots, [(10.0, 210)])


if __name__ == "__main__":
    unittest.main()
