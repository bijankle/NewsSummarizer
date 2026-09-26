"""Station one: gather headlines from Google News RSS and direct outlet feeds."""

import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote_plus

import feedparser
import requests

from .diagnostics import report
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
        domain = domain_of(src.get("href", "")) or domain_of(link)
        source = strip_html(src.get("title", "")) or outlet_name(domain, feed_title or domain)
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


# Direct feeds name themselves oddly ("Just In", "Ars Technica - All content").
OUTLET_NAMES = {
    "abc.net.au": "ABC News", "sbs.com.au": "SBS News", "watoday.com.au": "WAtoday",
    "rba.gov.au": "Reserve Bank of Australia", "sciencedaily.com": "ScienceDaily",
    "newatlas.com": "New Atlas", "theregister.com": "The Register", "arstechnica.com": "Ars Technica",
    "spectrum.ieee.org": "IEEE Spectrum", "perthnow.com.au": "PerthNow", "thewest.com.au": "The West Australian",
}


def outlet_name(domain, fallback):
    for known, name in OUTLET_NAMES.items():
        if domain == known or domain.endswith("." + known):
            return name
    return fallback


RETRY_STATUS = {429, 500, 502, 503, 504}
RETRY_WAITS = (5, 15)     # seconds before the second and third attempts
GOOGLE_SPACING = 2.0      # seconds between Google News requests


def fetch_feed(url, category, region):
    error = ""
    for attempt in range(len(RETRY_WAITS) + 1):
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
            if resp.status_code not in RETRY_STATUS:
                resp.raise_for_status()
                return parse_feed(resp.content, category, region)
            error = f"HTTP {resp.status_code} (busy or rate limited)"
        except requests.RequestException as exc:
            error = str(exc)
            if getattr(exc, "response", None) is not None and exc.response.status_code not in RETRY_STATUS:
                break  # a 404 or similar will not fix itself
        if attempt < len(RETRY_WAITS):
            time.sleep(RETRY_WAITS[attempt])
    print(f"  feed failed: {url[:90]} ({error})")
    report.feed_failures.append({"url": url, "error": error[:200]})
    return []


def collect(cfg, categories, lookback_hours):
    """Direct outlet feeds are fetched in parallel. Google News feeds go one at a
    time with a pause between them, because Google answers "503 busy" to a burst
    of simultaneous requests from GitHub's servers."""
    plan = feed_plan(cfg, categories, lookback_hours)
    google = [p for p in plan if p[0].startswith(GOOGLE_NEWS)]
    direct = [p for p in plan if not p[0].startswith(GOOGLE_NEWS)]
    print(f"Collecting from {len(plan)} feeds ({len(google)} Google News, {len(direct)} direct)")
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        direct_results = pool.map(lambda p: fetch_feed(*p), direct)
        for n, p in enumerate(google):
            if n:
                time.sleep(GOOGLE_SPACING)
            results.append(fetch_feed(*p))
        results.extend(direct_results)
    items = [item for batch in results for item in batch]
    print(f"  {len(items)} headlines collected")
    report.stage(f"Headlines collected from {len(plan) - len(report.feed_failures)} of {len(plan)} feeds", len(items))
    return items
