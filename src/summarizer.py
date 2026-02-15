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

_BATCH_PROMPT_TEMPLATE = (
    "以下の複数のニュース記事について、それぞれ日本語で1〜2文の簡潔な要約を書いてください。\n"
    "各要約は番号付きで返してください（例: 1. 要約文）。\n"
    "要約のみを返してください。\n\n"
    "{articles}"
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
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            logger.exception("Gemini API call failed")
            return None

    def _summarize_single(self, article: Article) -> Article:
        """Summarize a single article via Gemini API."""
        prompt = _PROMPT_TEMPLATE.format(title=article.title, summary=article.summary)
        ja_summary = self._call_gemini(prompt)
        if ja_summary:
            return replace(article, summary=ja_summary)
        logger.warning("Fallback to original summary for: %s", article.title)
        return article

    def _summarize_batch(self, batch: list[Article]) -> list[Article]:
        """Summarize a batch of articles in a single API call.

        Falls back to individual calls if the batch call fails.
        """
        articles_text = "\n".join(
            f"{i + 1}. タイトル: {a.title}\n   概要: {a.summary}"
            for i, a in enumerate(batch)
        )
        prompt = _BATCH_PROMPT_TEMPLATE.format(articles=articles_text)
        response = self._call_gemini(prompt)

        if response:
            summaries = self._parse_batch_response(response, len(batch))
            if summaries:
                results: list[Article] = []
                for article, summary in zip(batch, summaries):
                    results.append(replace(article, summary=summary))
                return results

        # Fallback: summarize individually
        logger.warning("Batch summarization failed, falling back to individual calls for %d articles", len(batch))
        return [self._summarize_single(a) for a in batch]

    @staticmethod
    def _parse_batch_response(response: str, expected_count: int) -> list[str] | None:
        """Parse numbered summaries from a batch response.

        Returns None if parsing fails or count doesn't match.
        """
        import re
        lines = response.strip().split("\n")
        summaries: list[str] = []
        current = ""
        for line in lines:
            match = re.match(r"^\d+[\.\)]\s*", line)
            if match:
                if current:
                    summaries.append(current.strip())
                current = line[match.end():]
            else:
                if current:
                    current += " " + line.strip()
        if current:
            summaries.append(current.strip())

        if len(summaries) == expected_count:
            return summaries
        logger.warning(
            "Batch response parse mismatch: expected %d, got %d",
            expected_count,
            len(summaries),
        )
        return None

    def summarize(self, articles: list[Article], batch_size: int = 5) -> list[Article]:
        logger.info("GeminiSummarizer: summarizing %d articles in Japanese (batch_size=%d)", len(articles), batch_size)
        results: list[Article] = []
        for i in range(0, len(articles), batch_size):
            batch = articles[i : i + batch_size]
            results.extend(self._summarize_batch(batch))
        return results

    def generate_briefing(self, articles: list[Article]) -> str | None:
        """Generate a curated weekly briefing for data/security engineers and JP/US stock investors."""
        article_list = "\n".join(
            f"- [{a.category}] {a.title}: {a.summary}" for a in articles
        )
        prompt = (
            "あなたは、データエンジニア・セキュリティエンジニア兼日本株・米国株の個人投資家向けの"
            "シニアニュースアナリストです。\n"
            "以下の今週のニュース記事一覧を分析し、日本語で**週次ブリーフィング**を作成してください。\n"
            "**技術情報がメイン、投資情報はサブ**という優先度で構成してください。\n"
            "単なる記事の羅列ではなく、**なぜ重要か、実務にどう影響するか**を深掘りしてください。\n\n"
            "## フォーマット（Markdown・絵文字活用）\n\n"
            "以下のセクション構成に従ってください:\n\n"
            "### `## 🔥 今週のハイライト`\n"
            "今週最も重要な3〜5件を厳選。各項目に:\n"
            "- 何が起きたか（1行）\n"
            "- **→ So What?**: なぜあなたに関係あるか（1行）\n\n"
            "### `## 🛠️ エンジニアリング・テクノロジー`\n"
            "**最も重要なセクション。** エンジニアとして押さえるべき内容を深掘り:\n"
            "- AI/ML の進展 → 実務での使い所、既存ワークフローへの影響\n"
            "- 新ツール・フレームワーク・OSS → 何が嬉しいのか、既存技術との差分\n"
            "- 注目論文 → 技術的に何が新しく、どこに応用できるか\n"
            "- インフラ・クラウド動向 → コスト・アーキテクチャへの影響\n\n"
            "### `## 📊 データエンジニアリング`\n"
            "データエンジニア向けの深掘り:\n"
            "- データパイプライン・基盤の新動向（dbt, Airflow, Spark, Flink等）\n"
            "- クラウドデータプラットフォーム更新（Snowflake, Databricks, BigQuery等）\n"
            "- データ品質・オブザーバビリティ・ガバナンスの話題\n"
            "- 該当記事がない場合はセクション省略可\n\n"
            "### `## 🔒 セキュリティ`\n"
            "セキュリティエンジニア向けの深掘り:\n"
            "- 今週の重大な脆弱性・CVE → 影響範囲と対応の緊急度\n"
            "- サプライチェーンセキュリティ、ゼロデイの動向\n"
            "- セキュリティツール・フレームワークの更新\n"
            "- 攻撃手法のトレンド → 防御側として何をすべきか\n"
            "- 該当記事がない場合はセクション省略可\n\n"
            "### `## 📈 投資・マーケット`\n"
            "日米株の個人投資家向け。**アクショナブルな情報**を重視:\n"
            "- 📌 **注目セクター・銘柄**: 今週のニュースから浮かぶ投資機会\n"
            "  - 例: 「AI電力需要増 → 再エネ/送配電関連に追い風」\n"
            "  - 例: 「〇〇社の決算サプライズ → 同業他社にも波及の可能性」\n"
            "- FRB/日銀の政策動向 → 金利・為替への影響\n"
            "- 具体的な数字（金利、指数、為替、PER等）を必ず含める\n"
            "- 日本株に波及しうるグローバルテーマがあれば言及\n\n"
            "### `## 🔮 来週の注目ポイント`\n"
            "来週に控えるイベント・発表・トレンドの予測を2〜3点:\n"
            "- 経済指標発表、企業決算、カンファレンス等\n"
            "- 今週の流れから来週起こりそうなこと\n\n"
            "## ルール\n"
            "- 各セクション見出しには指定の絵文字を使う\n"
            "- **技術セクション（🛠️📊🔒）を先に、投資セクション（📈）は後に**配置する\n"
            "- 表面的な要約に留まらず「**So What?**」「**Next Action?**」を常に意識\n"
            "- 複数記事を横断的に結びつけ、大きなトレンドやテーマを抽出する\n"
            "- 投資判断に関わる数字（金利、指数、為替、時価総額、PER等）は積極的に含める\n"
            "- 煽りや感情的な表現は避け、事実と分析に基づく\n"
            "- 該当トピックがないセクションは省略する\n"
            "- 各セクション3〜5項目を目安。質 > 量\n\n"
            f"## 今週の記事一覧（{len(articles)}件）\n\n"
            f"{article_list}"
        )
        logger.info("Generating weekly investor/engineer briefing")
        return self._call_gemini(prompt)


def generate_briefing(articles: list[Article], api_key: str | None = None) -> str:
    """Generate a curated briefing. Returns empty string if no API key."""
    if not api_key:
        return ""
    summarizer = GeminiSummarizer(api_key=api_key)
    result = summarizer.generate_briefing(articles)
    return result or ""


def get_summarizer(api_key: str | None = None) -> Summarizer:
    """Factory: returns GeminiSummarizer if API key is available, else Passthrough."""
    if api_key:
        return GeminiSummarizer(api_key=api_key)
    return PassthroughSummarizer()
