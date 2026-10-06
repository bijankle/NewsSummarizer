# News Digest

## [Open the news](https://bijankle.github.io/NewsSummarizer/)

**https://bijankle.github.io/NewsSummarizer/** is the app itself. Bookmark it, or open it in Chrome and click "Install app". This page you are reading is only the instruction manual.

A free daily news page stripped down to facts, key numbers and why they matter. Opinion pieces, sport and fluff are filtered out, the same event reported by several outlets is merged into one story, and genuine disagreements are laid out side by side. It runs entirely on GitHub's free servers, so your computer does not need to be on.

## Using the app

**Nothing runs by itself.** The AI only works when you press a button, so no effort is wasted on news you will not read. **Update news** collects and summarises new stories, usually in 5 to 15 minutes. Keep reading meanwhile; a line at the top shows progress and the stories appear by themselves when ready.

**Unread, Favourites, Read.** New stories land in Unread. Cards are compact: tap the headline or "Show story" to open the full facts, key numbers, why it matters, debate and sources.

Swipe a story **right** to mark it read, or **left** to add it to Favourites (which also clears it from Unread). On a computer, use the Read tickbox, the star, or the buttons inside an open story. Undo appears for a few seconds after each action. Favourites stay until you remove them; Read keeps the last 30 days.

With your GitHub key saved (see Settings below), Read and Favourites **sync between your devices**. They are stored in `state/reader.json` in this project, which is public like the rest of the project.

**Questions you might have.** Each open story ends with the three questions a reader is most likely to ask, with answers taken only from the articles (or "The reports do not say"). They are written in the same AI request as the summary, so they cost almost nothing extra.

**Fact check** (inside an open story) re reads that story's source articles and checks every sentence and number against them, one story at a time and only when pressed. It usually takes 1 to 3 minutes and shows each claim as supported, contradicted or not found, with the quote that decides it. Checked stories get a badge.

**Week in review** writes a one page summary of the last 7 days, grouped by topic, from the stories already published. It also runs only when you press its button.

**Settings** has two parts.

*On this device*: compact or full cards, text size, sort order and how many days Unread keeps. These apply straight away.

*News collection*: stories per update, topics, region priority, and whether to include sport, updates and debates. These are saved into this project.

The buttons and sync need a free GitHub key, made once:

1. Open https://github.com/settings/personal-access-tokens/new and name it "News Digest app".
2. Pick an expiration date.
3. Under Repository access choose "Only select repositories" and pick NewsSummarizer.
4. Under Repository permissions set **Contents** to "Read and write" and **Actions** to "Read and write".
5. Click "Generate token", copy it and paste it into the GitHub key box in Settings.

The key stays in that browser only. "Forget GitHub key" removes it. Anything not in the Settings panel (search words, outlets, blocked sites, AI model) is in [config.toml](config.toml), and every line there has a note explaining it.

**Run details.** At the bottom of the page, "Run details for the latest update" shows how many stories survived each stage, any feeds that failed, what the AI did and every dropped story with the reason. Use it when something looks wrong.

## How it works

It works like a production line that runs each time you press Update news.

**Intake.** Headlines come from Google News RSS (Australian edition, by topic and by search words) plus direct outlet feeds.

**Coarse screen.** Rules reject opinion sections, paywalled outlets, sport words, stale items and anything already published.

**Grouping and ranking.** Headlines about the same event are grouped, first by shared words and then by meaning (Google's free embedding model, so "RBA lifts cash rate" and "Reserve Bank raises interest rates" become one story), then a single AI request reviews the top candidates against each other and against the last week's published headlines, merging any that report the same event (for example a rate decision and the banks passing it on) and turning continuations into updates, and finally they are ranked by how many independent outlets reported them, topic weights and region priority.

**Extraction.** The top candidates have their full article text downloaded.

**Fact extraction.** A free AI (Google Gemini, falling back to its lighter Flash Lite model when busy, and to Groq if you add a key) marks remaining opinion, sport and fluff, then writes the facts, key numbers, why it matters and any debate, and checks whether a repeat story has genuinely new facts.

**Publishing.** The stories are added to the web page and remembered, so nothing repeats unless it has new facts.

If a run fails, the app shows it with a Details link to the run log on GitHub.

## One time setup

This is already done for this project. It is here in case it ever needs redoing.

**Step 1. Free Gemini API key.** Go to https://aistudio.google.com/apikey, click "Create API key" and copy it. On the free tier Google may use what you send to improve its models; here that is public news articles.

**Step 2. Store it in GitHub.** In the repository go to Settings, "Secrets and variables", Actions, "New repository secret". Name `GEMINI_API_KEY`, value the key. Optionally add `GROQ_API_KEY` (free from https://console.groq.com/keys) as a backup AI.

**Step 3. Turn on the web page.** Settings, Pages, "Deploy from a branch", pick the default branch and the `/docs` folder (or `/ (root)`, which forwards to the news page), then Save.

**Step 4. First run.** Press Update news in the app (or in GitHub: Actions tab, "News Digest", "Run workflow").

If a run fails it shows a red cross in the Actions tab; click it and then the "Run the update task" step to read what happened.

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
| `.github/workflows/digest.yml` | The steps GitHub runs when a button is pressed (update, fact check, week in review) |
| `docs/index.html` | The news app |
| `docs/data/` | Published stories, written automatically |
| `state/` | Memory of what has been published, and your synced Read and Favourites |
| `DESIGN.md` | The design decisions behind all this |
