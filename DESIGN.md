# Design decisions

This records what was agreed and why, so later changes stay consistent.

**Goal.** A concise daily briefing of facts, key numbers and consequences, with opinion and fluff removed. The topics are engineering, science, technology, Perth and WA local news, and socioeconomics backed by statistics. The whole thing must cost nothing to run.

**Source of news.** Google offers no API for a personal "For You" feed, and scraping it would need automated logins, which are fragile and against Google's terms. So the app uses Google News RSS (Australian edition) by topic and by search words, plus direct outlet feeds. All of this is set in `config.toml`. Paywalled outlets are blocked.

**Running.** GitHub Actions runs every hour. `newsdigest/gate.py` decides whether this hour is the one to send, based on `send_time` (default 3am Perth) and `send_days`. That lets the send time and frequency live in the settings file instead of the workflow file. A manual "Run workflow" always sends.

**No repeats.** Each run looks back to the previous send, with a 6 hour overlap to catch late timestamps. `state/history.json` remembers every story sent in the last 30 days, with its links and headlines. Links already sent are skipped. A new event whose headlines match a remembered story is treated as a possible update. The AI decides whether it holds materially new facts. If it does, it is sent marked UPDATE, with the new facts on top and the original story below. If not, it is dropped.

**Filtering opinion.** There are two screens. First, rules on headlines and web addresses (opinion, comment, editorial, analysis, letters, live blogs and so on). Second, the AI flags anything that is mainly opinion or has no real news event.

**Ranking.** The score is based on the number of independent outlets (on a log scale), multiplied by the category weight, the region weight (Perth 3, Australia 2, International 1 by default, where 0 hides a region), freshness and the AI's importance rating from 1 to 5.

**AI.** Gemini free tier by default, with Groq free tier as automatic backup. Stories are batched five per request with a pause between requests, to stay inside free limits. With no key, the digest falls back to headlines only, which is useful for testing. The AI is told to report only facts in the supplied text, attribute claims, keep "why it matters" to direct measurable consequences, and to name the real sides of any debate. For Australian politics these are Labor, the Coalition and the Greens where relevant, for US politics Democrats and Republicans, and for science the actual research groups.

**Output.** An HTML email with a plain text copy, sent through Gmail with an app password. Top 10 stories by default. It also publishes a static web page on GitHub Pages showing the top 40, with instant filters by region, topic, email stories and updates. Filter choices are remembered in the browser. The page cannot change collection settings, so it links to `config.toml` in GitHub's editor instead.

**Repository visibility.** Public. Secrets stay encrypted, Pages is free, and Actions minutes are unlimited. Visitors could see the topic list and the published digests, which is acceptable for public news.
