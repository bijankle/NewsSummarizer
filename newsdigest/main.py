"""Runs the whole production line once: collect, screen, group, extract, summarise, send, publish.

python -m newsdigest              build, email, publish the web page and save memory
python -m newsdigest --preview    build only, write output/preview.html, send and save nothing
"""

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import ai, cluster, collect, extract, render
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

    items = collect.collect(cfg, categories, hours)
    if not items:
        # Every feed failed. Fail the run so the next hourly check retries.
        raise SystemExit("No headlines could be collected from any feed")
    seen_links = {link for entry in history for link in entry.get("links", [])}
    items = cluster.screen(items, since, cfg["sources"]["blocked"], seen_links)
    stories = cluster.build_stories(items, cfg, categories, now)
    cluster.match_history(stories, history, d["similarity_threshold"])

    use_ai = bool(ai.available_providers(cfg))
    if not (use_ai and d["show_updates"]):
        stories = [s for s in stories if not s.previous]
    # Process a few extra, because some turn out to be opinion or old news.
    web_count = int(d["web_story_count"])
    candidates = stories[: web_count + max(5, web_count // 4)]

    extract.extract_stories(candidates, cfg)
    candidates = [s for s in candidates if not s.is_opinion]
    ai.summarise(candidates, cfg, categories)

    kept = []
    for story in candidates:
        if story.is_opinion or (story.previous and not story.has_new_facts):
            continue
        if cluster.region_weight(cfg, story.region) <= 0:
            continue
        if story.processed:
            story.score = cluster.final_score(story, cfg, categories, now)
        kept.append(story)
    kept.sort(key=lambda s: s.score, reverse=True)
    kept = kept[:web_count]
    email_count = int(d["email_story_count"])
    dicts = [render.story_to_dict(s, categories, n < email_count) for n, s in enumerate(kept)]
    print(f"Digest: {min(email_count, len(dicts))} stories for email, {len(dicts)} for the web page")
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


def publish(day_stamp, local, dicts, debates, web_url, settings_url):
    data_dir = DOCS_DIR / "data"
    digest_dir = data_dir / "digests"
    digest_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": local.isoformat(timespec="minutes"),
        "label": render.long_date(local.date()),
        "settings_url": settings_url,
        "stories": dicts,
        "debates": debates,
    }
    (digest_dir / f"{day_stamp}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    index_path = data_dir / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        index = {"digests": []}
    entries = [e for e in index["digests"] if e["file"] != f"{day_stamp}.json"]
    entries.insert(0, {"file": f"{day_stamp}.json", "label": payload["label"], "stories": len(dicts)})
    for old in entries[KEEP_DIGESTS:]:
        (digest_dir / old["file"]).unlink(missing_ok=True)
    index = {"digests": entries[:KEEP_DIGESTS], "settings_url": settings_url, "web_url": web_url}
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Web page data written for {payload['label']}")


def run(preview=False, now=None):
    now = now or datetime.now(timezone.utc)
    cfg = load_config()
    state, history = load_state(), load_history()
    local = now.astimezone(ZoneInfo(cfg["schedule"]["timezone"]))

    stories, dicts, _ = build(cfg, state, history, now)
    email_dicts = [s for s in dicts if s["in_email"]]
    show_debates = cfg["digest"]["debates_section"]
    email_debates = render.collect_debates(email_dicts) if show_debates else []
    web_debates = render.collect_debates(dicts) if show_debates else []
    web_url, settings_url = repo_urls(cfg)
    html = render.email_html(local.date(), email_dicts, email_debates, web_url, settings_url)
    text = render.email_text(local.date(), email_dicts, email_debates, web_url)
    n = len(email_dicts)
    subject = f"News Digest, {local:%a} {local.day} {local:%b}: {n} {'story' if n == 1 else 'stories'}"

    out_dir = ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "preview.html").write_text(html, encoding="utf-8")
    (out_dir / "preview.txt").write_text(text, encoding="utf-8")
    if preview:
        print(f"Preview only: see {out_dir / 'preview.html'}")
        return

    from .emailer import send_email

    send_email(subject, html, text)
    publish(f"{local:%Y-%m-%d-%H%M}", local, dicts, web_debates, web_url, settings_url)
    save_history(remember(history, stories, local.date().isoformat(), cfg, now))
    save_state({"last_sent_utc": now.isoformat(timespec="seconds"), "last_sent_local_date": local.date().isoformat()})


def main():
    parser = argparse.ArgumentParser(description="Build and send the news digest.")
    parser.add_argument("--preview", action="store_true", help="build only, do not email or save anything")
    run(preview=parser.parse_args().preview)


if __name__ == "__main__":
    main()
