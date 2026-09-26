"""Runs the whole production line once: collect, screen, group, extract, summarise, send, publish.

python -m newsdigest              build, email, publish the web page and save memory
python -m newsdigest --preview    build only: publish a Preview edition to the web page, no email,
                                  and the memory of sent stories is left untouched
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


def build(cfg, state, history, now, preview=False):
    categories = enabled_categories(cfg)
    if not categories:
        raise SystemExit("No categories are enabled in config.toml")
    d = cfg["digest"]
    since = lookback_start(cfg, state, now)
    hours = (now - since).total_seconds() / 3600
    print(f"Looking for news from the last {hours:.0f} hours")
    report.lookback_hours = hours

    items = collect.collect(cfg, categories, hours)
    if not items and not preview:
        # Every feed failed. Fail the run so the next hourly check retries.
        # A preview carries on, so the failures show up in the run details.
        raise SystemExit("No headlines could be collected from any feed")
    seen_links = {link for entry in history for link in entry.get("links", [])}
    items = cluster.screen(items, since, cfg["sources"]["blocked"], seen_links)
    stories = cluster.build_stories(items, cfg, categories, now)
    cluster.match_history(stories, history, d["similarity_threshold"])

    use_ai = bool(ai.available_providers(cfg))
    if not (use_ai and d["show_updates"]):
        why = "repeat of a story already sent (updates are off)" if use_ai else "repeat of a story already sent (no AI to check for new facts)"
        for s in stories:
            if s.previous:
                report.drop_story(s, why)
        stories = [s for s in stories if not s.previous]
    # Process a few extra, because some turn out to be opinion or old news.
    web_count = int(d["web_story_count"])
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
        if story.is_opinion:
            report.drop_story(story, "opinion or not news (AI judgement)")
            continue
        if story.previous and not story.has_new_facts:
            report.drop_story(story, f"already sent on {story.previous.get('date', 'an earlier day')}, no new facts")
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
    email_count = int(d["email_story_count"])
    dicts = [render.story_to_dict(s, categories, n < email_count) for n, s in enumerate(kept)]
    print(f"Digest: {min(email_count, len(dicts))} stories for email, {len(dicts)} for the web page")
    report.stage("Stories on the web page", len(dicts))
    report.stage("Stories in the email", min(email_count, len(dicts)))
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
    return index


def publish(local, dicts, debates, web_url, settings_url, preview):
    """Write the web page data. A preview replaces the single Preview edition."""
    data_dir = DOCS_DIR / "data"
    digest_dir = data_dir / "digests"
    digest_dir.mkdir(parents=True, exist_ok=True)
    label = render.long_date(local.date())
    if preview:
        label = f"Preview, {local:%a} {local.day} {local:%b} {local:%H:%M}, not emailed"
    payload = {
        "generated": local.isoformat(timespec="minutes"),
        "label": label,
        "preview": preview,
        "settings_url": settings_url,
        "stories": dicts,
        "debates": debates,
        "diagnostics": report.to_dict(),
    }
    path = "preview.json" if preview else f"digests/{local:%Y-%m-%d-%H%M}.json"
    (data_dir / path).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    index_path = data_dir / "index.json"
    index = _read_index(index_path)
    entry = {"file": path, "label": label, "stories": len(dicts), "generated": payload["generated"]}
    if preview:
        index["preview"] = entry
    else:
        entries = [entry] + [e for e in index["digests"] if e["file"] != path]
        for old in entries[KEEP_DIGESTS:]:
            (data_dir / old["file"]).unlink(missing_ok=True)
        index["digests"] = entries[:KEEP_DIGESTS]
    index.update(settings_url=settings_url, web_url=web_url)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Web page data written: {label}")


def write_run_summary(email_dicts, web_url, preview):
    """Shown on the run's page in the GitHub Actions tab."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(report.markdown(email_dicts, web_url, preview))


def run(preview=False, now=None):
    now = now or datetime.now(timezone.utc)
    report.reset()
    cfg = load_config()
    state, history = load_state(), load_history()
    local = now.astimezone(ZoneInfo(cfg["schedule"]["timezone"]))

    stories, dicts, _ = build(cfg, state, history, now, preview)
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
        publish(local, dicts, web_debates, web_url, settings_url, preview=True)
        write_run_summary(email_dicts, web_url, preview=True)
        print(f"Preview only, nothing emailed. Email layout saved in {out_dir / 'preview.html'}")
        return

    from .emailer import send_email

    send_email(subject, html, text)
    publish(local, dicts, web_debates, web_url, settings_url, preview=False)
    write_run_summary(email_dicts, web_url, preview=False)
    save_history(remember(history, stories, local.date().isoformat(), cfg, now))
    save_state({"last_sent_utc": now.isoformat(timespec="seconds"), "last_sent_local_date": local.date().isoformat()})


def main():
    parser = argparse.ArgumentParser(description="Build and send the news digest.")
    parser.add_argument("--preview", action="store_true", help="build and publish a Preview edition, no email, memory untouched")
    run(preview=parser.parse_args().preview)


if __name__ == "__main__":
    main()
