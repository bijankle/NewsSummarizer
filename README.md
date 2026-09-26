# News Digest

A free daily email of the news that matters to you, stripped down to facts, key numbers and why they matter. Opinion pieces are filtered out, the same event reported by several outlets is merged into one story, and genuine disagreements are laid out side by side at the bottom. Every digest is also published to a web page where you can filter by region and topic.

It runs entirely on GitHub's free servers. Your computer does not need to be on.

## How it works

Think of it as a production line that runs once a day.

**Intake.** Headlines come from Google News RSS feeds (Australian edition, by topic and by search words) plus any direct outlet feeds you list in `config.toml`.

**Coarse screen.** Rules reject opinion sections, paywalled outlets, stale items and anything already sent.

**Grouping and ranking.** Headlines about the same event are grouped. Events are ranked by how many independent outlets reported them, your category weights and your region weights.

**Extraction.** The top candidates have their full article text downloaded.

**Fine screen and fact extraction.** A free AI (Google Gemini, with Groq as backup) marks any remaining opinion, then writes the facts, key numbers, why it matters and any debate, and checks whether a repeat story contains genuinely new facts.

**Delivery.** The email goes out through your Gmail account, the web page is updated, and the memory of what was sent is saved so nothing repeats.

GitHub checks every hour whether your send time has passed on a send day. If it has and nothing has been sent today, it builds and sends the digest. If a run fails, the next hourly check tries again.

## One time setup (about 15 minutes)

**Step 1. Get a free Gemini API key.** Go to https://aistudio.google.com/apikey, sign in with your Google account, click "Create API key" and copy the key. No payment details are needed. Note that on the free tier Google may use what you send to improve its models. Here that is public news articles, so this is normally harmless.

**Step 2. Create a Gmail app password.** This is a separate 16 letter password that only lets this program send email. Your real password is never used. Two step verification must be on first: go to https://myaccount.google.com/security and turn on "2 Step Verification" if it is off. Then go to https://myaccount.google.com/apppasswords, type the name "News Digest", click Create and copy the 16 letters shown.

**Step 3. Store the secrets in GitHub.** Open the repository on GitHub, then go to Settings, then "Secrets and variables", then Actions, and click "New repository secret" for each of these:

| Name | Value |
|---|---|
| `GEMINI_API_KEY` | the key from step 1 |
| `GMAIL_ADDRESS` | your Gmail address |
| `GMAIL_APP_PASSWORD` | the 16 letters from step 2 |
| `EMAIL_TO` | optional, the address to send to if not the same Gmail address. Separate several with commas |
| `GROQ_API_KEY` | optional backup AI, free from https://console.groq.com/keys |

Secrets are encrypted. Nobody can read them, even on a public repository, and they never appear in logs.

**Step 4. Turn on the web page.** In the repository go to Settings, then Pages. Under "Build and deployment" choose "Deploy from a branch", pick the default branch and the `/docs` folder, then Save. After a minute or two the page lives at `https://<your GitHub username>.github.io/<repository name>/`. GitHub Pages is free for public repositories.

**Step 5. Run it once by hand.** Go to the Actions tab. If GitHub asks, click to enable workflows. Choose "News Digest" on the left, click "Run workflow", leave the mode on "send now" and click the green button. After about five minutes the email should arrive. From then on it runs by itself.

## Everyday use

**One click digest.** Actions tab, then News Digest, then Run workflow, with the mode on "send now".

**Seeing what the email would contain, without sending it.** Actions tab, then News Digest, then Run workflow, and change the mode to "preview". Nothing is emailed and the memory of sent stories is not touched, so you can preview as often as you like and the next real email is unaffected. After about five minutes the results show up in two places.

On the web page, a "Preview" edition appears at the top of the Edition list, with the stories marked "Would be in email". Press Reload if the page was already open. GitHub Pages can take a minute or two after the run finishes to pick up the new data.

On the run's own page in the Actions tab, the summary lists the email stories and the stage counts, with no waiting for the web page.

Both show a "Run details" panel for troubleshooting. It gives the number of stories left after each stage, from headlines collected down to stories in the email, plus any feeds that failed, what the AI did on each request, and every dropped story with the reason it was dropped (opinion, already sent with no new facts, region set to 0, ranked below the cut and so on). Real digests carry the same panel, so you can check afterwards why a story did or did not make it.

**Changing settings.** Open `config.toml` on GitHub, click the pencil icon, edit and click "Commit changes". Every setting has a note explaining it. The email and the web page both have a "Change settings" link that goes straight there. The main ones are listed here.

| Setting | Default | Meaning |
|---|---|---|
| `send_time` | `"03:00"` | Perth time, 24 hour clock |
| `send_days` | every day | Remove days for weekdays only or weekly |
| `email_story_count` | 10 | Stories in the email |
| `web_story_count` | 40 | Stories on the web page |
| `show_updates` | true | Re send stories that gain genuinely new facts, marked UPDATE |
| `debates_section` | true | Sides of genuine disagreements at the bottom |
| `[regions]` | Perth 3, Australia 2, International 1 | Ranking weights. 0 hides a region |
| `[categories.*]` | | Switch topics on or off, add search words or feeds |

**Why the email may arrive a bit after the send time.** GitHub starts scheduled jobs when it has capacity, usually 5 to 20 minutes late and occasionally more. The program simply sends on the first hourly check after your send time.

**When something goes wrong.** Failed runs show a red cross in the Actions tab, and GitHub emails you about them. Click the run and then "Build and send the digest" to read what happened. Common causes are a mistyped secret or a Gmail app password that was revoked.

**Keeping it alive.** GitHub pauses scheduled workflows in repositories with no activity for 60 days. The daily memory save counts as activity, so this should not happen while it is sending. If it ever does, the Actions tab shows a button to re enable it.

## Running on your own computer (optional)

With Python 3.11 or newer:

```
pip install -r requirements.txt
set GEMINI_API_KEY=your key        (Windows; use export on Mac or Linux)
python -m newsdigest --preview
```

Then open `output/preview.html`. The tests run with `python -m unittest discover tests`.

## Files

| Path | Purpose |
|---|---|
| `config.toml` | All settings |
| `newsdigest/` | The program, one file per station of the production line |
| `.github/workflows/digest.yml` | The hourly schedule and the steps GitHub runs |
| `docs/index.html` | The filterable web page |
| `docs/data/` | Published digests, written automatically |
| `state/` | Memory of what has been sent, written automatically |
| `DESIGN.md` | The design decisions behind all this |
