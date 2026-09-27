# Design decisions

This records what was agreed and why, so later changes stay consistent.

**Goal.** A concise daily briefing of facts, key numbers and consequences, with opinion and fluff removed. The topics are engineering, science, technology, Perth and WA local news, and socioeconomics backed by statistics. The whole thing must cost nothing to run.

**Source of news.** Google offers no API for a personal "For You" feed, and scraping it would need automated logins, which are fragile and against Google's terms. So the app uses Google News RSS (Australian edition) by topic and by search words, plus direct outlet feeds. All of this is set in `config.toml`. Paywalled outlets are blocked.

**Running.** Nothing is scheduled. To avoid wasting AI effort, the workflow runs only on workflow_dispatch, started from the app's buttons with a task input: update (collect and summarise), factcheck (one story, by edition file, story id and app key) or weekly (week in review from already published stories). The app watches for the result file to appear and reports failed runs with a link to the log.

**No repeats.** Each run looks back to the previous send, with a 6 hour overlap to catch late timestamps. `state/history.json` remembers every story published in the last 30 days, with its links and headlines. Links already published are skipped. A new event whose headlines match a remembered story is treated as a possible update. The AI decides whether it holds materially new facts. If it does, it is published marked UPDATE, with the new facts on top and the original story below. If not, it is dropped.

**Filtering opinion.** There are two screens. First, rules on headlines and web addresses (opinion, comment, editorial, analysis, letters, live blogs and so on). Second, the AI flags anything that is mainly opinion or has no real news event.

**Ranking.** The score is based on the number of independent outlets (on a log scale), multiplied by the category weight, the region weight (Perth 3, Australia 2, International 1 by default, where 0 hides a region), freshness and the AI's importance rating from 1 to 5.

**AI.** Gemini free tier by default, with Groq free tier as automatic backup. Stories are batched five per request with a pause between requests, to stay inside free limits. With no key, the digest falls back to headlines only, which is useful for testing. The AI is told to report only facts in the supplied text, attribute claims, keep "why it matters" to direct measurable consequences, and to name the real sides of any debate. For Australian politics these are Labor, the Coalition and the Greens where relevant, for US politics Democrats and Republicans, and for science the actual research groups.

**Reader state.** Read and favourite marks are kept per story key with a change time and synced through `state/reader.json` with the GitHub Contents API; on a clash the newest change per story wins. Favourites keep a copy of the story so they outlive the edition window; read marks older than 30 days are dropped.

**Output.** A web app on GitHub Pages is the only output; email was removed as not useful. The page is an inbox: stories from the last 14 days (adjustable) merged across daily editions, with a Read tickbox that moves a story to Archived. Read marks are kept in the browser's local storage, keyed by a hash of headline and first source, so they are per device. Each story shows when the first outlet published it. A Settings panel holds device preferences (text size, sort, days kept) and the main collection settings, which it writes to `config.toml` through the GitHub API using a fine grained key the user pastes once (Contents and Actions read and write on this repository only). The same key powers an "Update news now" button that starts the workflow. The page is installable as a Chrome app (manifest plus a small network first service worker).

**Repository visibility.** Public. Secrets stay encrypted, Pages is free, and Actions minutes are unlimited. Visitors could see the topic list and the published digests, which is acceptable for public news.
