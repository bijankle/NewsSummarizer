"""Station four: the AI reads each story's articles and extracts only the facts.

Two free providers are supported: Google Gemini and Groq. Keys come from the
GEMINI_API_KEY and GROQ_API_KEY environment variables (GitHub Secrets).
"""

import json
import os
import re
import time

import requests

from .diagnostics import report
from .settings import REGIONS

SYSTEM_PROMPT = """You are the editor of a strictly factual news briefing for a reader in Perth, Western Australia. The reader is an engineer who wants facts, numbers and consequences, with no opinion, spin or filler.

For every story you are given, follow these rules.

1. Report only facts stated in the supplied articles: who, what, when, where, how many. Attribute claims to whoever made them ("police said", "the ABS reported", "the company claims"). Never add facts that are not in the text. If outlets disagree on a fact, say so.
2. Remove opinion, speculation, loaded or emotional adjectives, commentators' predictions and rhetorical framing.
3. Set is_opinion to true if the piece is mainly opinion, a column, an editorial, a review, a promotion, or has no real news event. Otherwise false. Set kind to exactly one of: "news", "opinion", "sport", "entertainment", "lifestyle", "promotional". Match reports, team news, fixtures and how to watch guides are "sport". Celebrity, arts and TV are "entertainment". Lotto wins, travel, food and human interest fluff are "lifestyle". Press releases and advertorials are "promotional".
4. headline: a plain, neutral headline of at most 14 words.
5. facts: two to four plain sentences covering the core facts.
6. key_numbers: up to four figures, each with units and context, for example "Unemployment rate: 4.1% in August, up from 4.0% in July". Use an empty list if there are none.
7. why_it_matters: one or two sentences on the direct, concrete consequences that follow from the facts, such as who is affected, by how much and from when. No predictions beyond what the sources state and no value judgements.
8. category: the best fitting key from the allowed categories list.
9. region: "perth" if it mainly concerns Perth or Western Australia, "australia" if it mainly concerns Australia, otherwise "international".
10. importance: 1 to 5 for a general reader in Perth. 5 means major impact on many people, 1 means minor or niche.
11. debate: only when the sources show a genuine public disagreement over policy, evidence or interpretation. Name the real sides. For Australian politics use Labor, the Coalition (Liberal and National parties) and the Greens where relevant. For US politics use Democrats and Republicans. For science, engineering and economics use the actual groups, such as a research team and its critics, or an industry body and a regulator. Give each side's position and the evidence it cites, neutrally, without picking a winner. Otherwise null.
12. If a story includes a PREVIOUSLY SENT section, the reader already has that version. Set has_new_facts to true only if the new articles contain materially new facts, and put only those new facts in update_summary (one to three sentences). If there is nothing new, set has_new_facts to false.
13. If only headlines are available (no article text), keep facts to what the headlines state and say that details were not available.

Write in Australian English with plain sentences, using commas and full stops rather than dashes. Respond with JSON only."""

FORMAT_HINT = """Return a JSON object of this exact shape:
{"stories": [{"id": "s1", "is_opinion": false, "kind": "news", "headline": "...", "facts": "...", "key_numbers": ["..."], "why_it_matters": "...", "category": "...", "region": "perth", "importance": 3, "has_new_facts": true, "update_summary": "", "debate": null}]}
where debate, when present, looks like {"question": "...", "sides": [{"side": "...", "position": "...", "evidence": "..."}]}.
Include one object for every story id given."""

KINDS = ("news", "opinion", "sport", "entertainment", "lifestyle", "promotional")

# Characters of article text per request, sized to each free tier.
CHAR_BUDGET = {"gemini": 60000, "groq": 14000}


class ProviderError(Exception):
    pass


def available_providers(cfg):
    order = []
    first = cfg["ai"]["provider"].lower()
    if first == "none":
        return order
    for name in (first, "gemini", "groq"):
        key = os.environ.get(f"{name.upper()}_API_KEY", "").strip()
        if key and name not in order and name in CHAR_BUDGET:
            order.append(name)
    return order


BUSY_WAITS = (15, 30, 45)  # seconds between attempts when the AI is busy
_deadline = float("inf")   # set by summarise(); no waiting past it


class OutOfTime(ProviderError):
    pass


