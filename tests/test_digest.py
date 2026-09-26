"""Offline tests. Run with:  python -m unittest discover tests"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from newsdigest import ai, cluster, collect, extract, main, render, settings
from newsdigest.filters import is_blocked, is_opinion_title, is_opinion_url
from newsdigest.gate import should_send
from newsdigest.models import Article, Item
from newsdigest.textutil import clean_headline, similarity, tokens

UTC = timezone.utc
NOW = datetime(2026, 9, 24, 19, 30, tzinfo=UTC)  # Friday 25 September, 3:30am in Perth

SAMPLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>"Perth" - Google News</title>
<item><title>Perth rail line to close for six weeks - ABC News</title>
<link>https://news.google.com/rss/articles/CBMiAAA?oc=5</link>
<pubDate>Wed, 24 Sep 2026 10:00:00 GMT</pubDate>
<description>&lt;a href="x"&gt;Perth rail line to close for six weeks&lt;/a&gt; ABC News</description>
<source url="https://www.abc.net.au">ABC News</source></item>
<item><title>Opinion: The rail closure is a disaster - WAtoday</title>
<link>https://news.google.com/rss/articles/CBMiBBB?oc=5</link>
<pubDate>Wed, 24 Sep 2026 11:00:00 GMT</pubDate>
<source url="https://www.watoday.com.au">WAtoday</source></item>
</channel></rss>"""


def cfg():
    return settings.load_config()


def item(title, source="ABC News", hours_ago=2, category="perth", link=None):
    return Item(
        title=title, link=link or f"https://news.google.com/{abs(hash((title, source)))}",
        source=source, domain="abc.net.au", published=NOW - timedelta(hours=hours_ago),
        summary="", category=category, region="perth",
    )


class GateTests(unittest.TestCase):
    def test_sends_after_send_time_once_per_day(self):
        c = cfg()
        self.assertTrue(should_send(c, {}, NOW)[0])
        self.assertFalse(should_send(c, {"last_sent_local_date": "2026-09-25"}, NOW)[0])

    def test_too_early(self):
        early = datetime(2026, 9, 24, 18, 30, tzinfo=UTC)  # 2:30am Perth
        self.assertFalse(should_send(cfg(), {}, early)[0])

    def test_skips_days_not_listed(self):
        c = cfg()
        c["schedule"]["send_days"] = ["sun"]
        self.assertFalse(should_send(c, {}, NOW)[0])
        self.assertTrue(should_send(c, {}, NOW, force=True)[0])

    def test_late_github_run_still_sends(self):
        late = datetime(2026, 9, 25, 1, 0, tzinfo=UTC)  # 9am Perth
        self.assertTrue(should_send(cfg(), {"last_sent_local_date": "2026-09-24"}, late)[0])


class TextTests(unittest.TestCase):
    def test_headline_cleanup(self):
        self.assertEqual(clean_headline("Big news - ABC News", "ABC News"), "Big news")
        self.assertEqual(clean_headline("Big news - Some Outlet"), "Big news")

    def test_similar_headlines(self):
        a = tokens("Perth rail line to close for six weeks from October")
        b = tokens("Six week closure for Perth rail line announced")
        c = tokens("CSIRO finds new coral species off Ningaloo")
        self.assertGreater(similarity(a, b), 0.3)
        self.assertEqual(similarity(a, c), 0.0)

    def test_filters(self):
        self.assertTrue(is_opinion_title("Opinion: rates must fall"))
        self.assertTrue(is_opinion_title("Why the budget fails | Comment"))
        self.assertFalse(is_opinion_title("RBA holds rates at 3.6 per cent"))
        self.assertTrue(is_opinion_url("https://www.smh.com.au/opinion/why-2026.html"))
        self.assertFalse(is_opinion_url("https://www.abc.net.au/news/live-export-ban-passes/123"))
        self.assertTrue(is_blocked("www.theaustralian.com.au".removeprefix("www."), ["theaustralian.com.au"]))
        self.assertTrue(is_blocked("amp.afr.com", ["afr.com"]))


