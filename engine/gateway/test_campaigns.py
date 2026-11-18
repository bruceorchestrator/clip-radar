import unittest

from autopilot import campaign_for, item_checks
from clip_campaigns import broken_rules, build_post_text, matching, toggle
from campaigns import DEFAULT_CAMPAIGNS, check_clip, failed, verdict

LACY_CAMPAIGN = next(c for c in DEFAULT_CAMPAIGNS if c["id"] == "reach-lacy-gta")
GOOD = {"streamer": "lacy", "vod_started": "2026-11-18T10:11:00Z", "duration": 30,
        "caption": "LACY: his number one priority\n\n#LACY #gta6", "platforms": ["tiktok", "youtube"]}


def result(checks, prefix):
    return next(c["ok"] for c in checks if c["rule"].startswith(prefix))


class TestCheckClip(unittest.TestCase):
    def test_good_clip_only_needs_eyes(self):
        checks = check_clip(LACY_CAMPAIGN, GOOD)
        self.assertEqual(failed(checks), [])
        self.assertEqual(verdict(checks), "manual")

    def test_wrong_streamer_fails(self):
        self.assertFalse(result(check_clip(LACY_CAMPAIGN, {**GOOD, "streamer": "clix"}), "Footage from lacy"))

    def test_footage_before_the_marathon_fails(self):
        checks = check_clip(LACY_CAMPAIGN, {**GOOD, "vod_started": "2026-11-17T20:00:00Z"})
        self.assertFalse(result(checks, "Footage from 2026-11-18"))

    def test_unknown_stream_date_is_a_manual_check(self):
        self.assertIsNone(result(check_clip(LACY_CAMPAIGN, {**GOOD, "vod_started": None}), "Footage from 2026-11-18"))

    def test_missing_hashtag_and_name_fail(self):
        checks = check_clip(LACY_CAMPAIGN, {**GOOD, "caption": "crazy moment #gta6"})
        self.assertIn("Caption has #LACY", failed(checks))
        self.assertIn("Caption or on-screen text names LACY", failed(checks))

    def test_name_on_screen_is_enough_for_the_mention(self):
        checks = check_clip(LACY_CAMPAIGN, {**GOOD, "caption": "#LACY", "overlay": "LACY IN GTA 6"})
        self.assertTrue(result(checks, "Caption or on-screen text"))

    def test_platform_outside_the_brief_fails(self):
        checks = check_clip(LACY_CAMPAIGN, {**GOOD, "platforms": ["youtube", "facebook"]})
        self.assertFalse(result(checks, "Posted only where"))

    def test_japanese_caption_fails(self):
        self.assertFalse(result(check_clip(LACY_CAMPAIGN, {**GOOD, "caption": GOOD["caption"] + " すごい"}), "English caption"))

    def test_ended_campaign_fails(self):
        ended = {**LACY_CAMPAIGN, "ends": "2026-11-20T00:00:00Z"}
        self.assertFalse(result(check_clip(ended, GOOD, now=1_900_000_000), "Campaign is accepting"))

    def test_length_limits(self):
        brief = {**LACY_CAMPAIGN, "min_sec": 10, "max_sec": 25}
        self.assertFalse(result(check_clip(brief, GOOD), "Length within"))

    def test_all_automatic_rules_pass_gives_pass(self):
        brief = {**LACY_CAMPAIGN, "manual": []}
        self.assertEqual(verdict(check_clip(brief, GOOD)), "pass")


CORE = {"id": "reach-core", "name": "CORE pool", "source_channels": ["lacy", "jasontheween"],
        "platforms": ["tiktok", "instagram", "youtube", "x"], "must_mention": "CORE", "hashtags": ["#CORE"],
        "submit_within_min": 30, "manual": ["At least 2 CORE members in frame"]}
CAMPAIGNS = DEFAULT_CAMPAIGNS + [CORE]


