"""Tests for text_utils module."""

from src.text_utils import normalize_title, extract_keywords, keyword_similarity


class TestNormalizeTitle:
    def test_removes_breaking_prefix(self):
        assert "stock market" in normalize_title("Breaking: Stock Market Drops")

    def test_removes_update_prefix(self):
        assert "update" not in normalize_title("Update: Python 4.0 Released").split()[0]

    def test_removes_bracket_noise(self):
        result = normalize_title("[Updated] Security Patch Available")
        assert "updated" not in result.split()[:1]
        assert "security" in result

    def test_removes_source_suffix(self):
        result = normalize_title("Big Tech Earnings Beat Expectations - Bloomberg")
        assert "bloomberg" not in result

    def test_removes_punctuation(self):
        result = normalize_title("What's New in Python 3.13?")
        assert "?" not in result
        assert "'" not in result

    def test_lowercases(self):
        result = normalize_title("BREAKING NEWS TODAY")
        assert result == result.lower()

    def test_collapses_whitespace(self):
        result = normalize_title("  lots   of   spaces  ")
        assert "  " not in result

    def test_empty_string(self):
        assert normalize_title("") == ""

    def test_preserves_meaningful_words(self):
        result = normalize_title("Kubernetes 1.30 Release Candidate Available")
        assert "kubernetes" in result
        assert "130" in result or "release" in result


class TestExtractKeywords:
    def test_removes_stop_words(self):
        kw = extract_keywords("The new release of Python is here")
        assert "the" not in kw
        assert "is" not in kw
        assert "python" in kw
        assert "release" in kw

    def test_removes_short_words(self):
        kw = extract_keywords("Go is a great language")
        # "go" is 2 chars, filtered out
        assert "go" not in kw
        assert "great" in kw
        assert "language" in kw

    def test_empty_title(self):
        assert extract_keywords("") == set()

    def test_all_stop_words(self):
        assert extract_keywords("the and or but") == set()


class TestKeywordSimilarity:
    def test_identical_titles(self):
        score, overlap = keyword_similarity(
            "Python 3.13 Released with New Features",
            "Python 3.13 Released with New Features",
        )
        assert score == 1.0
        assert overlap > 0

    def test_similar_titles_from_different_sources(self):
        score, overlap = keyword_similarity(
            "Breaking: Critical CVE-2025-1234 in Apache Kafka - Reuters",
            "[Updated] Critical CVE-2025-1234 Found in Apache Kafka | Bloomberg",
        )
        assert score >= 0.6
        assert overlap >= 3

    def test_completely_different_titles(self):
        score, overlap = keyword_similarity(
            "Python 4.0 Released Today",
            "Stock Market Crashes Hard",
        )
        assert score < 0.3

    def test_empty_title(self):
        score, overlap = keyword_similarity("", "Some Title Here")
        assert score == 0.0
        assert overlap == 0

    def test_partial_overlap(self):
        score, overlap = keyword_similarity(
            "Google releases new Kubernetes security patch",
            "Google announces Kubernetes performance improvements",
        )
        assert 0.0 < score < 1.0
        assert overlap >= 2