class NewFilterTests(unittest.TestCase):
    def test_excluded_words_whole_word_only(self):
        from newsdigest.filters import excluded_word
        words = cfg()["sources"]["exclude_headline_words"]
        self.assertEqual(excluded_word("Talking points for today's AFL grand final", words), "AFL")
        self.assertEqual(excluded_word("Crash closes A9 in the Highlands of Scotland", words), "Scotland")
        self.assertIsNone(excluded_word("Wafl ruling hits council budget", ["AFL"]))
        self.assertIsNone(excluded_word("RBA holds cash rate at 3.6 per cent", words))

    def test_gemini_successor_from_error_message(self):
        msg = ('HTTP 404: "This model models/gemini-2.5-flash is no longer available to new users. '
               'Please update your code to use models/gemini-3.8-flash for the latest"')
        self.assertEqual(ai.replacement_gemini_model(msg, "gemini-2.5-flash"), "gemini-3.8-flash")

    def test_gemini_switches_model_on_404(self):
        calls = []

        def fake_post(url, headers, body):
            calls.append(url)
            if "gemini-old" in url:
                raise ai.ProviderError("HTTP 404: use models/gemini-9-flash instead")
            return {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}

        c = cfg()
        c["ai"]["gemini_model"] = "gemini-old"
        with mock.patch.object(ai, "_post_json", fake_post), mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}):
            self.assertEqual(ai.call_gemini(c, "prompt"), "{}")
        self.assertEqual(c["ai"]["gemini_model"], "gemini-9-flash")
        self.assertIn("gemini-9-flash", calls[-1])


class CollectTests(unittest.TestCase):
    def test_parse_google_news_feed(self):
        items = collect.parse_feed(SAMPLE_RSS, "perth", "perth")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "Perth rail line to close for six weeks")
        self.assertEqual(items[0].source, "ABC News")
        self.assertEqual(items[0].domain, "abc.net.au")
        self.assertEqual(items[0].summary, "")

    def test_feed_plan_uses_australian_edition(self):
        c = cfg()
        plan = collect.feed_plan(c, settings.enabled_categories(c), 30)
        self.assertTrue(any("when%3A2d" in url and "ceid=AU:en" in url for url, _, _ in plan))

    def test_screen_removes_opinion_and_old(self):
        items = collect.parse_feed(SAMPLE_RSS, "perth", "perth")
        items.append(item("Old story about Perth council budget", hours_ago=80))
        kept = cluster.screen(items, NOW - timedelta(hours=30), [], set())
        self.assertEqual([i.title for i in kept], ["Perth rail line to close for six weeks"])


class ClusterTests(unittest.TestCase):
    def test_groups_same_event_and_ranks_by_outlets(self):
        c = cfg()
        cats = settings.enabled_categories(c)
        items = [
            item("Perth rail line to close for six weeks", "ABC News"),
            item("Six week closure of Perth rail line confirmed", "WAtoday"),
            item("Perth rail line closure: six weeks of buses", "PerthNow"),
            item("CSIRO discovers coral species off Ningaloo reef", "ABC News", category="science"),
        ]
        stories = cluster.build_stories(items, c, cats, NOW)
        self.assertEqual(len(stories), 2)
        self.assertEqual(len(stories[0].items), 3)

    def test_zero_region_weight_hides(self):
        c = cfg()
        c["regions"]["perth"] = 0
        stories = cluster.build_stories([item("Perth rail line to close for six weeks")], c, settings.enabled_categories(c), NOW)
        self.assertEqual(stories, [])


