"""Article summarization (pluggable strategy)."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from .parser import Article

logger = logging.getLogger(__name__)


class Summarizer(ABC):
    """Base class for article summarizers."""

    @abstractmethod
    def summarize(self, articles: list[Article]) -> list[Article]:
        """Return articles with potentially updated summaries."""


class PassthroughSummarizer(Summarizer):
    """Uses RSS description as-is (no external API calls)."""

    def summarize(self, articles: list[Article]) -> list[Article]:
        logger.info("PassthroughSummarizer: keeping original summaries for %d articles", len(articles))
        return articles


class LLMSummarizer(Summarizer):
    """Placeholder for LLM-based summarization (e.g., Google Gemini free tier).

    To enable, set SUMMARIZER_API_KEY environment variable and configure
    the endpoint. Falls back to passthrough on failure.
    """

    def __init__(self, api_key: str | None = None, endpoint: str | None = None):
        self.api_key = api_key
        self.endpoint = endpoint

    def summarize(self, articles: list[Article]) -> list[Article]:
        if not self.api_key:
            logger.warning("LLMSummarizer: no API key, falling back to passthrough")
            return articles

        # Placeholder: implement actual LLM API call here
        logger.info("LLMSummarizer: would summarize %d articles (not yet implemented)", len(articles))
        return articles


def get_summarizer(api_key: str | None = None) -> Summarizer:
    """Factory: returns LLMSummarizer if API key is available, else Passthrough."""
    if api_key:
        return LLMSummarizer(api_key=api_key)
    return PassthroughSummarizer()
