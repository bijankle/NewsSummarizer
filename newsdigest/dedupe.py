"""One AI request that catches duplicates the word and meaning checks miss.

It sees the top candidate events (by their headlines) and the headlines published
over the last week, then reports:
  same:      candidate events that cover one news event, including its immediate
             follow on reports (a rate decision and banks passing it on), to merge;
  follow_up: candidate events that continue a story already published, so they are
             handled as possible updates rather than new stories.
"""

from datetime import date, timedelta

from . import ai
from .diagnostics import report

SYSTEM = """You sort news headlines for a daily briefing so the reader never sees the same news twice.
You get numbered candidate events (E numbers), each with one or more headlines from different outlets, and numbered headlines already published (P numbers).
1. "same": groups of E numbers that report the same specific news event, including its immediate follow on reports, for example a central bank rate decision and banks passing that rate change on, or a crash and the police update about that crash. Do not group different events that only share a topic, such as two separate court cases or two different interest rate stories in different countries.
2. "follow_up": for each E number that continues a story in the P list (same specific event, a development of it, or its direct consequence), the matching P number.
Only list confident matches. Respond with JSON only, shaped as:
{"same": [["E1", "E7"]], "follow_up": [{"event": "E3", "previous": "P12"}]}"""

MAX_EVENTS = 80
RECENT_DAYS = 7
TITLES_PER_EVENT = 3


def find_duplicates(stories, history, cfg, today=None):
    """Merge duplicate candidates in place and attach previous versions. Returns the new list."""
    if len(stories) < 2 and not history:
        return stories
    events = stories[:MAX_EVENTS]
    rest = stories[MAX_EVENTS:]
    cutoff = ((today or date.today()) - timedelta(days=RECENT_DAYS)).isoformat()
    recent = [h for h in history if h.get("date", "") >= cutoff and h.get("headline")]
    lines = ["CANDIDATE EVENTS"]
    for n, s in enumerate(events, start=1):
        titles = list(dict.fromkeys(s.titles))[:TITLES_PER_EVENT]
        lines.append(f"E{n}: " + " | ".join(titles))
    if recent:
        lines.append("\nALREADY PUBLISHED")
        lines += [f"P{n}: {h['headline']}" for n, h in enumerate(recent, start=1)]
    try:
        result = ai.ask(cfg, "\n".join(lines), SYSTEM, minutes=4)
    except ai.ProviderError as exc:
        report.ai_notes.append(f"Duplicate check skipped ({str(exc)[:120]}).")
        return stories

    def event(ref):
        try:
            k = int(str(ref).strip().upper().lstrip("E")) - 1
        except ValueError:
            return None
        return k if 0 <= k < len(events) else None

    merged_away = set()
    merges = 0
    for group in result.get("same") or []:
        ks = sorted({k for k in (event(r) for r in group if isinstance(group, list)) if k is not None} - merged_away)
        if len(ks) < 2:
            continue
        # Keep the best ranked event (lowest index, list is sorted by score) and fold the others in.
        primary = events[ks[0]]
        for k in ks[1:]:
            primary.items.extend(events[k].items)
            if events[k].previous and not primary.previous:
                primary.previous, primary.is_update = events[k].previous, True
            merged_away.add(k)
            merges += 1

    follow_ups = 0
    for f in result.get("follow_up") or []:
        if not isinstance(f, dict):
            continue
        k = event(f.get("event"))
        try:
            p = int(str(f.get("previous", "")).strip().upper().lstrip("P")) - 1
        except ValueError:
            continue
        if k is None or k in merged_away or not 0 <= p < len(recent):
            continue
        if not events[k].previous:
            events[k].previous, events[k].is_update = recent[p], True
            follow_ups += 1

    report.ai_notes.append(f"Duplicate check: merged {merges} duplicate events, found {follow_ups} follow ups to published stories.")
    return [s for k, s in enumerate(events) if k not in merged_away] + rest
