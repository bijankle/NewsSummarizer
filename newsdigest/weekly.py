"""On demand "week in review", started from the app's Week in review button.

python -m newsdigest.weekly

Reads the stories already published over the last 7 days (no new downloads) and asks
the AI for a one page review grouped by topic. Writes docs/data/weekly/<date>.json and
lists it in docs/data/weekly/index.json.
"""

import argparse
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import ai
from .settings import DOCS_DIR, load_config

DAYS = 7
KEEP = 26  # about six months of weekly reviews

SYSTEM = """You write a one page "week in review" for a reader in Perth, Western Australia who wants facts, numbers and consequences, with no opinion or filler.
You are given the week's published news summaries. Use only what they state.
Group the week into at most six topics that matter most to this reader. Within each topic give two to five points, most important first.
Each point is one or two plain sentences stating what happened and, where a story developed during the week, how it progressed.
Include the key figures. Mention a disagreement only if the summaries report one, naming each side.
Finish with "big_picture": two or three sentences on the most significant developments of the week and their concrete consequences.
Write in Australian English with plain sentences, using commas and full stops rather than dashes.
Respond with JSON only, shaped as:
{"sections": [{"topic": "...", "points": ["..."]}], "big_picture": "..."}"""


def week_stories(now):
    data_dir = DOCS_DIR / "data"
    index = json.loads((data_dir / "index.json").read_text(encoding="utf-8"))
    cutoff = now - timedelta(days=DAYS)
    stories, seen = [], set()
    for entry in index.get("digests", []):
        try:
            generated = datetime.fromisoformat(entry["generated"])
        except (KeyError, ValueError):
            continue
        if generated < cutoff:
            continue
        edition = json.loads((data_dir / entry["file"]).read_text(encoding="utf-8"))
        for s in edition.get("stories", []):
            if s.get("processed") and s.get("headline") not in seen:
                seen.add(s.get("headline"))
                stories.append(s)
    return stories


def story_line(s):
    parts = [f"[{s.get('category_label', '')}, {s.get('region', '')}, importance {s.get('importance', 3)}] {s.get('headline', '')}."]
    if s.get("update_summary"):
        parts.append(f"New: {s['update_summary']}")
    parts.append(s.get("facts", ""))
    if s.get("key_numbers"):
        parts.append("Numbers: " + "; ".join(s["key_numbers"]))
    return " ".join(p for p in parts if p)


def run(now=None):
    now = now or datetime.now(timezone.utc)
    cfg = load_config()
    local = now.astimezone(ZoneInfo(cfg["schedule"]["timezone"]))
    stories = week_stories(now)
    if not stories:
        raise SystemExit("No summarised stories were published in the last 7 days")
    stories.sort(key=lambda s: -int(s.get("importance", 3)))
    prompt = f"This week's {len(stories)} news summaries, most important first:\n\n" + "\n\n".join(story_line(s) for s in stories)
    result = ai.ask(cfg, prompt[:120000], SYSTEM)
    sections = [
        {"topic": str(sec.get("topic", "")).strip(), "points": [str(p).strip() for p in sec.get("points") or [] if str(p).strip()]}
        for sec in result.get("sections") or [] if isinstance(sec, dict)
    ]
    start = (local - timedelta(days=DAYS - 1)).date()
    review = {
        "generated": local.isoformat(timespec="minutes"),
        "label": f"Week of {start.day} {start:%B} to {local.day} {local:%B %Y}",
        "stories_used": len(stories),
        "sections": [s for s in sections if s["topic"] and s["points"]],
        "big_picture": str(result.get("big_picture", "")).strip(),
    }
    out_dir = DOCS_DIR / "data" / "weekly"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{local:%Y-%m-%d-%H%M}.json"
    (out_dir / name).write_text(json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")
    index_path = out_dir / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        index = {"reviews": []}
    entries = [{"file": name, "label": review["label"], "generated": review["generated"]}] + [
        e for e in index["reviews"] if e["file"] != name]
    for old in entries[KEEP:]:
        (out_dir / old["file"]).unlink(missing_ok=True)
    index_path.write_text(json.dumps({"reviews": entries[:KEEP]}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Week in review written from {len(stories)} stories: {review['label']}")
    return review


def main():
    argparse.ArgumentParser(description="Write the week in review from the last 7 days of stories.").parse_args()
    run()


if __name__ == "__main__":
    main()
