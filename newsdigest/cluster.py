"""Stations two and three: screen headlines, group them into events, rank them."""

import math
from collections import Counter
from datetime import datetime, timedelta, timezone

from .diagnostics import report
from .filters import is_blocked, is_opinion_title
from .models import Story
from .textutil import best_similarity, tokens


def screen(items, since, blocked, seen_links):
    """Drop old, already sent, blocked and obviously opinion headlines."""
    kept, seen = [], set()
    counts = Counter()
    for item in items:
        if item.link in seen:
            reason = "duplicate feed entry"
        elif item.link in seen_links:
            reason = "already sent"
        elif item.published and item.published < since:
            reason = "too old"
        elif is_blocked(item.domain, blocked):
            reason = "blocked outlet"
        elif is_opinion_title(item.title):
            reason = "opinion by headline"
        elif len(tokens(item.title)) < 3:
            reason = "headline too short"
        else:
            kept.append(item)
            seen.add(item.link)
            continue
        counts[reason] += 1
        # Old, duplicate and sent items are too numerous to list one by one.
        if reason in ("blocked outlet", "opinion by headline", "headline too short"):
            report.drop(item.title, item.source, reason)
    summary = ", ".join(f"{n} {why}" for why, n in counts.items()) or "nothing"
    print(f"Screen kept {len(kept)} headlines (removed {summary})")
    report.stage(f"Headlines left after screening (removed {summary})", len(kept))
    return kept


def group(items, threshold):
    """Greedy clustering: each headline joins the most similar existing event."""
    ordered = sorted(items, key=lambda i: i.published or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    groups = []  # list of (member token sets, member items)
    for item in ordered:
        toks = tokens(item.title)
        best, best_score = None, 0.0
        for g in groups:
            score = best_similarity([toks], g[0])
            if score > best_score:
                best, best_score = g, score
        if best is not None and best_score >= threshold:
            best[0].append(toks)
            best[1].append(item)
        else:
            groups.append(([toks], [item]))
    return [members for _, members in groups]


def _category_for(members, categories):
    counts = Counter(i.category for i in members)
    return max(counts, key=lambda k: (counts[k], categories[k]["weight"]))


def region_weight(cfg, region):
    return float(cfg["regions"].get(region, 1.0))


def base_score(story, cfg, categories, now):
    outlets = len({i.source for i in story.items})
    outlet_factor = 1.0 + 1.2 * math.log(outlets)
    published = story.published
    freshness = 1.0 if published and now - published < timedelta(hours=24) else 0.8
    return outlet_factor * categories[story.category]["weight"] * region_weight(cfg, story.region) * freshness


def build_stories(items, cfg, categories, now):
    stories = []
    for n, members in enumerate(group(items, cfg["digest"]["similarity_threshold"]), start=1):
        category = _category_for(members, categories)
        story = Story(id=f"s{n}", items=members, category=category, region=categories[category]["region"])
        story.score = base_score(story, cfg, categories, now)
        if story.score > 0:
            stories.append(story)
    stories.sort(key=lambda s: s.score, reverse=True)
    print(f"Grouped into {len(stories)} distinct events")
    report.stage("Distinct events after grouping headlines", len(stories))
    return stories


def match_history(stories, history, threshold):
    """Attach the previously sent version to any story we have sent before."""
    past = [(entry, [tokens(t) for t in entry.get("titles", [])]) for entry in history]
    for story in stories:
        mine = [tokens(t) for t in story.titles]
        best, best_score = None, 0.0
        for entry, toks in past:
            score = best_similarity(mine, toks)
            if score > best_score:
                best, best_score = entry, score
        if best is not None and best_score >= threshold:
            story.previous = best
            story.is_update = True


def final_score(story, cfg, categories, now):
    importance_factor = 0.4 + 0.2 * story.importance  # 1 gives 0.6, 5 gives 1.4
    return base_score(story, cfg, categories, now) * importance_factor
