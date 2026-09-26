"""Run details for troubleshooting: how many stories survived each stage, and why others were dropped.

Every stage records into the shared `report`, which main.py resets at the start of a run
and publishes alongside the stories.
"""

MAX_DROPPED = 150


class Report:
    def __init__(self):
        self.reset()

    def reset(self):
        self.funnel = []          # [label, count] in pipeline order
        self.dropped = []         # {"headline", "source", "reason"}
        self.feed_failures = []   # {"url", "error"}
        self.ai_notes = []        # one line per AI request
        self.lookback_hours = 0

    def stage(self, label, count):
        self.funnel.append([label, count])

    def drop(self, headline, source, reason):
        if len(self.dropped) < MAX_DROPPED:
            self.dropped.append({"headline": headline, "source": source, "reason": reason})

    def drop_story(self, story, reason):
        self.drop(story.headline or story.items[0].title, story.items[0].source, reason)

    def to_dict(self):
        return {
            "lookback_hours": round(self.lookback_hours),
            "funnel": self.funnel,
            "feed_failures": self.feed_failures,
            "ai_notes": self.ai_notes,
            "dropped": self.dropped,
        }

    def markdown(self, email_stories, web_url, preview):
        """Summary shown on the GitHub Actions run page."""
        lines = ["## " + ("Preview, not emailed" if preview else "Digest sent"), ""]
        if web_url:
            lines += [f"Web page: {web_url}" + (" (choose the Preview edition)" if preview else ""), ""]
        lines += ["### Stories " + ("that would be in the email" if preview else "in the email"), ""]
        for n, s in enumerate(email_stories, start=1):
            tag = "UPDATE: " if s["is_update"] else ""
            lines.append(f"{n}. {tag}{s['headline']} ({s['category_label']}, {s['region']})")
        if not email_stories:
            lines.append("None.")
        lines += ["", "### How many survived each stage", "", "| Stage | Count |", "|---|---|"]
        lines += [f"| {label} | {count} |" for label, count in self.funnel]
        if self.feed_failures:
            lines += ["", f"### Feeds that failed ({len(self.feed_failures)})", ""]
            lines += [f"{f['url']}: {f['error']}  " for f in self.feed_failures]
        if self.ai_notes:
            lines += ["", "### AI", ""] + [f"{note}  " for note in self.ai_notes]
        return "\n".join(lines) + "\n"


report = Report()
