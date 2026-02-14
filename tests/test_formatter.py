"""Tests for Markdown formatter module."""

from datetime import datetime, timezone

from src.formatter import format_digest
from src.parser import Article


def _make_article(
    title: str = "Test Article",
    category: str = "Test",
    category_ja: str = "テスト",
    source_name: str = "Test Feed",
) -> Article:
    return Article(
        id="1",
        title=title,
        link="https://example.com/article",
        summary="A test summary",
        published=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        source_name=source_name,
        category=category,
        category_ja=category_ja,
    )


class TestFormatDigest:
    def test_empty_articles(self):
        result = format_digest([])
        assert "No new articles today" in result
        assert "本日の新着記事はありません" in result

    def test_single_article(self):
        articles = [_make_article(title="AI Breakthrough")]
        result = format_digest(articles)
        assert "AI Breakthrough" in result
        assert "Test Feed" in result
        assert "https://example.com/article" in result
        assert "A test summary" in result

    def test_groups_by_category(self):
        articles = [
            _make_article(title="Economy News", category="Economy", category_ja="経済"),
            _make_article(title="Tech News", category="Tech", category_ja="技術"),
        ]
        result = format_digest(articles)
        assert "## Economy / 経済" in result
        assert "## Tech / 技術" in result

    def test_bilingual_header(self):
        articles = [_make_article()]
        result = format_digest(articles)
        assert "Daily News Digest" in result
        assert "デイリーニュースダイジェスト" in result

    def test_footer_counts(self):
        articles = [
            _make_article(title="A1", category="Cat1"),
            _make_article(title="A2", category="Cat2"),
            _make_article(title="A3", category="Cat1"),
        ]
        result = format_digest(articles)
        assert "3 articles from 2 categories" in result
        assert "3件の記事、2カテゴリ" in result

    def test_feed_stats_in_footer(self):
        articles = [_make_article()]
        stats = {"Feed A": True, "Feed B": False, "Feed C": True}
        result = format_digest(articles, feed_stats=stats)
        assert "2 succeeded, 1 failed" in result
        assert "Feed B" in result

    def test_date_formatting(self):
        articles = [_make_article()]
        date = datetime(2025, 6, 15, tzinfo=timezone.utc)
        result = format_digest(articles, date=date)
        assert "2025-06-15" in result
