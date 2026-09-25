"""Coarse screen: reject opinion pieces, unusable pages and blocked outlets by rule."""

import re

OPINION_TITLE = re.compile(
    r"^\s*(opinion|comment|commentary|editorial|analysis|letters?|column|op-ed|"
    r"perspective|my view|our view|your say|podcast|watch|live)\s*[:|]"
    r"|[|:]\s*(opinion|comment|editorial|letters?|analysis|podcast)\s*$"
    r"|\bletters to the editor\b|\bop-ed\b",
    re.IGNORECASE,
)

OPINION_URL = re.compile(
    r"/(opinion|opinions|comment|commentary|editorial|editorials|columnists?|"
    r"columns|letters|perspectives?|analysis|blogs?|podcasts?|videos?|live|"
    r"live-updates|quiz|quizzes|puzzles|sponsored|partner-content|advertorial|"
    r"lifestyle|horoscopes?|recipes?)(/|$)",
    re.IGNORECASE,
)


def is_opinion_title(title):
    return bool(OPINION_TITLE.search(title or ""))


def is_opinion_url(url):
    return bool(OPINION_URL.search(url or ""))


def is_blocked(domain, blocked):
    domain = (domain or "").lower()
    return any(domain == b or domain.endswith("." + b) for b in blocked)
