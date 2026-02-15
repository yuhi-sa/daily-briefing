"""Article summarization (pluggable strategy)."""

from __future__ import annotations

import json
import logging
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import replace

from .parser import Article

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (
    "以下のニュース記事のタイトルと概要を読んで、日本語で1〜2文の簡潔な要約を書いてください。"
    "要約のみを返してください。\n\n"
    "タイトル: {title}\n"
    "概要: {summary}"
)


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


class GeminiSummarizer(Summarizer):
    """Summarizes articles in Japanese using Google Gemini API (free tier)."""

    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _call_gemini(self, prompt: str) -> str | None:
        """Call Gemini API and return the generated text."""
        url = f"{self.ENDPOINT}?key={self.api_key}"
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            logger.exception("Gemini API call failed")
            return None

    def summarize(self, articles: list[Article]) -> list[Article]:
        logger.info("GeminiSummarizer: summarizing %d articles in Japanese", len(articles))
        results: list[Article] = []
        for article in articles:
            prompt = _PROMPT_TEMPLATE.format(title=article.title, summary=article.summary)
            ja_summary = self._call_gemini(prompt)
            if ja_summary:
                results.append(replace(article, summary=ja_summary))
            else:
                logger.warning("Fallback to original summary for: %s", article.title)
                results.append(article)
        return results


def get_summarizer(api_key: str | None = None) -> Summarizer:
    """Factory: returns GeminiSummarizer if API key is available, else Passthrough."""
    if api_key:
        return GeminiSummarizer(api_key=api_key)
    return PassthroughSummarizer()
