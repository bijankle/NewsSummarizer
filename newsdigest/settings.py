"""Loading config.toml and the saved state files. Standard library only."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.toml"
STATE_DIR = ROOT / "state"
STATE_PATH = STATE_DIR / "state.json"
HISTORY_PATH = STATE_DIR / "history.json"
DOCS_DIR = ROOT / "docs"

REGIONS = ("perth", "australia", "international")
DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

DEFAULTS = {
    "schedule": {
        "timezone": "Australia/Perth",
        "send_time": "03:00",
        "send_days": list(DAY_NAMES),
    },
    "digest": {
        "email_story_count": 10,
        "web_story_count": 40,
        "show_updates": True,
        "debates_section": True,
        "language": "en-AU",
        "country": "AU",
        "web_page_url": "",
        "max_lookback_days": 7,
        "first_run_lookback_hours": 30,
        "overlap_hours": 6,
        "articles_per_story": 2,
        "similarity_threshold": 0.3,
        "history_days": 30,
        "exclude_kinds": ["opinion", "sport", "entertainment", "lifestyle", "promotional"],
    },
    "ai": {
        "provider": "gemini",
        "gemini_model": "gemini-3.8-flash",
        "groq_model": "llama-3.3-70b-versatile",
        "stories_per_request": 5,
        "seconds_between_requests": 8,
        "max_minutes": 12,
    },
    "regions": {"perth": 3.0, "australia": 2.0, "international": 1.0},
    "sources": {"blocked": [], "exclude_headline_words": []},
    "categories": {},
}

CATEGORY_DEFAULTS = {
    "enabled": True,
    "weight": 1.0,
    "region": "international",
    "google_news_topics": [],
    "google_news_searches": [],
    "feeds": [],
}


def load_config(path=CONFIG_PATH):
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    cfg = {}
    for section, defaults in DEFAULTS.items():
        merged = dict(defaults)
        merged.update(raw.get(section, {}))
        cfg[section] = merged
    categories = {}
    for key, cat in cfg["categories"].items():
        merged = dict(CATEGORY_DEFAULTS, label=key.replace("_", " ").title())
        merged.update(cat)
        if merged["region"] not in REGIONS:
            merged["region"] = "international"
        categories[key] = merged
    cfg["categories"] = categories
    cfg["schedule"]["send_days"] = [d.lower()[:3] for d in cfg["schedule"]["send_days"]]
    return cfg


def enabled_categories(cfg):
    return {k: c for k, c in cfg["categories"].items() if c["enabled"]}


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")


def load_state():
    return _load_json(STATE_PATH, {})


def save_state(state):
    _save_json(STATE_PATH, state)


def load_history():
    return _load_json(HISTORY_PATH, [])


def save_history(history):
    _save_json(HISTORY_PATH, history)
