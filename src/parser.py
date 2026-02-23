"""RSS feed parser and article normalizer."""

from __future__ import annotations

import html
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from time import mktime

import feedparser

from .feeds import FeedSource

logger = logging.getLogger(__name__)

USER_AGENT = "NewsDigestBot/1.0 (+https://github.com/news-digest)"


@dataclass
class Article:
    id: str
    title: str
    link: str
    summary: str
    published: datetime
    source_name: str
    category: str
    category_ja: str


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_date(entry: dict) -> datetime:
    """Extract published date from a feed entry."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        return datetime.fromtimestamp(mktime(entry.updated_parsed), tz=timezone.utc)
    return datetime.now(timezone.utc)


def fetch_articles(
    source: FeedSource,
    max_articles: int = 10,
    max_age_hours: float | None = None,
) -> list[Article]:
    """Fetch and normalize articles from a single RSS feed.

    Args:
        source: Feed source configuration.
        max_articles: Maximum number of entries to process from the feed.
        max_age_hours: If set, skip articles older than this many hours.
            Articles without a parseable date are always included.

    Returns an empty list on failure (never crashes).
    """
    try:
        feed = feedparser.parse(
            source.url,
            agent=USER_AGENT,
        )

        if feed.bozo and not feed.entries:
            logger.warning("Feed error for %s: %s", source.name, feed.bozo_exception)
            return []

        now = datetime.now(timezone.utc)
        articles: list[Article] = []
        for entry in feed.entries[:max_articles]:
            published = _parse_date(entry)

            # Freshness filter: skip articles older than max_age_hours
            if max_age_hours is not None:
                age_hours = (now - published).total_seconds() / 3600
                if age_hours > max_age_hours:
                    continue

            title = _strip_html(entry.get("title", "No Title"))
            link = entry.get("link", "")
            summary_raw = entry.get("summary", entry.get("description", ""))
            summary = _strip_html(summary_raw)
            # Truncate long summaries
            if len(summary) > 500:
                summary = summary[:497] + "..."

            article_id = entry.get("id", link)

            articles.append(
                Article(
                    id=article_id,
                    title=title,
                    link=link,
                    summary=summary,
                    published=published,
                    source_name=source.name,
                    category=source.category,
                    category_ja=source.category_ja,
                )
            )

        logger.info("Fetched %d articles from %s", len(articles), source.name)
        return articles

    except Exception:
        logger.exception("Failed to fetch feed: %s", source.name)
        return []


def fetch_all_articles(
    sources: list[FeedSource],
    max_articles: int = 10,
    max_workers: int = 8,
    max_age_hours: float | None = None,
) -> tuple[list[Article], dict[str, bool]]:
    """Fetch articles from all feeds in parallel using a thread pool.

    Args:
        sources: List of feed sources to fetch.
        max_articles: Default maximum articles per feed.
        max_workers: Thread pool size.
        max_age_hours: If set, skip articles older than this many hours.

    Returns a tuple of (all_articles, feed_stats) where feed_stats maps
    each feed name to whether it succeeded (had at least one article).
    """
    all_articles: list[Article] = []
    feed_stats: dict[str, bool] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_source = {
            executor.submit(
                fetch_articles,
                source,
                source.max_articles if source.max_articles is not None else max_articles,
                max_age_hours,
            ): source
            for source in sources
        }

        for future in as_completed(future_to_source):
            source = future_to_source[future]
            try:
                articles = future.result()
                feed_stats[source.name] = len(articles) > 0
                all_articles.extend(articles)
            except Exception:
                logger.exception("Unexpected error fetching %s", source.name)
                feed_stats[source.name] = False

    return all_articles, feed_stats
