"""Article deduplication using URL normalization and title similarity."""

from __future__ import annotations

import json
import logging
import pathlib
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from .parser import Article

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "seen_articles.json"

# UTM and tracking parameters to strip
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "source", "fbclid", "gclid", "mc_cid", "mc_eid",
}


def normalize_url(url: str) -> str:
    """Normalize a URL for dedup comparison."""
    parsed = urlparse(url)
    # Remove www prefix
    host = parsed.hostname or ""
    if host.startswith("www."):
        host = host[4:]
    # Remove tracking parameters
    params = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {k: v for k, v in params.items() if k.lower() not in TRACKING_PARAMS}
    clean_query = urlencode(filtered, doseq=True)
    # Remove trailing slash
    path = parsed.path.rstrip("/")
    return urlunparse(("", host, path, "", clean_query, ""))


def _titles_similar(a: str, b: str, threshold: float = 0.9) -> bool:
    """Check if two titles are similar enough to be duplicates."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


class Deduplicator:
    """Manages seen articles and filters duplicates."""

    def __init__(self, db_path: str | pathlib.Path | None = None):
        self.db_path = pathlib.Path(db_path) if db_path else DEFAULT_DB_PATH
        self._seen: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        """Load seen articles from disk."""
        if not self.db_path.exists():
            return {}
        try:
            with open(self.db_path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logger.warning("Invalid seen_articles.json format, resetting")
                return {}
            return data
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupted seen_articles.json, starting fresh")
            return {}

    def save(self) -> None:
        """Persist seen articles to disk."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(self._seen, f, indent=2, ensure_ascii=False)

    def prune(self, window_days: int = 7) -> None:
        """Remove entries older than the dedup window."""
        now = datetime.now(timezone.utc)
        to_remove = []
        for key, entry in self._seen.items():
            try:
                seen_at = datetime.fromisoformat(entry["seen_at"])
                if (now - seen_at).days > window_days:
                    to_remove.append(key)
            except (KeyError, ValueError):
                to_remove.append(key)
        for key in to_remove:
            del self._seen[key]
        if to_remove:
            logger.info("Pruned %d old entries from dedup DB", len(to_remove))

    def filter_new(self, articles: list[Article]) -> list[Article]:
        """Return only articles not previously seen."""
        new_articles: list[Article] = []
        seen_titles = [e.get("title", "") for e in self._seen.values()]

        for article in articles:
            norm_url = normalize_url(article.link)

            # Check URL match
            if norm_url in self._seen:
                continue

            # Check title similarity
            is_dup = False
            for seen_title in seen_titles:
                if _titles_similar(article.title, seen_title):
                    is_dup = True
                    break
            if is_dup:
                continue

            # Mark as seen
            self._seen[norm_url] = {
                "title": article.title,
                "seen_at": datetime.now(timezone.utc).isoformat(),
            }
            seen_titles.append(article.title)
            new_articles.append(article)

        logger.info(
            "Dedup: %d articles in, %d new", len(articles), len(new_articles)
        )
        return new_articles