def _post_json(url, headers, body):
    error = ""
    for attempt in range(len(BUSY_WAITS) + 1):
        if time.monotonic() >= _deadline:
            raise OutOfTime("AI time limit reached")
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=120)
        except requests.RequestException as exc:
            error = str(exc)
        else:
            if resp.status_code == 200:
                return resp.json()
            error = f"HTTP {resp.status_code}: {resp.text[:300]}"
            if resp.status_code not in (429, 500, 502, 503, 504):
                raise ProviderError(error)
        if attempt == len(BUSY_WAITS):
            break
        wait = BUSY_WAITS[attempt]
        if time.monotonic() + wait >= _deadline:
            break
        print(f"    AI request failed ({error[:120]}), retrying in {wait}s")
        time.sleep(wait)
    raise ProviderError(error)


GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
FLASH_NAME = re.compile(r"^gemini-(\d+(?:\.\d+)?)-flash$")
LITE_NAME = re.compile(r"^gemini-(\d+(?:\.\d+)?)-flash-lite$")


def _newest_gemini(pattern):
    """Newest model whose name matches pattern, from Google's model list."""
    try:
        resp = requests.get(
            f"{GEMINI_API}/models", params={"pageSize": 1000},
            headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"].strip()}, timeout=30,
        )
        resp.raise_for_status()
        models = resp.json().get("models", [])
    except (requests.RequestException, ValueError):
        return None
    candidates = []
    for m in models:
        name = m.get("name", "").removeprefix("models/")
        match = pattern.match(name)
        if match and "generateContent" in m.get("supportedGenerationMethods", []):
            candidates.append((float(match.group(1)), name))
    return max(candidates)[1] if candidates else None


def replacement_gemini_model(error_text, current):
    """When Google retires a model, find the newest plain Flash model instead.

    Google's error usually names the successor. Otherwise ask for the model list.
    """
    hinted = [m for m in re.findall(r"models/(gemini[\w.\-]*\w)", error_text) if m != current]
    return hinted[0] if hinted else _newest_gemini(FLASH_NAME)


def _is_busy(error):
    return any(code in str(error) for code in ("HTTP 429", "HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504"))


def _switch(cfg, new_model, why):
    note = f"Gemini model {cfg['ai']['gemini_model']} {why}, switched to {new_model} for the rest of this run."
    print(f"  {note}")
    report.ai_notes.append(note)
    cfg["ai"]["gemini_model"] = new_model


