# News Digest

## [Open the news](https://bijankle.github.io/NewsSummarizer/)

**https://bijankle.github.io/NewsSummarizer/** is the app itself. Bookmark it, or open it in Chrome and click "Install app". This page you are reading is only the instruction manual.

A free daily news page stripped down to facts, key numbers and why they matter. Opinion pieces, sport and fluff are filtered out, the same event reported by several outlets is merged into one story, and genuine disagreements are laid out side by side. It runs entirely on GitHub's free servers, so your computer does not need to be on.

## Using the app

**Unread, Archived, All.** New stories land in Unread, newest update first. Tick the "Read" box beside a story when you are done with it and it moves to Archived. "Undo" appears for a few seconds after each tick. "Mark all shown as read" clears everything currently shown. Read marks are remembered in the browser on that device.

**Each story** shows when the first outlet published it (and the latest report, if the story kept developing), the facts, key numbers, why it matters, the sides of any debate, and links to every outlet that reported it. An UPDATE label means a story you already had gained genuinely new facts: the new facts are on top and the original story is underneath.

**Filters.** Region and topic buttons, a search box and "Updates only". They change only what is shown.

**Settings** (button at the top) has two parts.

*On this device*: text size, sort order (importance or newest first) and how many days of news to keep. These apply straight away.

*News collection*: daily update time and days, stories per update, topics, region priority, and whether to include sport, updates and debates. These are saved into this project and apply from the next daily update. Saving them, and the "Update news now" button, need a free GitHub key, made once:

1. Open https://github.com/settings/personal-access-tokens/new and name it "News Digest app".
2. Pick an expiration date.
3. Under Repository access choose "Only select repositories" and pick NewsSummarizer.
4. Under Repository permissions set **Contents** to "Read and write" and **Actions** to "Read and write".
5. Click "Generate token", copy it and paste it into the GitHub key box in Settings.

The key stays in that browser only. "Forget GitHub key" removes it. Anything not in the Settings panel (search words, outlets, blocked sites, AI model) is in [config.toml](config.toml), and every line there has a note explaining it.

**Run details.** At the bottom of the page, "Run details for the latest update" shows how many stories survived each stage, any feeds that failed, what the AI did and every dropped story with the reason. Use it when something looks wrong.

## How it works

It works like a production line that runs once a day, at 3am Perth time by default.

**Intake.** Headlines come from Google News RSS (Australian edition, by topic and by search words) plus direct outlet feeds.

**Coarse screen.** Rules reject opinion sections, paywalled outlets, sport words, stale items and anything already published.

**Grouping and ranking.** Headlines about the same event are grouped and ranked by how many independent outlets reported them, topic weights and region priority.

**Extraction.** The top candidates have their full article text downloaded.

**Fact extraction.** A free AI (Google Gemini, falling back to its lighter Flash Lite model when busy, and to Groq if you add a key) marks remaining opinion, sport and fluff, then writes the facts, key numbers, why it matters and any debate, and checks whether a repeat story has genuinely new facts.

**Publishing.** The stories are added to the web page and remembered, so nothing repeats unless it has new facts.

GitHub checks every hour whether the update time has passed on an update day. If a run fails, the next hourly check tries again.

## One time setup

This is already done for this project. It is here in case it ever needs redoing.

**Step 1. Free Gemini API key.** Go to https://aistudio.google.com/apikey, click "Create API key" and copy it. On the free tier Google may use what you send to improve its models; here that is public news articles.

**Step 2. Store it in GitHub.** In the repository go to Settings, "Secrets and variables", Actions, "New repository secret". Name `GEMINI_API_KEY`, value the key. Optionally add `GROQ_API_KEY` (free from https://console.groq.com/keys) as a backup AI.

**Step 3. Turn on the web page.** Settings, Pages, "Deploy from a branch", pick the default branch and the `/docs` folder (or `/ (root)`, which forwards to the news page), then Save.

**Step 4. First run.** Actions tab, "News Digest", "Run workflow". About ten minutes later the news appears on the page. The "Update news now" button in the app's Settings does the same thing.

If a run fails it shows a red cross in the Actions tab; click it and then "Build the news update" to read what happened. GitHub pauses scheduled workflows in repositories with no activity for 60 days; the daily update counts as activity, so this should not happen, but the Actions tab has a button to re enable it if it does.

## Running on your own computer (optional)

With Python 3.11 or newer:

```
pip install -r requirements.txt
set GEMINI_API_KEY=your key        (Windows; use export on Mac or Linux)
python -m newsdigest --dry-run
```

The stories are written to `output/latest.json` and nothing is published. The tests run with `python -m unittest discover tests`.

## Files

| Path | Purpose |
|---|---|
| `config.toml` | All settings |
| `newsdigest/` | The program, one file per station of the production line |
| `.github/workflows/digest.yml` | The hourly schedule and the steps GitHub runs |
| `docs/index.html` | The news app |
| `docs/data/` | Published stories, written automatically |
| `state/` | Memory of what has been published, written automatically |
| `DESIGN.md` | The design decisions behind all this |
