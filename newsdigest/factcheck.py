"""On demand fact check of one published story, started from the app's Fact check button.

python -m newsdigest.factcheck --file digests/2026-09-27-0744.json --id s3 --key abc123

Re reads the story's source articles, asks the AI to check every fact, number and
consequence against them, and writes docs/data/factchecks/<key>.json for the app.
"""

import argparse
import json
import re
from datetime import datetime, timezone

from . import ai, extract
from .settings import DOCS_DIR, load_config

SYSTEM = """You check a short news summary against the original articles it was written from.
Split the summary into its individual claims: each factual sentence, each key number and the "why it matters" statement.
For each claim decide:
"supported" if an article states it (numbers must match, allowing for rounding),
"contradicted" if an article states something different,
"not_found" if no article mentions it.
Quote the shortest passage that decides it, and name the outlet. Judge only against the supplied text, never your own knowledge.
Then give an overall verdict: "supported" if every claim is supported, "contradicted" if any claim is contradicted, otherwise "partly_supported".
Write in Australian English with plain sentences, using commas and full stops rather than dashes.
Respond with JSON only, shaped as:
{"verdict": "...", "summary": "one sentence", "claims": [{"claim": "...", "status": "...", "evidence": "...", "source": "..."}]}"""

STATUSES = ("supported", "contradicted", "not_found")
VERDICTS = ("supported", "partly_supported", "contradicted")
ARTICLE_CHARS = 12000
SAFE_KEY = re.compile(r"^[a-z0-9]{1,16}$")


def claims_text(story):
    parts = [f"Headline: {story.get('headline', '')}"]
    if story.get("update_summary"):
        parts.append(f"What is new: {story['update_summary']}")
    parts.append(f"Facts: {story.get('facts', '')}")
    for number in story.get("key_numbers") or []:
        parts.append(f"Key number: {number}")
    if story.get("why_it_matters"):
        parts.append(f"Why it matters: {story['why_it_matters']}")
    return "\n".join(parts)


def fetch_articles(story):
    sources = story.get("sources") or []
    resolved = extract.resolve_links([s["url"] for s in sources])
    articles = []
    for s in sources[:4]:
        url = resolved.get(s["url"]) or s["url"]
        text = extract.fetch_text(url)
        if text:
            articles.append({"source": s["name"], "url": url, "text": text[:ARTICLE_CHARS]})
    return articles


def clean(result, articles):
    claims = []
    for c in result.get("claims") or []:
        if not isinstance(c, dict) or not str(c.get("claim", "")).strip():
            continue
        status = c.get("status") if c.get("status") in STATUSES else "not_found"
        claims.append({k: str(c.get(k, "")).strip() for k in ("claim", "evidence", "source")} | {"status": status})
    verdict = result.get("verdict") if result.get("verdict") in VERDICTS else "partly_supported"
    if any(c["status"] == "contradicted" for c in claims):
        verdict = "contradicted"
    elif claims and all(c["status"] == "supported" for c in claims):
        verdict = "supported"
    elif verdict == "supported":
        verdict = "partly_supported"
    return {
        "verdict": verdict,
        "summary": str(result.get("summary", "")).strip(),
        "claims": claims,
        "articles_checked": [{"source": a["source"], "url": a["url"]} for a in articles],
    }


def check(story, cfg):
    articles = fetch_articles(story)
    if not articles:
        return {"verdict": "unavailable", "summary": "None of the source articles could be downloaded (they may be paywalled or removed), so nothing could be checked.", "claims": [], "articles_checked": []}
    prompt = "SUMMARY TO CHECK\n" + claims_text(story) + "\n\n" + "\n\n".join(
        f"ARTICLE from {a['source']}:\n{a['text']}" for a in articles)
    return clean(ai.ask(cfg, prompt, SYSTEM), articles)


def run(edition_file, story_id, key, now=None):
    if not SAFE_KEY.match(key or ""):
        raise SystemExit("story key must be letters and digits only")
    data_dir = DOCS_DIR / "data"
    path = (data_dir / edition_file).resolve()
    if data_dir.resolve() not in path.parents:
        raise SystemExit("edition file must be inside docs/data")
    edition = json.loads(path.read_text(encoding="utf-8"))
    story = next((s for s in edition.get("stories", []) if s.get("id") == story_id), None)
    if story is None:
        raise SystemExit(f"story {story_id} not found in {edition_file}")
    cfg = load_config()
    try:
        result = check(story, cfg)
    except ai.ProviderError as exc:
        result = {"verdict": "unavailable", "summary": f"The AI could not run the check: {exc}", "claims": [], "articles_checked": []}
    result.update(key=key, headline=story.get("headline", ""), checked=(now or datetime.now(timezone.utc)).isoformat(timespec="minutes"))
    out_dir = data_dir / "factchecks"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{key}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    # A small index so the app knows which stories have been checked.
    index_path = out_dir / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        index = {}
    index[key] = {"verdict": result["verdict"], "checked": result["checked"]}
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Fact check of '{story.get('headline', '')}': {result['verdict']}, {len(result['claims'])} claims")
    return result


def main():
    parser = argparse.ArgumentParser(description="Fact check one published story.")
    parser.add_argument("--file", required=True, help="edition file inside docs/data, e.g. digests/2026-09-27-0744.json")
    parser.add_argument("--id", required=True, help="story id inside the edition, e.g. s3")
    parser.add_argument("--key", required=True, help="the app's key for the story, used as the result file name")
    args = parser.parse_args()
    run(args.file, args.id, args.key)


if __name__ == "__main__":
    main()
