"""Station one: gather headlines from Google News RSS and direct outlet feeds."""

import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote_plus

import feedparser
import requests

from .models import Item
from .textutil import clean_headline, domain_of, strip_html

GOOGLE_NEWS = "https://news.google.com/rss"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)


def edition_params(cfg):
    lang = cfg["digest"]["language"]
    country = cfg["digest"]["country"]
    return f"hl={lang}&gl={country}&ceid={country}:{lang.split('-')[0]}"


def feed_plan(cfg, categories, lookback_hours):
    """List of (url, category key, region) to fetch."""
    params = edition_params(cfg)
    days = max(1, math.ceil(lookback_hours / 24))
    plan = []
    for key, cat in categories.items():
        for topic in cat["google_news_topics"]:
            plan.append((f"{GOOGLE_NEWS}/headlines/section/topic/{topic.upper()}?{params}", key, cat["region"]))
        for query in cat["google_news_searches"]:
            q = quote_plus(f"{query} when:{days}d")
            plan.append((f"{GOOGLE_NEWS}/search?q={q}&{params}", key, cat["region"]))
        for url in cat["feeds"]:
            plan.append((url, key, cat["region"]))
    return plan


def _entry_time(entry):
    for attr in ("published_parsed", "updated_parsed"):
        value = entry.get(attr)
        if value:
            return datetime(*value[:6], tzinfo=timezone.utc)
    return None


def parse_feed(content, category, region):
    parsed = feedparser.parse(content)
    feed_title = strip_html(parsed.feed.get("title", ""))
    items = []
    for entry in parsed.entries:
        link = entry.get("link", "")
        if not link:
            continue
        src = entry.get("source") or {}
        source = strip_html(src.get("title", "")) or feed_title or domain_of(link)
        domain = domain_of(src.get("href", "")) or domain_of(link)
        title = clean_headline(entry.get("title", ""), source)
        summary = strip_html(entry.get("summary", ""))
        # Google News summaries just repeat the headline and outlet name.
        if summary.startswith(title[:40]) or "news.google.com" in link:
            summary = ""
        items.append(Item(
            title=title, link=link, source=source, domain=domain,
            published=_entry_time(entry), summary=summary[:600],
            category=category, region=region,
        ))
    return items


def fetch_feed(url, category, region):
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  feed failed: {url[:90]} ({exc})")
        return []
    return parse_feed(resp.content, category, region)


def collect(cfg, categories, lookback_hours):
    plan = feed_plan(cfg, categories, lookback_hours)
    print(f"Collecting from {len(plan)} feeds")
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda p: fetch_feed(*p), plan))
    items = [item for batch in results for item in batch]
    print(f"  {len(items)} headlines collected")
    return items
