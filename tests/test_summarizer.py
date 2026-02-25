"""Tests for summarizer module — new quality improvements."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src.parser import Article
from src.summarizer import (
    GeminiSummarizer,
    _ArticleExtractor,
    _is_relevant_for_reader,
)


def _make_article(
    title: str = "Test Article",
    link: str = "https://example.com/article",
    summary: str = "A test summary.",
    category: str = "Engineering & Technology",
) -> Article:
    return Article(
        id=link,
        title=title,
        link=link,
        summary=summary,
        published=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source_name="Test Source",
        category=category,
        category_ja="テスト",
    )


# --- _ArticleExtractor tests -----------------------------------------


class TestArticleExtractor(unittest.TestCase):
    """Tests for the HTML article text extractor."""

    def test_extracts_article_tag_content(self):
        html = (
            "<html><body>"
            "<nav>Navigation here</nav>"
            "<article><p>Main article text.</p></article>"
            "<footer>Footer text</footer>"
            "</body></html>"
        )
        ext = _ArticleExtractor()
        ext.feed(html)
        text = ext.get_text()
        self.assertIn("Main article text.", text)
        self.assertNotIn("Navigation here", text)
        self.assertNotIn("Footer text", text)

    def test_extracts_main_tag_content(self):
        html = (
            "<html><body>"
            "<header>Site Header</header>"
            "<main><p>The main content.</p></main>"
            "<aside>Sidebar ads</aside>"
            "</body></html>"
        )
        ext = _ArticleExtractor()
        ext.feed(html)
        text = ext.get_text()
        self.assertIn("The main content.", text)
        self.assertNotIn("Site Header", text)
        self.assertNotIn("Sidebar ads", text)

    def test_skips_script_and_style(self):
        html = (
            "<html><body>"
            "<script>var x = 1;</script>"
            "<style>.foo { color: red; }</style>"
            "<p>Visible text.</p>"
            "</body></html>"
        )
        ext = _ArticleExtractor()
        ext.feed(html)
        text = ext.get_text()
        self.assertIn("Visible text.", text)
        self.assertNotIn("var x", text)
        self.assertNotIn("color", text)

    def test_fallback_to_all_text_when_no_article_tag(self):
        html = "<html><body><div><p>Some paragraph.</p></div></body></html>"
        ext = _ArticleExtractor()
        ext.feed(html)
        text = ext.get_text()
        self.assertIn("Some paragraph.", text)

    def test_nested_skip_tags(self):
        html = (
            "<nav><div><a href='/'>Home</a></div></nav>"
            "<p>Content outside nav.</p>"
        )
        ext = _ArticleExtractor()
        ext.feed(html)
        text = ext.get_text()
        self.assertIn("Content outside nav.", text)
        self.assertNotIn("Home", text)

    def test_empty_html(self):
        ext = _ArticleExtractor()
        ext.feed("")
        self.assertEqual(ext.get_text(), "")


# --- _is_relevant_for_reader tests ------------------------------------


class TestIsRelevantForReader(unittest.TestCase):
    """Tests for the ArXiv relevance pre-filter."""

    def test_non_arxiv_article_always_passes(self):
        article = _make_article(
            title="Traffic Simulation in Urban Areas",
            link="https://example.com/traffic",
            summary="A study about traffic patterns.",
        )
        self.assertTrue(_is_relevant_for_reader(article))

    def test_relevant_arxiv_article_passes(self):
        article = _make_article(
            title="LLM-Based Code Generation for Python",
            link="https://arxiv.org/abs/2602.12345",
            summary="We propose a new approach to code generation using language models.",
        )
        self.assertTrue(_is_relevant_for_reader(article))

    def test_irrelevant_arxiv_article_filtered(self):
        article = _make_article(
            title="Mobility-Aware Cache Framework for Traffic Simulation",
            link="https://arxiv.org/abs/2602.16727",
            summary="A framework for simulating human mobility patterns in urban areas.",
        )
        self.assertFalse(_is_relevant_for_reader(article))

    def test_arxiv_with_security_keyword_passes(self):
        article = _make_article(
            title="Novel Zero-Day Exploit Detection via Deep Learning",
            link="https://arxiv.org/abs/2602.99999",
            summary="Detecting zero-day vulnerabilities using neural networks.",
        )
        self.assertTrue(_is_relevant_for_reader(article))

    def test_arxiv_with_kubernetes_passes(self):
        article = _make_article(
            title="Autoscaling Microservices in Kubernetes Clusters",
            link="https://arxiv.org/abs/2602.11111",
            summary="We study autoscaling policies for Kubernetes deployments.",
        )
        self.assertTrue(_is_relevant_for_reader(article))

    def test_arxiv_medical_imaging_filtered(self):
        article = _make_article(
            title="Deep Learning for Medical Image Segmentation",
            link="https://arxiv.org/abs/2602.22222",
            summary="Segmenting tumors in MRI scans using convolutional networks.",
        )
        self.assertFalse(_is_relevant_for_reader(article))


# --- Post-processing tests --------------------------------------------


class TestPostProcessBriefing(unittest.TestCase):
    """Tests for deterministic post-processing quality checks."""

    def setUp(self):
        self.summarizer = GeminiSummarizer.__new__(GeminiSummarizer)

    def test_removes_banned_phrases(self):
        text = (
            "## 🔥 本日のハイライト\n\n"
            "- **テスト見出し**\n"
            "Kubernetesの新機能に注目が集まっています。"
            "v1.32でGateway APIがGA昇格した。\n"
            "📎 [記事](https://example.com)\n"
        )
        result = self.summarizer._post_process_briefing(text)
        self.assertNotIn("注目が集まっています", result)
        self.assertIn("v1.32", result)
        self.assertIn("Gateway API", result)

    def test_drops_section_without_links(self):
        text = (
            "## 🛠️ テクノロジー\n\n"
            "- テストコンテンツ（リンクなし）\n\n"
            "## 🔒 セキュリティ\n\n"
            "- CVE-2026-1234が悪用されている。\n"
            "📎 [記事](https://example.com/cve)\n"
        )
        result = self.summarizer._post_process_briefing(text)
        self.assertNotIn("テクノロジー", result)
        self.assertIn("セキュリティ", result)

    def test_keeps_future_section_without_links(self):
        text = (
            "## 🔮 今後の注目\n\n"
            "- 2026年3月1日: 重要イベント\n"
        )
        result = self.summarizer._post_process_briefing(text)
        self.assertIn("今後の注目", result)

    def test_market_section_data_insufficient_notice(self):
        text = (
            "## 📈 マーケット\n\n"
            "- 市場は概ね堅調に推移した。\n"
            "📎 [記事](https://example.com/market)\n"
        )
        result = self.summarizer._post_process_briefing(text)
        self.assertIn("データ不足", result)

    def test_market_section_with_numbers_no_notice(self):
        text = (
            "## 📈 マーケット\n\n"
            "- S&P500は0.6%上昇した。\n"
            "📎 [記事](https://example.com/market)\n"
        )
        result = self.summarizer._post_process_briefing(text)
        self.assertNotIn("データ不足", result)
        self.assertIn("0.6%", result)

    def test_cleans_up_double_spaces_after_phrase_removal(self):
        text = (
            "## 🔥 本日のハイライト\n\n"
            "- 新たな対策が急務です。パッチ適用を推奨する。\n"
            "📎 [記事](https://example.com)\n"
        )
        result = self.summarizer._post_process_briefing(text)
        self.assertNotIn("  ", result)  # No double spaces


# --- _select_articles pre-filter integration test ---------------------


class TestSelectArticlesPreFilter(unittest.TestCase):
    """Test that _select_articles pre-filters ArXiv articles."""

    @patch.object(GeminiSummarizer, "_call_gemini", return_value="[0, 1]")
    def test_prefilter_removes_irrelevant_arxiv(self, mock_gemini):
        summarizer = GeminiSummarizer(api_key="test-key")
        articles = [
            _make_article(
                title="Kubernetes v1.32 Gateway API",
                link="https://kubernetes.io/blog/v132",
            ),
            _make_article(
                title="Traffic Simulation Model for Urban Planning",
                link="https://arxiv.org/abs/2602.16727",
                summary="Simulating traffic in cities.",
            ),
            _make_article(
                title="LLM-Based Vulnerability Detection",
                link="https://arxiv.org/abs/2602.99999",
                summary="Using language models for security vulnerability detection.",
            ),
        ]
        summarizer._select_articles(articles)
        # The prompt sent to Gemini should not contain the traffic article
        call_args = mock_gemini.call_args[0][0]
        self.assertNotIn("Traffic Simulation", call_args)
        self.assertIn("Kubernetes", call_args)
        self.assertIn("Vulnerability Detection", call_args)

    @patch.object(GeminiSummarizer, "_call_gemini", return_value="[1]")
    def test_prefilter_index_maps_to_original_articles(self, mock_gemini):
        """Indices returned should map correctly to the original article list."""
        summarizer = GeminiSummarizer(api_key="test-key")
        articles = [
            _make_article(
                title="Kubernetes v1.32 Gateway API",
                link="https://kubernetes.io/blog/v132",
            ),
            _make_article(
                title="Traffic Simulation Model",
                link="https://arxiv.org/abs/2602.16727",
                summary="Simulating traffic in cities.",
            ),
            _make_article(
                title="LLM-Based Vulnerability Detection",
                link="https://arxiv.org/abs/2602.99999",
                summary="Using language models for security vulnerability detection.",
            ),
        ]
        # After pre-filter: [articles[0], articles[2]] (indices 0, 2 in original)
        # Gemini returns [1] meaning filtered index 1 = original index 2
        result = summarizer._select_articles(articles)
        self.assertEqual(result, [2])  # Must map to original index, not filtered

    @patch.object(GeminiSummarizer, "_call_gemini", return_value="[0]")
    def test_prefilter_no_arxiv_filtered_returns_correct_index(self, mock_gemini):
        """When no ArXiv articles are filtered, indices should be unchanged."""
        summarizer = GeminiSummarizer(api_key="test-key")
        articles = [
            _make_article(title="Article A", link="https://a.com/1"),
            _make_article(title="Article B", link="https://b.com/2"),
        ]
        result = summarizer._select_articles(articles)
        self.assertEqual(result, [0])


class TestArticleExtractorNesting(unittest.TestCase):
    """Test edge cases for content/skip tag nesting in _ArticleExtractor."""

    def test_article_inside_nav_is_skipped(self):
        """Content tag nested inside skip tag should not extract text."""
        html = (
            "<nav>"
            "<article><p>Should be skipped</p></article>"
            "</nav>"
            "<p>Visible text</p>"
        )
        ext = _ArticleExtractor()
        ext.feed(html)
        text = ext.get_text()
        self.assertNotIn("Should be skipped", text)
        self.assertIn("Visible text", text)

    def test_script_inside_article_is_skipped(self):
        html = (
            "<article>"
            "<p>Article text.</p>"
            "<script>var tracking = true;</script>"
            "<p>More article text.</p>"
            "</article>"
        )
        ext = _ArticleExtractor()
        ext.feed(html)
        text = ext.get_text()
        self.assertIn("Article text.", text)
        self.assertIn("More article text.", text)
        self.assertNotIn("tracking", text)


if __name__ == "__main__":
    unittest.main()
