import json
import os
import tempfile
import unittest

import brief_import as bi
import campaign_api
import campaigns

HERE = os.path.dirname(__file__)


def fixture(name):
    with open(os.path.join(HERE, "fixtures", "briefs", name)) as fh:
        return fh.read()


GOOD = {"name": "$12,500 LACY GTA VI Marathon Pool", "agency": "Reach", "creator": "LACY", "source_channels": ["Lacy"],
        "source_since": "2026-11-18", "ends": None, "payout": "Pool split by views",
        "min_total_views": "750,000", "platforms": ["TikTok", "Instagram Reels", "YouTube Shorts", "Twitter"],
        "must_mention": "LACY", "hashtags": ["LACY", "#LACY"], "submit_within_min": 30,
        "audience": "50% English-speaking", "ai_content": "forbidden",
        "manual": ["LACY must be the main focus", "No logos of any kind"]}


class TestText(unittest.TestCase):
    def test_reach_page_keeps_rules_and_drops_scripts(self):
        text = bi.html_to_text(fixture("reach_LACYGTA.html"))
        self.assertIn("Your captions must use the hashtag: #LACY", text)
        self.assertIn("750,000", text)
        self.assertNotIn("<script", text)

    def test_only_brief_hosts_over_https(self):
        self.assertTrue(bi.check_url("https://reachclipping.com/LACYGTA"))
        for bad in ("http://reachclipping.com/LACYGTA", "https://evil.com/x", "https://reachclipping.com.evil.com/",
                    "file:///etc/passwd", "https://127.0.0.1/"):
            with self.assertRaises(bi.BriefError):
                bi.check_url(bad)

    def test_content_rewards_page_pulls_the_linked_reach_rules(self):
        pages = {"https://contentrewards.com/c/campaigns/abc":
                 "<p>Pool. RULES HERE: https://reachclipping.com/LACYGTA and https://evil.com/x</p>",
                 "https://reachclipping.com/LACYGTA": "<li>Your captions must use the hashtag: #LACY</li>"}
        brief = bi.gather_brief("https://contentrewards.com/c/campaigns/abc", fetch=lambda u: pages[u])
        self.assertEqual(brief["sources"], ["https://contentrewards.com/c/campaigns/abc", "https://reachclipping.com/LACYGTA"])
        self.assertIn("#LACY", brief["text"])

    def test_a_broken_rules_link_does_not_fail_the_import(self):
        def fetch(u):
            if "reachclipping" in u:
                raise OSError("down")
            return "<p>see https://reachclipping.com/LACYGTA</p>"
        self.assertEqual(len(bi.gather_brief("https://contentrewards.com/c/campaigns/x", fetch)["sources"]), 1)


class TestExtract(unittest.TestCase):
    TEXT = fixture("pasted_cpm_brief.txt")

    def test_retries_once_on_broken_json(self):
        replies = iter(["Sure! here you go", json.dumps(GOOD)])
        self.assertEqual(bi.extract(self.TEXT, llm=lambda p: next(replies))["name"], GOOD["name"])

    def test_gives_up_after_two_bad_replies(self):
        with self.assertRaises(bi.BriefError):
            bi.extract(self.TEXT, llm=lambda p: "{not json")

    def test_rejects_text_that_is_not_a_brief(self):
        with self.assertRaises(bi.BriefError):
            bi.extract("hi", llm=lambda p: "{}")

    def test_prompt_carries_the_text_and_date(self):
        seen = {}
        bi.extract(self.TEXT, llm=lambda p: seen.setdefault("p", p) and json.dumps(GOOD), today="2026-11-18")
        self.assertIn("Today is 2026-11-18", seen["p"])
        self.assertIn("streamhouse_la", seen["p"])


