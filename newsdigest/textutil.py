"""Small text helpers: keyword sets, headline similarity, HTML stripping."""

import html
import re
from urllib.parse import urlparse

STOPWORDS = set("""
a about after again against all also an and any are as at be been before being
but by can could did do does during for from had has have he her here his how
if in into is it its just more most new news no not now of off on once only or
other our out over own said says same she should so some such than that the
their them then there these they this those through to too under until up very
was we were what when where which while who why will with would you your year
years week today yesterday live update updates latest report reports first
""".split())

SHORT_KEEP = {"wa", "us", "uk", "eu", "ai", "nt", "sa", "un", "ev"}
WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def tokens(text):
    """Keyword set for comparing headlines. Crude stemming on purpose."""
    out = set()
    for word in WORD_RE.findall(text.lower()):
        if word.endswith("'s"):
            word = word[:-2]
        word = word.replace("'", "")
        if word in STOPWORDS:
            continue
        if len(word) < 3 and word not in SHORT_KEEP and not word.isdigit():
            continue
        if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        out.add(word)
    return out


def similarity(a, b):
    """Jaccard overlap of two keyword sets, requiring at least two shared words."""
    if not a or not b:
        return 0.0
    shared = len(a & b)
    if shared < 2:
        return 0.0
    return shared / len(a | b)


def best_similarity(token_sets_a, token_sets_b):
    return max((similarity(a, b) for a in token_sets_a for b in token_sets_b), default=0.0)


def strip_html(text):
    return SPACE_RE.sub(" ", html.unescape(TAG_RE.sub(" ", text or ""))).strip()


def domain_of(url):
    host = urlparse(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def clean_headline(title, source=""):
    """Google News appends ' - Outlet Name' to titles. Remove it."""
    title = strip_html(title)
    if source and title.endswith(" - " + source):
        return title[: -len(source) - 3].strip()
    head, sep, tail = title.rpartition(" - ")
    if sep and head and len(tail) <= 40:
        return head.strip()
    return title
