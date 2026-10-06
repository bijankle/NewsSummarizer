"""Data containers passed between the stages of the pipeline."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Item:
    """One headline from one feed."""

    title: str
    link: str
    source: str
    domain: str
    published: datetime | None
    summary: str
    category: str
    region: str
    resolved: str = ""  # the outlet's own address, once known

    @property
    def best_link(self):
        return self.resolved or self.link


@dataclass
class Article:
    """Full text of one article, after extraction."""

    source: str
    url: str
    text: str


@dataclass
class Story:
    """One news event, possibly reported by several outlets."""

    id: str
    items: list
    category: str
    region: str
    score: float = 0.0
    previous: dict | None = None
    articles: list = field(default_factory=list)
    # Filled in by the AI stage.
    processed: bool = False
    is_opinion: bool = False
    kind: str = "news"
    headline: str = ""
    facts: str = ""
    key_numbers: list = field(default_factory=list)
    why_it_matters: str = ""
    importance: int = 3
    is_update: bool = False
    has_new_facts: bool = True
    update_summary: str = ""
    faq: list = field(default_factory=list)
    debate: dict | None = None

    @property
    def sources(self):
        """Distinct outlets, each with the link to use for it."""
        seen = {}
        for article in self.articles:
            seen.setdefault(article.source, article.url)
        for item in self.items:
            seen.setdefault(item.source, item.best_link)
        return [{"name": name, "url": url} for name, url in seen.items()]

    @property
    def published(self):
        """Time of the most recent report."""
        dates = [i.published for i in self.items if i.published]
        return max(dates) if dates else None

    @property
    def first_published(self):
        """When the first outlet published it."""
        dates = [i.published for i in self.items if i.published]
        return min(dates) if dates else None

    @property
    def titles(self):
        return [i.title for i in self.items]

    @property
    def links(self):
        return sorted({i.link for i in self.items} | {i.resolved for i in self.items if i.resolved})
