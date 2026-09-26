"""Runs the whole production line once: collect, screen, group, extract, summarise, publish.

python -m newsdigest              build, publish to the web page and save the memory of published stories
python -m newsdigest --dry-run    build only, write output/latest.json, change nothing else
"""

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import ai, cluster, collect, extract, render
from .diagnostics import report
from .settings import DOCS_DIR, ROOT, enabled_categories, load_config, load_history, load_state, save_history, save_state

KEEP_DIGESTS = 60


def lookback_start(cfg, state, now):
    d = cfg["digest"]
    earliest = now - timedelta(days=d["max_lookback_days"])
    last = state.get("last_sent_utc")
    if last:
        since = datetime.fromisoformat(last) - timedelta(hours=d["overlap_hours"])
    else:
        since = now - timedelta(hours=d["first_run_lookback_hours"])
    return max(since, earliest)


def repo_urls(cfg):
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    web = cfg["digest"]["web_page_url"].strip()
    settings = ""
    if repo:
        owner, _, name = repo.partition("/")
        web = web or f"https://{owner.lower()}.github.io/{name}/"
        branch = os.environ.get("GITHUB_REF_NAME", "main")
        settings = f"https://github.com/{repo}/edit/{branch}/config.toml"
    return web, settings


def build(cfg, state, history, now):
    categories = enabled_categories(cfg)
    if not categories:
        raise SystemExit("No categories are enabled in config.toml")
    d = cfg["digest"]
    since = lookback_start(cfg, state, now)
    hours = (now - since).total_seconds() / 3600
    print(f"Looking for news from the last {hours:.0f} hours")
    report.lookback_hours = hours

    items = collect.collect(cfg, categories, hours)
    if not items:
        # Every feed failed. Fail the run so the next hourly check retries.
        raise SystemExit("No headlines could be collected from any feed")
    seen_links = {link for entry in history for link in entry.get("links", [])}
    words = list(cfg["sources"]["exclude_headline_words"])
    if "sport" in d["exclude_kinds"]:
        words += cfg["sources"]["sport_headline_words"]
    items = cluster.screen(items, since, cfg["sources"]["blocked"], seen_links, words)
    stories = cluster.build_stories(items, cfg, categories, now)
    cluster.match_history(stories, history, d["similarity_threshold"])

    use_ai = bool(ai.available_providers(cfg))
    if not (use_ai and d["show_updates"]):
        why = "already published (updates are off)" if use_ai else "already published (no AI to check for new facts)"
        for s in stories:
            if s.previous:
                report.drop_story(s, why)
        stories = [s for s in stories if not s.previous]
    # Process a few extra, because some turn out to be opinion or old news.
    web_count = int(d["stories_per_run"])
    candidates = stories[: web_count + max(5, web_count // 4)]
    report.stage("Top events picked for full processing", len(candidates))

    extract.extract_stories(candidates, cfg)
    for s in candidates:
        if s.is_opinion:
            report.drop_story(s, "opinion (every outlet filed it under an opinion web address)")
    candidates = [s for s in candidates if not s.is_opinion]
    ai.summarise(candidates, cfg, categories)

    kept = []
    for story in candidates:
        if story.is_opinion and "opinion" in d["exclude_kinds"]:
            report.drop_story(story, "opinion or not news (AI judgement)")
            continue
        if story.kind in d["exclude_kinds"] and story.kind != "opinion":
            report.drop_story(story, f"{story.kind} (excluded kind, AI judgement)")
            continue
        if story.previous and not story.has_new_facts:
            report.drop_story(story, f"already published on {story.previous.get('date', 'an earlier day')}, no new facts")
            continue
        if cluster.region_weight(cfg, story.region) <= 0:
            report.drop_story(story, f"region {story.region} is set to 0")
            continue
        if story.processed:
            story.score = cluster.final_score(story, cfg, categories, now)
        kept.append(story)
    kept.sort(key=lambda s: s.score, reverse=True)
    report.stage("Stories left after the AI check", len(kept))
    for story in kept[web_count:]:
        report.drop_story(story, f"ranked below the top {web_count}")
    kept = kept[:web_count]
    dicts = [render.story_to_dict(s, categories) for s in kept]
    unprocessed = sum(1 for s in kept if not s.processed)
    if use_ai and kept and unprocessed:
        report.notice = (
            f"The AI could not summarise {unprocessed} of {len(kept)} stories this run, so those show headlines only "
            "and were not checked for opinion or sport. See Run details on the web page for the reason."
        )
    print(f"Publishing {len(dicts)} stories")
    report.stage("Stories published to the web page", len(dicts))
    return kept, dicts, categories


def remember(history, stories, local_date, cfg, now):
    cutoff = (now - timedelta(days=cfg["digest"]["history_days"])).date().isoformat()
    by_id = {}
    for story in stories:
        entry = {
            "date": local_date,
            "headline": story.headline or story.items[0].title,
            "facts": " ".join(x for x in (story.facts, story.update_summary) if x),
            "titles": story.titles[:5],
            "links": story.links,
        }
        if story.previous:
            # Carry the original forward so the story keeps one history entry.
            entry["titles"] = (story.previous.get("titles", []) + entry["titles"])[-8:]
            entry["links"] = story.previous.get("links", []) + entry["links"]
            by_id[id(story.previous)] = entry
        else:
            by_id[id(entry)] = entry
    kept = [by_id.pop(id(e), e) for e in history if e.get("date", "") >= cutoff]
    return kept + list(by_id.values())


def _read_index(path):
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        index = {}
    index.setdefault("digests", [])
    for entry in index["digests"]:
        # Early digests stored bare file names inside digests/.
        if "/" not in entry["file"]:
            entry["file"] = f"digests/{entry['file']}"
    return index


def publish(local, dicts, web_url, settings_url):
    """Write this run's stories as a new edition and list it in index.json."""
    data_dir = DOCS_DIR / "data"
    (data_dir / "digests").mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": local.isoformat(timespec="minutes"),
        "label": render.long_date(local.date()),
        "settings_url": settings_url,
        "stories": dicts,
        "notice": report.notice,
        "diagnostics": report.to_dict(),
    }
    path = f"digests/{local:%Y-%m-%d-%H%M}.json"
    (data_dir / path).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    index_path = data_dir / "index.json"
    index = _read_index(index_path)
    entry = {"file": path, "label": payload["label"], "stories": len(dicts), "generated": payload["generated"]}
    entries = [entry] + [e for e in index["digests"] if e["file"] != path]
    for old in entries[KEEP_DIGESTS:]:
        (data_dir / old["file"]).unlink(missing_ok=True)
    index["digests"] = entries[:KEEP_DIGESTS]
    index.pop("preview", None)
    (data_dir / "preview.json").unlink(missing_ok=True)
    index.update(settings_url=settings_url, web_url=web_url)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Web page data written: {payload['label']}, {len(dicts)} stories")


def write_run_summary(dicts, web_url):
    """Shown on the run's page in the GitHub Actions tab."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(report.markdown(dicts, web_url))


def run(dry_run=False, now=None):
    now = now or datetime.now(timezone.utc)
    report.reset()
    cfg = load_config()
    state, history = load_state(), load_history()
    local = now.astimezone(ZoneInfo(cfg["schedule"]["timezone"]))

    stories, dicts, _ = build(cfg, state, history, now)
    if not cfg["digest"]["debates_section"]:
        for s in dicts:
            s["debate"] = None
    web_url, settings_url = repo_urls(cfg)

    if dry_run:
        out_dir = ROOT / "output"
        out_dir.mkdir(exist_ok=True)
        (out_dir / "latest.json").write_text(json.dumps(dicts, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Dry run, nothing published. Stories saved in {out_dir / 'latest.json'}")
        return

    publish(local, dicts, web_url, settings_url)
    write_run_summary(dicts, web_url)
    save_history(remember(history, stories, local.date().isoformat(), cfg, now))
    save_state({"last_sent_utc": now.isoformat(timespec="seconds"), "last_sent_local_date": local.date().isoformat()})


def main():
    parser = argparse.ArgumentParser(description="Build the news digest and publish it to the web page.")
    parser.add_argument("--dry-run", action="store_true", help="build only, publish and save nothing")
    run(dry_run=parser.parse_args().dry_run)


if __name__ == "__main__":
    main()
