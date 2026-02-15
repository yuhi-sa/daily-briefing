"""Markdown digest generator."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from .parser import Article

logger = logging.getLogger(__name__)


def format_digest(
    articles: list[Article],
    date: datetime | None = None,
    feed_stats: dict[str, bool] | None = None,
) -> str:
    """Generate a Markdown digest grouped by category."""
    if date is None:
        date = datetime.now(timezone.utc)

    date_str = date.strftime("%Y-%m-%d")
    lines: list[str] = []

    # Header
    lines.append(f"# デイリーニュースダイジェスト")
    lines.append(f"## {date_str}")
    lines.append("")

    if not articles:
        lines.append("本日の新着記事はありません。")
        lines.append("")
        return "\n".join(lines)

    # Group by category
    by_category: dict[str, list[Article]] = defaultdict(list)
    for article in articles:
        by_category[article.category].append(article)

    # Render each category
    for category, cat_articles in by_category.items():
        cat_ja = cat_articles[0].category_ja
        lines.append(f"## {cat_ja}")
        lines.append("")

        for i, article in enumerate(cat_articles, 1):
            lines.append(f"### {i}. {article.title}")
            lines.append(f"- **ソース**: {article.source_name}")
            lines.append(f"- **公開日時**: {article.published.strftime('%Y-%m-%d %H:%M UTC')}")
            lines.append(f"- **リンク**: {article.link}")
            if article.summary:
                lines.append(f"- **概要**: {article.summary}")
            lines.append("")

    # Footer
    total = len(articles)
    cat_count = len(by_category)
    lines.append("---")
    lines.append(f"*{total}件の記事、{cat_count}カテゴリ*")

    # Feed status
    if feed_stats:
        ok = sum(1 for v in feed_stats.values() if v)
        fail = sum(1 for v in feed_stats.values() if not v)
        lines.append(f"*フィード: {ok}件 成功、{fail}件 失敗*")
        if fail > 0:
            failed_names = [k for k, v in feed_stats.items() if not v]
            lines.append(f"*失敗フィード: {', '.join(failed_names)}*")

    lines.append("")
    return "\n".join(lines)
