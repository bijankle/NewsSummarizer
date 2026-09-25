"""Station two, part two: turn Google News links into real links, then pull article text."""

from concurrent.futures import ThreadPoolExecutor

import requests
import trafilatura

from .collect import USER_AGENT
from .filters import is_blocked, is_opinion_url
from .models import Article
from .textutil import domain_of

MIN_WORDS = 120          # fewer than this usually means a paywall or a video page
MAX_ITEMS_TRIED = 4      # outlets tried per story before giving up


def resolve_links(links):
    """Map Google News redirect links to the outlet's own address."""
    google = [link for link in links if "news.google.com" in link]
    resolved = {link: link for link in links if link not in google}
    if not google:
        return resolved
    try:
        from googlenewsdecoder import gnewsdecoder

        results = gnewsdecoder(google, interval=None, timeout=15)
        for link, result in zip(google, results):
            if result.get("success") or result.get("status"):
                resolved[link] = result.get("decoded_url")
    except Exception as exc:  # the decoder depends on Google's page layout
        print(f"  link decoder failed ({exc}), falling back to redirects")
    for link in google:
        if not resolved.get(link):
            resolved[link] = _follow_redirect(link)
    return resolved


def _follow_redirect(link):
    try:
        resp = requests.get(link, headers={"User-Agent": USER_AGENT}, timeout=15, allow_redirects=True)
        if "news.google.com" not in resp.url:
            return resp.url
    except requests.RequestException:
        pass
    return None


def fetch_text(url):
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        resp.raise_for_status()
    except requests.RequestException:
        return ""
    text = trafilatura.extract(
        resp.text, url=url, include_comments=False, include_tables=False, favor_precision=True
    ) or ""
    return text if len(text.split()) >= MIN_WORDS else ""


def _candidates(story):
    """One item per outlet, in the order they appear, capped."""
    picked, outlets = [], set()
    for item in story.items:
        if item.source not in outlets:
            outlets.add(item.source)
            picked.append(item)
    return picked[:MAX_ITEMS_TRIED]


def extract_stories(stories, cfg):
    per_story = cfg["digest"]["articles_per_story"]
    blocked = cfg["sources"]["blocked"]
    wanted = [item for story in stories for item in _candidates(story)]
    print(f"Resolving {len(wanted)} article links")
    resolved = resolve_links([item.link for item in wanted])

    def work(story):
        opinion_hits = 0
        for item in _candidates(story):
            if len(story.articles) >= per_story:
                break
            url = resolved.get(item.link)
            item.resolved = url or ""
            if not url or is_blocked(domain_of(url), blocked):
                continue
            if is_opinion_url(url):
                opinion_hits += 1
                continue
            text = fetch_text(url)
            if text:
                story.articles.append(Article(source=item.source, url=url, text=text))
        # Every outlet we could check filed it under opinion: treat as opinion.
        if opinion_hits and not story.articles and opinion_hits == len(_candidates(story)):
            story.is_opinion = True

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(work, stories))
    with_text = sum(1 for s in stories if s.articles)
    print(f"  full text for {with_text} of {len(stories)} stories")
