"""Station five: turn finished stories into the data the web page shows."""

REGION_LABELS = {"perth": "Perth", "australia": "Australia", "international": "International"}


def long_date(d):
    return f"{d:%A} {d.day} {d:%B %Y}"


def story_to_dict(story, categories):
    return {
        "id": story.id,
        "headline": story.headline or story.items[0].title,
        "facts": story.facts,
        "key_numbers": story.key_numbers,
        "why_it_matters": story.why_it_matters,
        "category": story.category,
        "category_label": categories[story.category]["label"],
        "region": story.region,
        "importance": story.importance,
        "is_update": bool(story.previous),
        "update_summary": story.update_summary,
        "previous": {
            "date": story.previous.get("date", ""),
            "headline": story.previous.get("headline", ""),
            "facts": story.previous.get("facts", ""),
        } if story.previous else None,
        "debate": story.debate,
        "sources": story.sources[:6],
        "published": story.first_published.isoformat() if story.first_published else None,
        "latest_report": story.published.isoformat() if story.published else None,
        "processed": story.processed,
    }