class AITests(unittest.TestCase):
    def test_parse_and_apply(self):
        c = cfg()
        cats = settings.enabled_categories(c)
        reply = '```json\n{"stories":[{"id":"s1","is_opinion":false,"headline":"Rail line shut","facts":["A.","B."],"key_numbers":["6 weeks"],"why_it_matters":"Commuters affected.","category":"perth","region":"perth","importance":"4","debate":{"question":"Q?","sides":[{"side":"Labor","position":"P","evidence":"E"}]}}]}\n```'
        results = ai.parse_reply(reply)
        story = cluster.build_stories([item("Perth rail line to close for six weeks")], c, cats, NOW)[0]
        ai.apply_result(story, results["s1"], cats)
        self.assertEqual(story.facts, "A. B.")
        self.assertEqual(story.importance, 4)
        self.assertEqual(story.debate["sides"][0]["side"], "Labor")

    def test_no_keys_means_no_provider(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": ""}):
            self.assertEqual(ai.available_providers(cfg()), [])
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "k"}):
            self.assertEqual(ai.available_providers(cfg()), ["groq"])


def fake_ai_reply(update_ids=()):
    def reply(provider_cfg, prompt):
        ids = [line.split()[2] for line in prompt.splitlines() if line.startswith("=== STORY")]
        stories = []
        for sid in ids:
            stories.append({
                "id": sid, "is_opinion": False, "headline": f"Headline {sid}", "facts": f"Facts for {sid}.",
                "key_numbers": [], "why_it_matters": "It matters.", "category": "perth", "region": "perth",
                "importance": 3, "has_new_facts": sid in update_ids, "update_summary": "New detail." if sid in update_ids else "",
                "debate": None,
            })
        return json.dumps({"stories": stories})
    return reply


