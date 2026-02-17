"""Tests for paper_summarizer module."""

from unittest.mock import patch

from src.paper_fetcher import Paper
from src.paper_summarizer import summarize_paper


def _make_paper(**kwargs) -> Paper:
    defaults = {
        "paper_id": "abc123",
        "title": "Attention Is All You Need",
        "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.",
        "authors": ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
        "year": 2017,
        "citation_count": 100000,
        "url": "https://www.semanticscholar.org/paper/abc123",
        "pdf_url": "https://example.com/paper.pdf",
        "category": "ai",
        "category_ja": "AI",
    }
    defaults.update(kwargs)
    return Paper(**defaults)


class TestSummarizePaper:
    def test_calls_gemini_with_paper_info(self):
        paper = _make_paper()
        with patch("src.paper_summarizer.call_gemini", return_value="要約テキスト") as mock:
            result = summarize_paper(paper, "test-api-key")

        assert result == "要約テキスト"
        mock.assert_called_once()
        prompt = mock.call_args[0][0]
        assert "Attention Is All You Need" in prompt
        assert "Ashish Vaswani" in prompt
        assert "2017" in prompt
        assert "100,000" in prompt or "100000" in prompt

    def test_fallback_on_api_failure(self):
        paper = _make_paper()
        with patch("src.paper_summarizer.call_gemini", return_value=None):
            result = summarize_paper(paper, "test-api-key")

        assert "📖 背景と動機" in result
        assert "dominant sequence transduction" in result

    def test_fallback_without_api_key(self):
        paper = _make_paper()
        result = summarize_paper(paper, None)

        assert "📖 背景と動機" in result
        assert "💡 主要な貢献" in result
        assert "100,000" in result or "100000" in result

    def test_truncates_long_author_list(self):
        paper = _make_paper(authors=[f"Author {i}" for i in range(10)])
        with patch("src.paper_summarizer.call_gemini", return_value="要約") as mock:
            summarize_paper(paper, "test-api-key")

        prompt = mock.call_args[0][0]
        assert "他5名" in prompt
