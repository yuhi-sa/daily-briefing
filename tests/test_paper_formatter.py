"""Tests for paper_formatter module."""

from src.paper_fetcher import Paper
from src.paper_formatter import format_paper_pr_body


def _make_paper(**kwargs) -> Paper:
    defaults = {
        "paper_id": "abc123",
        "title": "MapReduce: Simplified Data Processing on Large Clusters",
        "abstract": "MapReduce is a programming model...",
        "authors": ["Jeffrey Dean", "Sanjay Ghemawat"],
        "year": 2004,
        "citation_count": 25000,
        "url": "https://www.semanticscholar.org/paper/abc123",
        "pdf_url": "https://example.com/paper.pdf",
        "category": "distributed_systems",
        "category_ja": "大規模分散処理",
    }
    defaults.update(kwargs)
    return Paper(**defaults)


class TestFormatPaperPrBody:
    def test_contains_title_and_metadata(self):
        paper = _make_paper()
        result = format_paper_pr_body(paper, "要約テキスト", "2026-02-17")

        assert "MapReduce" in result
        assert "Jeffrey Dean" in result
        assert "2004" in result
        assert "25,000" in result
        assert "大規模分散処理" in result
        assert "2026-02-17" in result

    def test_contains_summary(self):
        paper = _make_paper()
        result = format_paper_pr_body(paper, "これはテスト要約です", "2026-02-17")
        assert "これはテスト要約です" in result

    def test_includes_pdf_link(self):
        paper = _make_paper(pdf_url="https://example.com/paper.pdf")
        result = format_paper_pr_body(paper, "要約", "2026-02-17")
        assert "https://example.com/paper.pdf" in result
        assert "PDF" in result

    def test_no_pdf_link_when_none(self):
        paper = _make_paper(pdf_url=None)
        result = format_paper_pr_body(paper, "要約", "2026-02-17")
        assert "PDF" not in result

    def test_includes_semantic_scholar_link(self):
        paper = _make_paper()
        result = format_paper_pr_body(paper, "要約", "2026-02-17")
        assert "https://www.semanticscholar.org/paper/abc123" in result

    def test_truncates_long_author_list(self):
        paper = _make_paper(authors=[f"Author {i}" for i in range(10)])
        result = format_paper_pr_body(paper, "要約", "2026-02-17")
        assert "他5名" in result

    def test_unknown_year(self):
        paper = _make_paper(year=None)
        result = format_paper_pr_body(paper, "要約", "2026-02-17")
        assert "不明" in result