class PipelineTests(unittest.TestCase):
    """Runs the full line twice with the network replaced by fakes."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        patches = [
            mock.patch.object(settings, "STATE_PATH", self.tmp / "state.json"),
            mock.patch.object(settings, "HISTORY_PATH", self.tmp / "history.json"),
            mock.patch.object(main, "DOCS_DIR", self.tmp / "docs"),
            mock.patch.object(main, "ROOT", self.tmp),
            mock.patch.object(extract, "resolve_links", lambda links: {l: l.replace("news.google.com", "example.com") for l in links}),
            mock.patch.object(extract, "fetch_text", lambda url: "word " * 200),
            mock.patch.object(ai, "CALLERS", {"gemini": fake_ai_reply(), "groq": fake_ai_reply()}),
            mock.patch.object(ai.time, "sleep", lambda s: None),
            mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test", "GITHUB_REPOSITORY": "someone/NewsSummarizer"}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.sent = []
        emailer = mock.patch("newsdigest.emailer.send_email", lambda *a: self.sent.append(a))
        emailer.start()
        self.addCleanup(emailer.stop)

    def run_with(self, items, now):
        with mock.patch.object(collect, "collect", lambda *a: list(items)):
            main.run(now=now)

    def test_two_days(self):
        day1 = [
            item("Perth rail line to close for six weeks", "ABC News", link="https://news.google.com/a1"),
            item("Six week closure of Perth rail line confirmed", "WAtoday", link="https://news.google.com/a2"),
            item("CSIRO discovers coral species off Ningaloo reef", "ABC News", category="science", link="https://news.google.com/b1"),
        ]
        self.run_with(day1, NOW)
        self.assertEqual(len(self.sent), 1)
        subject, html, text = self.sent[0]
        self.assertIn("2 stories", subject)
        self.assertIn("Facts for", html)
        self.assertIn("someone.github.io/NewsSummarizer", html)
        history = json.loads((self.tmp / "history.json").read_text())
        self.assertEqual(len(history), 2)
        index = json.loads((self.tmp / "docs/data/index.json").read_text())
        self.assertEqual(len(index["digests"]), 1)

        # Day two: same links again (must be skipped), plus a follow up on the rail story.
        day2_now = NOW + timedelta(days=1)
        day2 = day1 + [item("Perth rail line closure extended to eight weeks", "PerthNow", link="https://news.google.com/a3")]
        for i in day2:
            i.published = day2_now - timedelta(hours=3)
        with mock.patch.object(ai, "CALLERS", {"gemini": fake_ai_reply(update_ids={"s1"})}):
            self.run_with(day2, day2_now)
        subject, html, text = self.sent[1]
        self.assertIn("1 story", subject)
        self.assertIn("UPDATE", text)
        self.assertIn("What is new", html)
        self.assertIn("Original story, sent on", html)
        history = json.loads((self.tmp / "history.json").read_text())
        self.assertEqual(len(history), 2, "an update replaces its original entry")

    def test_update_without_new_facts_is_dropped(self):
        self.run_with([item("Perth rail line to close for six weeks", link="https://news.google.com/a1")], NOW)
        later = NOW + timedelta(days=1)
        repeat = item("Perth rail line closure for six weeks begins", "WAtoday", link="https://news.google.com/a9")
        repeat.published = later - timedelta(hours=2)
        self.run_with([repeat], later)
        self.assertIn("0 stories", self.sent[1][0])

    def test_preview_publishes_without_email_or_memory(self):
        items = [
            item("Perth rail line to close for six weeks", link="https://news.google.com/a1"),
            item("Opinion: the rail closure is a disaster", "WAtoday", link="https://news.google.com/a2"),
        ]
        with mock.patch.object(collect, "collect", lambda *a: list(items)):
            main.run(preview=True, now=NOW)
        self.assertEqual(self.sent, [])
        self.assertFalse((self.tmp / "history.json").exists())
        self.assertFalse((self.tmp / "state.json").exists())
        index = json.loads((self.tmp / "docs/data/index.json").read_text())
        self.assertEqual(index["digests"], [])
        preview = json.loads((self.tmp / "docs/data" / index["preview"]["file"]).read_text())
        self.assertTrue(preview["preview"])
        self.assertTrue(preview["stories"][0]["in_email"])
        diag = preview["diagnostics"]
        self.assertIn(["Stories in the email", 1], diag["funnel"])
        self.assertIn("opinion by headline", [d["reason"] for d in diag["dropped"]])

    def test_preview_with_every_feed_failing_still_reports(self):
        with mock.patch.object(collect, "collect", lambda *a: []):
            main.run(preview=True, now=NOW)
            with self.assertRaises(SystemExit):
                main.run(preview=False, now=NOW)
        self.assertEqual(self.sent, [])

    def test_sport_dropped_by_ai_kind(self):
        def reply(provider_cfg, prompt):
            data = json.loads(fake_ai_reply()(provider_cfg, prompt))
            data["stories"][0]["kind"] = "sport"
            return json.dumps(data)

        with mock.patch.object(ai, "CALLERS", {"gemini": reply}):
            self.run_with([item("Perth Heat win baseball series opener at home")], NOW)
        self.assertIn("0 stories", self.sent[0][0])

    def test_ai_failure_is_announced(self):
        def broken(provider_cfg, prompt):
            raise ai.ProviderError("HTTP 404: model gone")

        with mock.patch.object(ai, "CALLERS", {"gemini": broken}):
            self.run_with([item("Perth rail line to close for six weeks")], NOW)
        self.assertIn("could not summarise 1 of 1", self.sent[0][1])
        self.assertIn("NOTE:", self.sent[0][2])

    def test_headlines_only_without_ai_key(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            self.run_with([item("Perth rail line to close for six weeks")], NOW)
        self.assertIn("Headline only", self.sent[0][1])


class RenderTests(unittest.TestCase):
    def test_escapes_html(self):
        c = cfg()
        cats = settings.enabled_categories(c)
        story = cluster.build_stories([item("Perth <script> rail line closes for weeks")], c, cats, NOW)[0]
        story.articles.append(Article("ABC News", "https://abc.net.au/x", "text"))
        d = render.story_to_dict(story, cats, True)
        self.assertNotIn("<script>", render.story_html(d))


if __name__ == "__main__":
    unittest.main()
