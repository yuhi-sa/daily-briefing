"""Feed configuration loader."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

import yaml


@dataclass
class FeedSource:
    name: str
    url: str
    category: str
    category_ja: str
    max_articles: int | None = None


@dataclass
class DigestConfig:
    max_articles_per_feed: int
    dedup_window_days: int
    feeds: list[FeedSource] = field(default_factory=list)


def load_config(path: str | pathlib.Path | None = None) -> DigestConfig:
    """Load and validate feed configuration from YAML."""
    if path is None:
        path = pathlib.Path(__file__).resolve().parent.parent / "config" / "feeds.yml"
    path = pathlib.Path(path)

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    settings = raw.get("settings", {})
    max_articles = settings.get("max_articles_per_feed", 10)
    dedup_days = settings.get("dedup_window_days", 7)

    if max_articles < 1:
        raise ValueError("max_articles_per_feed must be >= 1")
    if dedup_days < 1:
        raise ValueError("dedup_window_days must be >= 1")

    feeds: list[FeedSource] = []
    for category in raw.get("categories", []):
        cat_name = category["name"]
        cat_ja = category.get("label_ja", cat_name)
        for feed in category.get("feeds", []):
            feeds.append(
                FeedSource(
                    name=feed["name"],
                    url=feed["url"],
                    category=cat_name,
                    category_ja=cat_ja,
                    max_articles=feed.get("max_articles"),
                )
            )

    if not feeds:
        raise ValueError("No feeds configured")

    return DigestConfig(
        max_articles_per_feed=max_articles,
        dedup_window_days=dedup_days,
        feeds=feeds,
    )