class TestAutopilotWiring(unittest.TestCase):
    STREAMER = {"login": "lacy", "name": "LACY", "hashtags": ["#LACY", "#gta6"], "platforms": ["tiktok", "youtube"]}
    ITEM = {"streamer": "lacy", "hook": "his number one priority", "vod_started": "2026-11-18T10:11:00Z",
            "duration": 30, "status": "review"}

    def test_campaign_found_by_channel_or_by_id(self):
        self.assertEqual(campaign_for(self.STREAMER, DEFAULT_CAMPAIGNS)["id"], "reach-lacy-gta")
        self.assertEqual(campaign_for({**self.STREAMER, "campaign": "reach-clix-gta"}, DEFAULT_CAMPAIGNS)["id"],
                         "reach-clix-gta")
        self.assertEqual(campaign_for({**self.STREAMER, "campaign": "gone"}, DEFAULT_CAMPAIGNS)["id"], "reach-lacy-gta")
        self.assertIsNone(campaign_for({"login": "nobody", "campaign": "gone"}, DEFAULT_CAMPAIGNS))

    def test_forced_caption_passes_the_text_rules(self):
        check = item_checks(self.ITEM, self.STREAMER, DEFAULT_CAMPAIGNS)
        self.assertEqual(check["campaigns"][0]["campaign"]["id"], "reach-lacy-gta")
        self.assertEqual(broken_rules(check), [])

    def test_no_campaign_means_no_checks(self):
        self.assertEqual(item_checks({"streamer": "x"}, {"login": "x"}, DEFAULT_CAMPAIGNS)["verdict"], "none")

    def test_other_pools_are_listed_but_opt_in(self):
        check = item_checks(self.ITEM, self.STREAMER, CAMPAIGNS)
        self.assertEqual([(r["campaign"]["id"], r["selected"], r["primary"]) for r in check["campaigns"]],
                         [("reach-lacy-gta", True, True), ("reach-core", False, False)])
        self.assertNotIn("#CORE", check["text"]["caption"])
        # Shown as it would pass once added: the caption would then carry #CORE.
        self.assertEqual(failed(check["campaigns"][1]["checks"]), [])

    def test_opting_in_puts_every_pool_rule_in_the_caption(self):
        item = {**self.ITEM}
        matches = matching(self.STREAMER, CAMPAIGNS)
        self.assertIsNone(toggle(item, "reach-core", matches))
        check = item_checks(item, self.STREAMER, CAMPAIGNS)
        self.assertTrue(all(r["selected"] for r in check["campaigns"]))
        caption = check["text"]["caption"]
        self.assertIn("#LACY", caption)
        self.assertIn("#CORE", caption)
        self.assertEqual(broken_rules(check), [])
        self.assertEqual(check["verdict"], "manual")
        self.assertIsNone(toggle(item, "reach-core", matches))
        self.assertEqual(item["extra_campaigns"], [])

    def test_toggle_refuses_bad_moves(self):
        matches = matching(self.STREAMER, CAMPAIGNS)
        self.assertIsNotNone(toggle({**self.ITEM}, "reach-lacy-gta", matches))
        self.assertIsNotNone(toggle({**self.ITEM}, "reach-clix-gta", matches))
        self.assertIsNotNone(toggle({**self.ITEM, "status": "posted"}, "reach-core", matches))

    def test_a_broken_extra_pool_blocks_the_clip(self):
        strict = {**CORE, "platforms": ["tiktok"]}
        item = {**self.ITEM, "extra_campaigns": ["reach-core"]}
        check = item_checks(item, self.STREAMER, DEFAULT_CAMPAIGNS + [strict])
        self.assertEqual(check["verdict"], "fail")
        self.assertTrue(broken_rules(check)[0].startswith("CORE pool: Posted only where"))

    def test_name_is_added_when_no_hashtag_carries_it(self):
        brief = {**CORE, "hashtags": [], "must_mention": "CORE Miami"}
        text = build_post_text(self.ITEM, self.STREAMER, [brief])
        self.assertIn("(CORE Miami)", text["caption"])


if __name__ == "__main__":
    unittest.main()
