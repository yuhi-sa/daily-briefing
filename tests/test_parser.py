"""Tests for RSS parser module."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from time import mktime

from src.parser import Article, _strip_html, _parse_date, fetch_articles
from src.feeds import FeedSource


class TestStripHtml:
    def test_removes_tags(self):
        assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_decodes_entities(self):
        assert _strip_html("&amp; &lt; &gt;") == "& < >"

    def test_collapses_whitespace(self):
        assert _strip_html("  hello   world  ") == "hello world"

    def test_empty_string(self):
        assert _strip_html("") == ""


class TestParseDate:
    def test_with_published_parsed(self):
        entry = MagicMock()
        entry.published_parsed = (2025, 1, 15, 10, 30, 0, 2, 15, 0)
        entry.updated_parsed = None
        result = _parse_date(entry)
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15

    def test_fallback_to_now(self):
        entry = MagicMock()
        entry.published_parsed = None
        entry.updated_parsed = None
        result = _parse_date(entry)
        assert isinstance(result, datetime)


class TestFetchArticles:
    def _make_source(self) -> FeedSource:
        return FeedSource(
            name="Test Feed",
            url="https://example.com/rss",
            category="Test",
            category_ja="テスト",
        )

    @patch("src.parser.feedparser.parse")
    def test_successful_fetch(self, mock_parse):
        mock_entry = MagicMock()
        mock_entry.get = lambda key, default="": {
            "title": "Test Article",
            "link": "https://example.com/article",
            "summary": "A summary",
            "id": "article-1",
        }.get(key, default)
        mock_entry.published_parsed = (2025, 1, 15, 10, 0, 0, 2, 15, 0)
        mock_entry.updated_parsed = None

        mock_parse.return_value = MagicMock(
            bozo=False,
            entries=[mock_entry],
        )

        source = self._make_source()
        articles = fetch_articles(source, max_articles=5)

        assert len(articles) == 1
        assert articles[0].title == "Test Article"
        assert articles[0].link == "https://example.com/article"
        assert articles[0].source_name == "Test Feed"
        assert articles[0].category == "Test"

    @patch("src.parser.feedparser.parse")
    def test_bozo_with_no_entries_returns_empty(self, mock_parse):
        mock_parse.return_value = MagicMock(
            bozo=True,
            bozo_exception=Exception("parse error"),
            entries=[],
        )
        source = self._make_source()
        articles = fetch_articles(source)
        assert articles == []

    @patch("src.parser.feedparser.parse")
    def test_exception_returns_empty(self, mock_parse):
        mock_parse.side_effect = Exception("network error")
        source = self._make_source()
        articles = fetch_articles(source)
        assert articles == []

    @patch("src.parser.feedparser.parse")
    def test_respects_max_articles(self, mock_parse):
        entries = []
        for i in range(20):
            entry = MagicMock()
            entry.get = lambda key, default="", idx=i: {
                "title": f"Article {idx}",
                "link": f"https://example.com/{idx}",
                "summary": "Summary",
                "id": f"id-{idx}",
            }.get(key, default)
            entry.published_parsed = (2025, 1, 15, 10, 0, 0, 2, 15, 0)
            entry.updated_parsed = None
            entries.append(entry)

        mock_parse.return_value = MagicMock(bozo=False, entries=entries)
        source = self._make_source()
        articles = fetch_articles(source, max_articles=5)
        assert len(articles) == 5

    @patch("src.parser.feedparser.parse")
    def test_max_age_hours_filters_old_articles(self, mock_parse):
        """Articles older than max_age_hours are skipped."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(hours=72)
        fresh_time = now - timedelta(hours=1)

        old_tt = old_time.timetuple()
        fresh_tt = fresh_time.timetuple()

        old_entry = MagicMock()
        old_entry.get = lambda key, default="": {
            "title": "Old Article",
            "link": "https://example.com/old",
            "summary": "Old summary",
            "id": "old-1",
        }.get(key, default)
        old_entry.published_parsed = old_tt
        old_entry.updated_parsed = None

        fresh_entry = MagicMock()
        fresh_entry.get = lambda key, default="": {
            "title": "Fresh Article",
            "link": "https://example.com/fresh",
            "summary": "Fresh summary",
            "id": "fresh-1",
        }.get(key, default)
        fresh_entry.published_parsed = fresh_tt
        fresh_entry.updated_parsed = None

        mock_parse.return_value = MagicMock(
            bozo=False,
            entries=[old_entry, fresh_entry],
        )

        source = self._make_source()
        articles = fetch_articles(source, max_articles=10, max_age_hours=48)

        assert len(articles) == 1
        assert articles[0].title == "Fresh Article"

    @patch("src.parser.feedparser.parse")
    def test_no_max_age_keeps_all(self, mock_parse):
        """Without max_age_hours, all articles are kept."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(hours=72)
        old_tt = old_time.timetuple()

        entry = MagicMock()
        entry.get = lambda key, default="": {
            "title": "Old Article",
            "link": "https://example.com/old",
            "summary": "Old summary",
            "id": "old-1",
        }.get(key, default)
        entry.published_parsed = old_tt
        entry.updated_parsed = None

        mock_parse.return_value = MagicMock(
            bozo=False,
            entries=[entry],
        )

        source = self._make_source()
        articles = fetch_articles(source, max_articles=10, max_age_hours=None)
        assert len(articles) == 1
