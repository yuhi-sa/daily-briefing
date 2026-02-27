"""Tests for feed configuration validity."""

from src.feeds import load_config


class TestFeedsConfig:
    """Validate the feed configuration file."""

    def setup_method(self):
        self.config = load_config()
        self.feeds = self.config.feeds

    def test_feed_count_within_bounds(self):
        """Total feed count should be between 40 and 80."""
        assert 40 <= len(self.feeds) <= 80, f"Unexpected feed count: {len(self.feeds)}"

    def test_no_duplicate_feed_urls(self):
        """No two feeds should share the same URL."""
        urls = [f.url for f in self.feeds]
        assert len(urls) == len(set(urls)), "Duplicate feed URLs found"

    def test_all_categories_have_japanese_label(self):
        """Every feed should have a non-empty category_ja."""
        for feed in self.feeds:
            assert feed.category_ja, f"Feed '{feed.name}' missing category_ja"

    def test_all_feed_urls_are_valid_format(self):
        """Every feed URL should start with http:// or https://."""
        for feed in self.feeds:
            assert feed.url.startswith(("http://", "https://")), (
                f"Feed '{feed.name}' has invalid URL: {feed.url}"
            )

    def test_expected_categories_exist(self):
        """All expected categories should be present."""
        categories = {f.category for f in self.feeds}
        expected = {
            "Engineering & Technology",
            "AI & LLM",
            "Cloud & DevOps",
            "Japanese Tech",
            "Languages & Frameworks",
            "Infrastructure",
            "Data Engineering",
            "Security",
            "Economy & Finance",
            "Investment & Markets",
        }
        assert expected == categories, f"Missing categories: {expected - categories}"

    def test_high_volume_feeds_have_max_articles(self):
        """High-volume feeds like Bloomberg and Seeking Alpha should have max_articles set."""
        high_volume_feeds = {
            "Bloomberg Economics",
            "Bloomberg Markets",
            "Seeking Alpha Market News",
            "Seeking Alpha Articles",
            "Yahoo Finance",
            "Google News Nikkei 225",
            "Google News US Market JP",
            "Google News Kafka",
            "Google News Cassandra",
        }
        for feed in self.feeds:
            if feed.name in high_volume_feeds:
                assert feed.max_articles is not None, (
                    f"High-volume feed '{feed.name}' should have max_articles set"
                )
