"""Shared text processing utilities for dedup and summarizer."""

from __future__ import annotations

import re

# Common English stop words for keyword extraction
STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "need", "must",
    "it", "its", "this", "that", "these", "those", "i", "you", "he", "she",
    "we", "they", "me", "him", "her", "us", "them", "my", "your", "his",
    "our", "their", "what", "which", "who", "whom", "how", "when", "where",
    "why", "not", "no", "nor", "so", "if", "then", "than", "too", "very",
    "just", "about", "above", "after", "before", "between", "into", "through",
    "during", "each", "few", "more", "most", "other", "some", "such", "only",
    "own", "same", "also", "as", "up", "out", "off", "over", "under", "again",
    "new", "says", "said", "report", "reports", "according", "via", "now",
    "here", "all", "any", "both", "every", "many", "much",
})

# Noise prefixes commonly added by news sources
_NOISE_PREFIX_RE = re.compile(
    r"^(?:breaking|update|updated|exclusive|opinion|analysis|report|watch|live"
    r"|developing|just\s+in|alert)\s*[:|\-]\s*",
    re.IGNORECASE,
)

# Source name suffixes like "- Bloomberg", "| Reuters", "— The Verge"
_SOURCE_SUFFIX_RE = re.compile(
    r"\s*[-–—|]\s*(?:bloomberg|reuters|cnbc|yahoo|the\s+verge|ars\s+technica"
    r"|techcrunch|wired|bbc|cnn|nyt|wsj|seeking\s+alpha|marketwatch"
    r"|investing\.com|the\s+hacker\s+news|bleepingcomputer)\s*$",
    re.IGNORECASE,
)

# Brackets like [Updated], (Exclusive), etc.
_BRACKET_NOISE_RE = re.compile(
    r"\[(?:updated?|breaking|exclusive|live|developing|video|podcast|opinion)\]",
    re.IGNORECASE,
)


def normalize_title(title: str) -> str:
    """Normalize a title for comparison.

    Removes noise prefixes, source suffixes, brackets, punctuation,
    and converts to lowercase.
    """
    text = _BRACKET_NOISE_RE.sub("", title)
    text = _NOISE_PREFIX_RE.sub("", text)
    text = _SOURCE_SUFFIX_RE.sub("", text)
    # Remove punctuation (keep alphanumeric and spaces)
    text = re.sub(r"[^\w\s]", "", text)
    # Collapse whitespace and lowercase
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def extract_keywords(title: str) -> set[str]:
    """Extract meaningful keywords from a title.

    Normalizes the title first, then filters out stop words and short tokens.
    """
    normalized = normalize_title(title)
    words = normalized.split()
    return {w for w in words if w not in STOP_WORDS and len(w) > 2}


def keyword_similarity(a: str, b: str) -> tuple[float, int]:
    """Compute Jaccard similarity and overlap count between two titles' keywords.

    Returns (jaccard_score, overlap_count).
    """
    kw_a = extract_keywords(a)
    kw_b = extract_keywords(b)
    if not kw_a or not kw_b:
        return 0.0, 0
    overlap = kw_a & kw_b
    union = kw_a | kw_b
    return len(overlap) / len(union), len(overlap)
