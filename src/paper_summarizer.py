"""Structured paper summarization via Gemini API."""

from __future__ import annotations

import logging

from .paper_fetcher import Paper
from .summarizer import call_gemini

logger = logging.getLogger(__name__)

_PAPER_SUMMARY_PROMPT = """\
あなたはコンピュータサイエンスの研究論文を解説する専門家です。
以下の論文について、日本語で構造化された要約を作成してください。

## 論文情報
- タイトル: {title}
- 著者: {authors}
- 発表年: {year}
- 被引用数: {citation_count}
- 分野: {category_ja}

## アブストラクト
{abstract}

## 出力形式
以下の4つのセクションに分けて要約してください。各セクション3〜5文で簡潔に。

### 📖 背景と動機
この研究が取り組んだ問題と、なぜそれが重要だったのか。

### 🔬 手法・アプローチ
提案された手法やシステムの核心的なアイデア。

### 💡 主要な貢献
この論文が分野にもたらした具体的な成果や新規性。

### 🌍 影響と意義
この研究が後続の研究や実務に与えた影響。被引用数{citation_count}件の理由。

要約のみを返してください。冒頭の挨拶や末尾の締め文は不要です。
"""

_FALLBACK_TEMPLATE = """\
### 📖 背景と動機
{abstract_short}

### 🔬 手法・アプローチ
詳細はアブストラクトを参照してください。

### 💡 主要な貢献
被引用数 {citation_count} 件の高インパクト論文です。

### 🌍 影響と意義
{category_ja}分野における重要な研究です。
"""


def summarize_paper(paper: Paper, api_key: str | None) -> str:
    """Generate a structured summary of a paper using Gemini API.

    Falls back to a basic summary if no API key or on failure.
    """
    if not api_key:
        logger.info("No API key, using fallback summary")
        return _fallback_summary(paper)

    authors_str = ", ".join(paper.authors[:5])
    if len(paper.authors) > 5:
        authors_str += f" 他{len(paper.authors) - 5}名"

    abstract = paper.abstract or f"(アブストラクト未登録。タイトル「{paper.title}」から内容を推測してください)"

    prompt = _PAPER_SUMMARY_PROMPT.format(
        title=paper.title,
        authors=authors_str,
        year=paper.year or "不明",
        citation_count=paper.citation_count,
        category_ja=paper.category_ja,
        abstract=abstract,
    )

    result = call_gemini(prompt, api_key)
    if result:
        return result

    logger.warning("Gemini API failed, using fallback summary for: %s", paper.title)
    return _fallback_summary(paper)


def _fallback_summary(paper: Paper) -> str:
    """Generate a basic summary without LLM."""
    abstract_short = paper.abstract[:300] if paper.abstract else paper.title
    if len(paper.abstract or "") > 300:
        abstract_short += "..."

    return _FALLBACK_TEMPLATE.format(
        abstract_short=abstract_short,
        citation_count=paper.citation_count,
        category_ja=paper.category_ja,
    )