def call_gemini(cfg, prompt):
    model = cfg["ai"]["gemini_model"]
    headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"].strip()}
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }
    try:
        data = _post_json(f"{GEMINI_API}/models/{model}:generateContent", headers, body)
    except OutOfTime:
        raise
    except ProviderError as exc:
        if "HTTP 404" in str(exc):
            new_model = replacement_gemini_model(str(exc), model)
            why = f"is not available (set gemini_model = \"{new_model}\" in config.toml)"
        elif _is_busy(exc) and not LITE_NAME.match(model):
            # The lighter Flash Lite model is usually less loaded during busy spells.
            new_model = _newest_gemini(LITE_NAME)
            why = "is overloaded"
        else:
            raise
        if not new_model or new_model == model:
            raise
        _switch(cfg, new_model, why)
        data = _post_json(f"{GEMINI_API}/models/{new_model}:generateContent", headers, body)
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError) as exc:
        raise ProviderError(f"unexpected Gemini reply: {str(data)[:300]}") from exc
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def call_groq(cfg, prompt):
    headers = {"Authorization": f"Bearer {os.environ['GROQ_API_KEY'].strip()}"}
    body = {
        "model": cfg["ai"]["groq_model"],
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    data = _post_json("https://api.groq.com/openai/v1/chat/completions", headers, body)
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise ProviderError(f"unexpected Groq reply: {str(data)[:300]}") from exc


CALLERS = {"gemini": call_gemini, "groq": call_groq}


def build_prompt(stories, categories, budget):
    lines = [
        "Allowed categories: " + ", ".join(f"{k} ({c['label']})" for k, c in categories.items()),
        "Allowed regions: " + ", ".join(REGIONS),
        FORMAT_HINT,
        "",
    ]
    n_articles = sum(max(1, len(s.articles)) for s in stories)
    per_article = max(800, budget // max(1, n_articles))
    for story in stories:
        lines.append(f"=== STORY {story.id} ===")
        lines.append("Headlines: " + " | ".join(f"{i.title} ({i.source})" for i in story.items[:6]))
        if story.previous:
            lines.append(f"PREVIOUSLY SENT on {story.previous.get('date', 'an earlier day')}: {story.previous.get('facts', '')}")
        if story.articles:
            for n, article in enumerate(story.articles, start=1):
                lines.append(f"Article {n} ({article.source}):\n{article.text[:per_article]}")
        else:
            extra = " ".join(i.summary for i in story.items if i.summary)[:per_article]
            lines.append("No article text available." + (f" Feed summary: {extra}" if extra else ""))
        lines.append("")
    return "\n".join(lines)


def parse_reply(text):
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    data = json.loads(text)
    stories = data.get("stories", data if isinstance(data, list) else [])
    return {str(s.get("id")): s for s in stories if isinstance(s, dict)}


def _text(value):
    if isinstance(value, list):
        value = " ".join(str(v) for v in value)
    return str(value or "").strip()


def apply_result(story, result, categories):
    story.processed = True
    story.is_opinion = story.is_opinion or bool(result.get("is_opinion"))
    kind = _text(result.get("kind")).lower()
    story.kind = kind if kind in KINDS else ("opinion" if story.is_opinion else "news")
    story.headline = _text(result.get("headline")) or story.items[0].title
    story.facts = _text(result.get("facts"))
    story.key_numbers = [str(n).strip() for n in result.get("key_numbers") or [] if str(n).strip()][:4]
    story.why_it_matters = _text(result.get("why_it_matters"))
    if result.get("category") in categories:
        story.category = result["category"]
    if result.get("region") in REGIONS:
        story.region = result["region"]
    try:
        story.importance = min(5, max(1, int(result.get("importance", 3))))
    except (TypeError, ValueError):
        story.importance = 3
    if story.previous:
        story.has_new_facts = bool(result.get("has_new_facts"))
        story.update_summary = _text(result.get("update_summary"))
    debate = result.get("debate")
    if isinstance(debate, dict) and debate.get("sides"):
        story.debate = {
            "question": _text(debate.get("question")),
            "sides": [
                {k: _text(side.get(k)) for k in ("side", "position", "evidence")}
                for side in debate["sides"] if isinstance(side, dict)
            ],
        }


def summarise(stories, cfg, categories):
    providers = available_providers(cfg)
    if not providers:
        print("AI: no provider configured, sending headlines only")
        report.ai_notes.append("No AI key found (or provider is \"none\"), so stories are headlines only.")
        return
    size = max(1, int(cfg["ai"]["stories_per_request"]))
    pause = float(cfg["ai"]["seconds_between_requests"])
    batches = [stories[i:i + size] for i in range(0, len(stories), size)]
    print(f"AI: {len(stories)} stories in {len(batches)} requests via {', '.join(providers)}")
    global _deadline
    minutes = float(cfg["ai"]["max_minutes"])
    _deadline = time.monotonic() + minutes * 60

    def attempt(n, batch):
        for provider in providers:
            try:
                prompt = build_prompt(batch, categories, CHAR_BUDGET[provider])
                results = parse_reply(CALLERS[provider](cfg, prompt))
            except (ProviderError, ValueError, KeyError) as exc:
                print(f"  batch {n}: {provider} failed ({str(exc)[:200]})")
                report.ai_notes.append(f"Request {n}: {provider} failed: {str(exc)[:200]}")
                continue
            for story in batch:
                if story.id in results:
                    apply_result(story, results[story.id], categories)
            print(f"  batch {n}: done by {provider}")
            report.ai_notes.append(f"Request {n}: done by {provider} ({len(batch)} stories)")
            return True
        return False

    def out_of_time():
        return time.monotonic() >= _deadline

    failed = []
    for n, batch in enumerate(batches, start=1):
        if out_of_time() or not attempt(n, batch):
            failed.append((n, batch))
        if n < len(batches) and not out_of_time():
            time.sleep(pause)
    if failed and time.monotonic() + 60 < _deadline:
        # Busy spells usually pass within a few minutes: one more go at the end.
        print(f"  retrying {len(failed)} failed request(s) after a pause")
        time.sleep(60)
        failed = [(n, b) for n, b in failed if out_of_time() or not attempt(n, b)]
    if failed:
        left = sum(len(b) for _, b in failed)
        why = f"the {minutes:g} minute AI time limit (max_minutes) was reached" if out_of_time() else "every AI provider failed"
        report.ai_notes.append(f"{left} stories left as headlines only because {why}.")
    _deadline = float("inf")