class TestNormalize(unittest.TestCase):
    def test_cleans_model_output(self):
        c = bi.normalize(GOOD, ["https://contentrewards.com/c/campaigns/a", "https://reachclipping.com/LACYGTA"])
        self.assertEqual(c["platforms"], ["tiktok", "instagram", "youtube", "x"])
        self.assertEqual(c["hashtags"], ["#LACY"])
        self.assertEqual(c["min_total_views"], 750000)
        self.assertEqual(c["source_since"], "2026-11-18T00:00:00Z")
        self.assertEqual(c["source_channels"], ["lacy"])
        self.assertEqual(c["marketplace"], "Content Rewards")
        self.assertEqual(c["rules_url"], "https://reachclipping.com/LACYGTA")
        self.assertEqual(c["id"], "reach-12-500-lacy-gta-vi-marathon-pool")
        self.assertTrue(any("AI" in m for m in c["manual"]))

    def test_group_creator_is_not_turned_into_a_login(self):
        c = bi.normalize({**GOOD, "creator": "CORE", "source_channels": []})
        self.assertEqual(c["source_channels"], [])

    def test_drops_junk_values(self):
        c = bi.normalize({**GOOD, "min_total_views": "lots", "source_since": "next week", "platforms": ["myspace"],
                          "source_channels": ["Bad Name!", "lacy"], "ai_content": "maybe", "submit_within_min": -5})
        self.assertIsNone(c["min_total_views"])
        self.assertIsNone(c["source_since"])
        self.assertEqual(c["platforms"], [])
        self.assertEqual(c["source_channels"], ["lacy"])
        self.assertEqual(c["ai_content"], "unclear")
        self.assertIsNone(c["submit_within_min"])

    def test_needs_a_name_and_some_rules(self):
        with self.assertRaises(bi.BriefError):
            bi.normalize({**GOOD, "name": " "})
        with self.assertRaises(bi.BriefError):
            bi.normalize({"name": "x", "creator": "two words"})

    def test_result_runs_through_the_clip_check(self):
        c = bi.normalize(GOOD)
        checks = campaigns.check_clip(c, {"streamer": "lacy", "vod_started": "2026-11-18T10:00:00Z",
                                          "caption": "LACY wins #LACY", "platforms": ["tiktok"]})
        self.assertEqual(campaigns.failed(checks), [])


class TestApi(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_save_list_replace_remove(self):
        code, out = campaign_api.handle_post("/campaigns", {"campaign": GOOD}, self.dir)
        self.assertEqual(code, 201)
        cid = out["campaign"]["id"]
        self.assertIn(cid, [c["id"] for c in campaigns.load_campaigns(self.dir)])
        campaign_api.handle_post("/campaigns", {"campaign": {**GOOD, "id": cid, "payout": "changed"}}, self.dir)
        saved = [c for c in campaigns.load_campaigns(self.dir) if c["id"] == cid]
        self.assertEqual([c["payout"] for c in saved], ["changed"])
        self.assertEqual(campaign_api.handle_post(f"/campaigns/{cid}/remove", {}, self.dir)[0], 200)
        self.assertEqual(campaign_api.handle_post(f"/campaigns/{cid}/remove", {}, self.dir)[0], 404)

    def test_reimporting_the_same_brief_replaces_it(self):
        builtin = next(c for c in campaigns.DEFAULT_CAMPAIGNS if c["id"] == "reach-lacy-gta")
        campaign_api.handle_post("/campaigns", {"campaign": {**GOOD, "rules_url": builtin["rules_url"]}}, self.dir)
        ids = [c["id"] for c in campaigns.load_campaigns(self.dir)]
        self.assertNotIn("reach-lacy-gta", ids)
        self.assertEqual(len([i for i in ids if "lacy" in i]), 1)

    def test_built_in_briefs_stay_until_removed(self):
        campaign_api.handle_post("/campaigns", {"campaign": GOOD}, self.dir)
        ids = [c["id"] for c in campaigns.load_campaigns(self.dir)]
        self.assertIn("reach-clix-gta", ids)

    def test_bad_input_is_400(self):
        self.assertEqual(campaign_api.handle_post("/campaigns", {"campaign": "x"}, self.dir)[0], 400)
        self.assertEqual(campaign_api.handle_post("/campaigns/import", {"url": "https://evil.com"}, self.dir)[0], 400)
        self.assertEqual(campaign_api.handle_post("/campaigns/import", {}, self.dir)[0], 400)


if __name__ == "__main__":
    unittest.main()
