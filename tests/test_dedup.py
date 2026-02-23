"""Tests for deduplication module."""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.dedup import Deduplicator, normalize_url
from src.parser import Article


def _make_article(
    title: str = "Test Article",
    link: str = "https://example.com/article",
    article_id: str = "1",
) -> Article:
    return Article(
        id=article_id,
        title=title,
        link=link,
        summary="Summary",
        published=datetime.now(timezone.utc),
        source_name="Test",
        category="Test",
        category_ja="テスト",
    )


class TestNormalizeUrl:
    def test_removes_utm_params(self):
        url = "https://example.com/article?utm_source=twitter&utm_medium=social"
        assert normalize_url(url) == "//example.com/article"

    def test_removes_www(self):
        url = "https://www.example.com/article"
        assert normalize_url(url) == "//example.com/article"

    def test_removes_trailing_slash(self):
        url = "https://example.com/article/"
        assert normalize_url(url) == "//example.com/article"

    def test_keeps_meaningful_params(self):
        url = "https://example.com/search?q=python"
        result = normalize_url(url)
        assert "q=python" in result

    def test_combined_normalization(self):
        url = "https://www.example.com/article/?utm_source=rss&ref=homepage"
        assert normalize_url(url) == "//example.com/article"


class TestDeduplicator:
    def test_filters_duplicate_urls(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({}, f)
            db_path = f.name

        dedup = Deduplicator(db_path=db_path)
        articles = [
            _make_article(title="Article 1", link="https://example.com/1", article_id="1"),
            _make_article(title="Article 2", link="https://example.com/1", article_id="2"),
        ]
        result = dedup.filter_new(articles)
        assert len(result) == 1
        assert result[0].title == "Article 1"

    def test_filters_similar_titles(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({}, f)
            db_path = f.name

        dedup = Deduplicator(db_path=db_path)
        articles = [
            _make_article(title="Breaking: Stock Market Crashes Today", link="https://a.com/1"),
            _make_article(title="Breaking: Stock Market Crashes Today!", link="https://b.com/2"),
        ]
        result = dedup.filter_new(articles)
        assert len(result) == 1

    def test_allows_different_articles(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({}, f)
            db_path = f.name

        dedup = Deduplicator(db_path=db_path)
        articles = [
            _make_article(title="Python 4.0 Released", link="https://a.com/1"),
            _make_article(title="Rust 2.0 Announced", link="https://b.com/2"),
        ]
        result = dedup.filter_new(articles)
        assert len(result) == 2

    def test_persistence(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({}, f)
            db_path = f.name

        # First run
        dedup1 = Deduplicator(db_path=db_path)
        articles = [_make_article(title="Article A", link="https://example.com/a")]
        dedup1.filter_new(articles)
        dedup1.save()

        # Second run - same article should be filtered
        dedup2 = Deduplicator(db_path=db_path)
        result = dedup2.filter_new(articles)
        assert len(result) == 0

    def test_prune_old_entries(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
            json.dump({
                "//example.com/old": {"title": "Old", "seen_at": old_date},
            }, f)
            db_path = f.name

        dedup = Deduplicator(db_path=db_path)
        dedup.prune(window_days=7)
        assert len(dedup._seen) == 0

    def test_cross_source_keyword_dedup(self):
        """Same news story reported by different sources with different wording."""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({}, f)
            db_path = f.name

        dedup = Deduplicator(db_path=db_path)
        articles = [
            _make_article(
                title="Breaking: Critical CVE-2025-1234 Vulnerability Found in Apache Kafka",
                link="https://reuters.com/kafka-vuln",
            ),
            _make_article(
                title="[Updated] Critical CVE-2025-1234 Vulnerability Discovered in Apache Kafka - Bloomberg",
                link="https://bloomberg.com/kafka-vuln",
            ),
        ]
        result = dedup.filter_new(articles)
        assert len(result) == 1

    def test_different_topics_not_merged(self):
        """Articles about different topics should not be deduped."""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({}, f)
            db_path = f.name

        dedup = Deduplicator(db_path=db_path)
        articles = [
            _make_article(
                title="Google Releases New Kubernetes Security Patch v1.30",
                link="https://a.com/k8s",
            ),
            _make_article(
                title="Microsoft Announces Azure Price Reductions for 2025",
                link="https://b.com/azure",
            ),
        ]
        result = dedup.filter_new(articles)
        assert len(result) == 2

    def test_normalized_title_similarity(self):
        """Titles that differ only in prefix/suffix noise should be deduped."""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({}, f)
            db_path = f.name

        dedup = Deduplicator(db_path=db_path)
        articles = [
            _make_article(
                title="Python 3.14 Released with Major Performance Improvements",
                link="https://a.com/py1",
            ),
            _make_article(
                title="Breaking: Python 3.14 Released with Major Performance Improvements - Reuters",
                link="https://b.com/py2",
            ),
        ]
        result = dedup.filter_new(articles)
        assert len(result) == 1

    def test_corrupted_db_starts_fresh(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            f.write("not valid json{{{")
            db_path = f.name

        dedup = Deduplicator(db_path=db_path)
        assert dedup._seen == {}
