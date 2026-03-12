"""Article summarization (pluggable strategy)."""

from __future__ import annotations

import html
import json
import logging
import re
import time
import urllib.request
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace

from html.parser import HTMLParser as _StdHTMLParser

from .parser import Article
from .text_utils import keyword_similarity

logger = logging.getLogger(__name__)

_MAX_BODY_CHARS = 10000


class _ArticleExtractor(_StdHTMLParser):
    """HTML parser that extracts text, preferring <article>/<main> content."""

    _SKIP_TAGS: frozenset[str] = frozenset({
        "script", "style", "nav", "footer", "aside",
        "header", "noscript", "iframe", "svg", "form",
    })
    _CONTENT_TAGS: frozenset[str] = frozenset({"article", "main"})

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth: int = 0
        self._content_depth: int = 0
        self._content_parts: list[str] = []
        self._all_parts: list[str] = []

    # -- parser callbacks --------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in self._SKIP_TAGS:
            self._skip_depth += 1
        if t in self._CONTENT_TAGS and self._skip_depth == 0:
            self._content_depth += 1

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if t in self._CONTENT_TAGS and self._content_depth > 0:
            self._content_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        stripped = data.strip()
        if not stripped:
            return
        if self._content_depth > 0:
            self._content_parts.append(stripped)
        self._all_parts.append(stripped)

    # -- public API --------------------------------------------------------

    def get_text(self) -> str:
        """Return extracted text, preferring article/main content."""
        if self._content_parts:
            return " ".join(self._content_parts)
        return " ".join(self._all_parts)


def _fetch_page_text(url: str, timeout: int = 15) -> str:
    """Fetch a URL and return plain text extracted from HTML.

    Returns empty string on any failure.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "NewsDigestBot/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception:
        logger.debug("Failed to fetch %s", url)
        return ""

    # Strip HTML comments before parsing
    cleaned = re.sub(r"<!--.*?-->", "", raw, flags=re.S)

    # Try structured extraction via HTMLParser
    try:
        extractor = _ArticleExtractor()
        extractor.feed(cleaned)
        text = extractor.get_text()
    except Exception:
        # Fallback: regex approach
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", cleaned, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)

    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_MAX_BODY_CHARS]


def _fetch_pages_parallel(
    urls: list[str], max_workers: int = 6,
) -> dict[str, str]:
    """Fetch multiple URLs in parallel. Returns {url: text}."""
    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(_fetch_page_text, url): url for url in urls
        }
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                results[url] = future.result()
            except Exception:
                results[url] = ""
    return results

# Keywords from the reader's tech stack for relevance filtering
_READER_STACK_KEYWORDS = frozenset({
    # Reader's specific stack
    "typescript", "javascript", "next.js", "nextjs", "python", "golang",
    "spark", "kubernetes", "k8s", "kafka", "mysql", "cassandra", "redis",
    "hadoop", "athenz", "dbt", "airflow", "databricks", "bigquery", "athena",
    # Closely related infrastructure
    "docker", "container", "microservice", "data pipeline", "etl",
    "data warehouse", "iceberg", "parquet", "data lake",
    # AI/ML (practical applications relevant to engineers)
    "llm", "language model", "rag", "vector database", "embedding",
    "fine-tun", "prompt engineer", "code generation", "copilot",
    # AI/LLM (practical applications relevant to engineers) — EXPANDED
    "chatgpt", "gpt-4", "gpt-5", "claude", "llama", "mistral",
    "transformer", "diffusion", "llm agent", "ai agent", "function calling",
    "tool use", "mcp", "openai", "anthropic", "huggingface",
    # Security (always relevant)
    "vulnerability", "cve-", "exploit", "malware", "ransomware",
    "zero-day", "supply chain attack", "authentication",
    # Cloud & DevOps
    "aws", "gcp", "azure", "serverless", "terraform", "github action",
    # Cloud & DevOps — EXPANDED
    "cloudflare", "cdn", "edge computing",
    "ci/cd", "cicd", "gitops",
    "hashicorp", "consul", "vault", "nomad",
    "helm", "argocd", "flux",
    "eks", "gke", "aks",
    "aws lambda", "cloud functions", "cloud run",
    # Observability
    "prometheus", "grafana", "opentelemetry", "datadog",
    "jaeger", "tracing", "sli", "slo",
    # Additional languages/frameworks
    "rust", "rustlang", "react", "wasm", "webassembly",
    # Practical engineering topics
    "api gateway", "service mesh", "observability", "monitoring",
    "database", "caching", "queue", "streaming",
    "postgresql", "postgres", "grpc", "clickhouse", "duckdb",
})


def _is_relevant_for_reader(article: Article) -> bool:
    """Check if an article is relevant to the reader's tech stack.

    Non-ArXiv articles always pass through. ArXiv articles must mention
    at least one keyword from the reader's tech stack to be included.
    """
    if "arxiv.org" not in article.link:
        return True
    text = (article.title + " " + article.summary).lower()
    return any(kw in text for kw in _READER_STACK_KEYWORDS)

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


GEMINI_ENDPOINT_FLASH = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
GEMINI_ENDPOINT_PRO = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent"


def call_gemini(prompt: str, api_key: str, max_retries: int = 2, use_pro: bool = False) -> str | None:
    """Call Gemini API with retry logic and return the generated text.

    Retries up to max_retries times on failure with backoff.
    When use_pro=True, uses Gemini 2.5 Pro for higher quality output.
    """
    endpoint = GEMINI_ENDPOINT_PRO if use_pro else GEMINI_ENDPOINT_FLASH
    url = f"{endpoint}?key={api_key}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
    }).encode("utf-8")

    for attempt in range(max_retries + 1):
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
            if attempt < max_retries:
                delay = 5 * (attempt + 1)
                logger.warning(
                    "Gemini API call failed (attempt %d/%d), retrying in %ds",
                    attempt + 1, max_retries + 1, delay,
                )
                time.sleep(delay)
            else:
                logger.exception(
                    "Gemini API call failed after %d attempts", max_retries + 1,
                )
    return None


class GeminiSummarizer(Summarizer):
    """Summarizes articles in Japanese using Google Gemini API."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _call_gemini(self, prompt: str, use_pro: bool = False) -> str | None:
        """Call Gemini API and return the generated text."""
        return call_gemini(prompt, self.api_key, use_pro=use_pro)

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

    # ------------------------------------------------------------------
    # Two-stage briefing
    # ------------------------------------------------------------------

    def _select_articles(self, articles: list[Article]) -> list[int]:
        """Stage 1: Ask Gemini to pick the most important article indices.

        Returns indices into the *original* articles list.
        """
        # Pre-filter: remove ArXiv papers not relevant to reader's stack.
        # Keep a mapping from filtered-index → original-index so Gemini's
        # response can be translated back to the caller's list.
        original_indices = [
            i for i, a in enumerate(articles) if _is_relevant_for_reader(a)
        ]
        if len(original_indices) < len(articles):
            logger.info(
                "Pre-filter: removed %d irrelevant ArXiv articles (%d → %d)",
                len(articles) - len(original_indices),
                len(articles),
                len(original_indices),
            )
        if not original_indices:
            original_indices = list(range(len(articles)))  # Safety fallback
        filtered = [articles[i] for i in original_indices]

        article_list = "\n".join(
            f"{i}. [{a.category}] {a.title}: {a.summary}"
            for i, a in enumerate(filtered)
        )
        prompt = (
            "あなたはデータエンジニア・セキュリティエンジニア兼日本株・米国株の個人投資家向けの"
            "シニアニュースアナリストです。\n"
            "以下の記事一覧から、読者にとって本当に重要な記事を**12〜15件**選んでください。\n\n"
            "## 読者の技術スタック\n"
            "読者は以下の技術を日常的に使うデータエンジニア・セキュリティエンジニアです。"
            "これらに関連する記事は優先的に選んでください:\n"
            "- 言語: TypeScript/Next.js, Python, Go, Rust, Spark\n"
            "- インフラ: Kubernetes, Docker, Kafka, MySQL, Cassandra, Redis, Hadoop, Athenz\n"
            "- データ基盤: dbt, Airflow, Databricks, BigQuery, Athena\n"
            "- AI/LLM: RAG, Vector DB, Embedding, LLMエージェント, Function Calling\n"
            "- クラウド: AWS, GCP, Azure, Terraform, Cloudflare, GitHub Actions\n\n"
            "## 必須の選定配分\n"
            "以下のカテゴリごとに最低限の記事数を確保すること:\n"
            "- AI・LLM: 2〜3件（モデルリリース、API変更、実用的なRAG/Agent手法を優先。"
            "理論のみの論文は除外）\n"
            "- セキュリティ: 2〜4件（実際に悪用されているCVE、重大な脆弱性、攻撃キャンペーンのみ。"
            "一般論や啓蒙記事は除外）\n"
            "- マーケット/投資: 2〜3件（具体的数値・指標・決算を含む記事を優先。"
            "数字のない一般的な経済論評は除外）\n"
            "- クラウド・DevOps: 1〜2件（AWS/GCP/Azure/CI-CDの具体的サービス更新・障害情報）\n"
            "- データエンジニアリング: 1〜2件（dbt/Airflow/Spark/BigQuery等の具体的ツール更新・"
            "アーキテクチャ変更を含む記事）\n"
            "- テクノロジー全般: 2〜4件（読者スタックに直結する記事を優先）\n"
            "- 世間の話題: 0〜2件（テック以外でも社会的に大きなニュースがあれば含める。"
            "政治・経済・災害・国際情勢など、話題として知っておくべきもの）\n\n"
            "## 選定基準（優先順）\n"
            "1. **アクション可能か？**: 読者が読んだ後に「何かすべきこと」がある記事を最優先\n"
            "   （例: パッチ適用、API移行、設定変更、投資判断、ツール導入検討）\n"
            "2. 具体的な数値・メトリクス・CVE番号・バージョン番号を含む記事\n"
            "3. 投資判断に直結（マクロ指標の具体数値、決算、セクター動向）\n"
            "4. 世間で大きな話題になっている出来事（テック以外でも社会的インパクトが大きいもの）\n"
            "5. 日本語テック記事も選定対象（英語記事と同一トピックの場合は英語版を優先）\n\n"
            "## 除外基準（以下に該当する記事は選ばない）\n"
            "- 「〜が発表された」だけで具体的中身がない速報\n"
            "- 製品の宣伝・マーケティング色が強い記事\n"
            "- 既に広く知られている事実の繰り返し解説\n"
            "- 抽象的な「トレンド予測」や「〜が重要になる」系の記事\n"
            "- チュートリアルや入門記事（読者はシニアエンジニア）\n"
            "- 似たテーマの記事は最も情報量の多い1件だけ選ぶ\n\n"
            "## 出力形式\n"
            "選んだ記事の番号をJSON配列で返してください。それ以外のテキストは不要です。\n"
            "例: [0, 3, 5, 7, 9, 12, 15, 18]\n\n"
            f"## 記事一覧（{len(filtered)}件）\n\n"
            f"{article_list}"
        )
        logger.info("Stage 1: selecting important articles from %d candidates", len(filtered))
        response = self._call_gemini(prompt, use_pro=True)
        if not response:
            return []

        # Extract JSON array from response and map back to original indices
        try:
            match = re.search(r"\[[\d\s,]+\]", response)
            if match:
                indices = json.loads(match.group())
                valid = [
                    original_indices[i]
                    for i in indices
                    if 0 <= i < len(filtered)
                ]
                logger.info("Stage 1: selected %d articles", len(valid))
                return valid
        except (json.JSONDecodeError, ValueError):
            pass
        logger.warning("Stage 1: failed to parse selection response")
        return []

    _BRIEFING_MIN_CHARS = 200

    def generate_briefing(self, articles: list[Article]) -> str | None:
        """Generate a curated daily briefing using two-stage approach.

        Stage 1: Select important articles from RSS summaries.
        Stage 2: Fetch full text of selected articles, then generate deep briefing.
        Includes retry logic for empty or too-short results.
        """
        # Stage 1: Select
        selected_indices = self._select_articles(articles)
        if not selected_indices:
            logger.warning("Stage 1 returned no articles, falling back to summary-only briefing")
            selected = articles[:10]
        else:
            selected = [articles[i] for i in selected_indices]

        # Fetch full text of selected articles
        urls = [a.link for a in selected if a.link]
        logger.info("Stage 2: fetching full text for %d selected articles", len(urls))
        page_texts = _fetch_pages_parallel(urls)
        fetched = sum(1 for t in page_texts.values() if t)
        logger.info("Stage 2: successfully fetched %d/%d pages", fetched, len(urls))

        # Build enriched article list
        enriched_parts: list[str] = []
        for a in selected:
            body = page_texts.get(a.link, "")
            entry = (
                f"### [{a.category}] {a.title}\n"
                f"- URL: {a.link}\n"
                f"- RSS概要: {a.summary}\n"
            )
            if body:
                entry += f"- 記事本文（抜粋）: {body}\n"
            enriched_parts.append(entry)
        enriched_text = "\n".join(enriched_parts)

        # Stage 2: Generate briefing with full context
        prompt = (
            "あなたはベテランのテックジャーナリストです。データエンジニア・セキュリティエンジニア兼"
            "個人投資家（日米株）向けのデイリーブリーフィングを日本語で作成してください。\n\n"
            "## 読者\n"
            "- 技術スタック: TypeScript/Next.js, Python, Go, Rust, Spark, "
            "Kubernetes, Docker, Kafka, MySQL, Cassandra, Redis, Hadoop, Athenz, "
            "dbt, Airflow, Databricks, BigQuery, Athena\n"
            "- AI/LLM: RAG, Vector DB, LLMエージェント, Function Calling を実務で活用\n"
            "- クラウド: AWS, GCP, Azure, Terraform, Cloudflare\n"
            "- 読者のスタックに直結する話題は技術名を挙げて影響を具体的に述べる\n"
            "- 読者は日米の個別株・ETFに投資している。ニュースの投資インパクトを知りたい\n\n"
            "## 禁止表現（これらを使ったら書き直す）\n"
            "- 「〜に注目が集まっています」「〜が重要です」「〜が求められています」\n"
            "- 「〜の可能性があります」で終わる文\n"
            "- 「エンジニアは注意が必要です」「対策が急務です」\n"
            "- 「〜が進んでいます」「〜が加速しています」\n"
            "- 「今後の動向に注目」「引き続き注視」\n"
            "- 「〜が期待されます」「〜が見込まれます」（根拠なしの場合）\n"
            "- 同じ語尾の3連続（「〜した。〜した。〜した。」は不可）\n\n"
            "## 文体\n"
            "- 1トピック5〜8行。事実・背景・読者への影響を踏み込んで書く\n"
            "- 1文は40字以内。長い文は分割する\n"
            "- 基本構成: 事実(1〜2文) ＋ 技術的背景(1〜2文) ＋ 読者の業務への影響(1〜2文)\n"
            "- 全トピックの末尾に 📎 [記事タイトル](URL) 必須。例外なし\n"
            "- 複数の関連記事は1トピックにまとめてよい\n"
            "- 各バレットポイントには必ず1つ以上の具体的事実（数値、固有名詞、バージョン番号、"
            "CVE番号など）を含める。具体性のないバレットは書かない\n"
            "- **悪い例**: 「Kubernetesの新バージョンがリリースされた。新機能が追加されている。」"
            "（何の新機能か不明。読者が何をすべきかわからない）\n"
            "- **良い例**: 「Kubernetes v1.32でGateway APIがGA昇格。"
            "Ingress廃止ロードマップが前進し、v1.30以前のHPA manifestは移行が必要。」"
            "（バージョン、変更点、影響が明確）\n\n"
            "## セクション構成\n\n"
            "### `## 🔥 本日のハイライト`\n"
            "最重要の3件のみ。各セクションと重複しないこと。\n"
            "- **太字見出し**（10字前後）\n"
            "- 事実1文 + 意味1文\n"
            "- 📎 リンク\n\n"
            "### `## 🤖 AI・LLM`\n"
            "AI/ML関連。モデルリリース、API変更、実用的なRAG/Agent/ツール活用法のみ。最大3件。\n"
            "読者はLLMを実務で使うエンジニア。理論より実装・運用への影響を具体的に述べる。\n"
            "📎 リンク必須。\n\n"
            "### `## 🛠️ テクノロジー`\n"
            "読者の技術スタック（TypeScript, Python, Go, K8s, Kafka等）に直結するトピックのみ。\n"
            "ハイライトと重複しない別のトピック。最大3件。\n"
            "具体的なバージョン番号、API変更点、マイグレーション手順があれば明記。\n"
            "📎 リンク必須。\n\n"
            "### `## ☁️ クラウド・DevOps`\n"
            "AWS/GCP/Azure、CI/CD、IaC、CDN関連。該当なしなら省略。最大3件。\n"
            "サービスのバージョン、料金変更、アーキテクチャ変更の具体値を含める。\n"
            "📎 リンク必須。\n\n"
            "### `## 📊 データエンジニアリング`\n"
            "データ基盤・パイプライン関連。該当なしなら省略。最大3件。\n"
            "dbt/Airflow/Spark/BigQuery/Databricks等の具体名で影響を述べる。\n"
            "ツールのバージョン、設定変更点、パフォーマンス改善の具体数値を含める。\n"
            "📎 リンク必須。\n\n"
            "### `## 🔒 セキュリティ`\n"
            "脆弱性・攻撃動向。該当なしなら省略。**最大5件、影響度順**。\n"
            "各項目に必須: (1)CVE番号（あれば）, (2)影響を受けるソフトウェア・バージョン, "
            "(3)深刻度（Critical/High/Medium）, (4)具体的対応策（パッチ適用、設定変更等）\n"
            "類似の脆弱性は1トピックにまとめる。\n"
            "📎 リンク必須。\n\n"
            "### `## 🌍 世間の話題`\n"
            "テック以外で社会的インパクトが大きいニュース。該当なしなら省略。最大2件。\n"
            "政治・経済政策・国際情勢・災害・社会現象など。\n"
            "エンジニアや投資家としてどう関係するかを1文添える。\n"
            "📎 リンク必須。\n\n"
            "### `## 📈 マーケット`\n"
            "**記事本文から抽出した具体的数値のみ記載**。以下を可能な限り含む:\n"
            "- 株価指数（S&P500, NASDAQ, 日経225, TOPIX）の数値と前日比%\n"
            "- 為替（USD/JPY）の水準\n"
            "- 米国債利回り（10年）の水準\n"
            "- 個別銘柄の決算・株価変動（ティッカーシンボル付き）\n"
            "**記事に数値がない場合は「データ不足：該当記事に具体的数値の記載なし」と正直に書く。**\n"
            "数値を捏造・推測しないこと。\n"
            "📎 リンク必須。\n\n"
            "### `## 🔮 今後の注目`\n"
            "1〜2週間以内のイベント・予測を2〜3点。**具体的な日付を必ず明記**。\n"
            "漠然とした予測は書かない。\n\n"
            "## ルール\n"
            "- 記事本文を踏まえて書く（RSS概要だけに頼らない）\n"
            "- 「だから何？」を常に意識。事実の羅列は不可\n"
            "- 複数記事を横断的に結びつけてトレンドを抽出\n"
            "- ハイライトの記事は他セクションに書かない（重複厳禁）\n"
            "- 冒頭挨拶・末尾締め不要。セクションだけ出力\n"
            "- 記事に書かれていない数値や事実を捏造しない\n"
            "- 日本語ソースの記事は日本語のまま自然に組み込む\n"
            "- 日本語と英語で同じトピックの場合、1つにまとめて両方のリンクを付ける\n\n"
            f"## 厳選記事（{len(selected)}件・本文付き）\n\n"
            f"{enriched_text}"
        )
        logger.info("Stage 2: generating briefing with enriched content")
        draft = self._call_gemini(prompt, use_pro=True)
        if not draft:
            logger.error("Stage 2: Gemini returned no content")
            return None
        if len(draft) < self._BRIEFING_MIN_CHARS:
            logger.warning(
                "Stage 2: briefing unusually short (%d chars < %d minimum)",
                len(draft), self._BRIEFING_MIN_CHARS,
            )

        # Stage 3: LLM-based refinement then deterministic post-processing
        refined = self._refine_briefing(draft)
        return self._post_process_briefing(refined)

    def _refine_briefing(self, draft: str) -> str:
        """Stage 3: Deepen analysis and improve readability (LLM-only improvements)."""
        prompt = (
            "以下のデイリーブリーフィングの原稿を改善してください。\n\n"
            "## 改善方針（LLMでしかできないことに集中）\n"
            "1. 浅い分析を深める: 事実の羅列を「だから何？」まで踏み込んだ分析に書き換える\n"
            "   - 各トピックで「読者（AI/LLMを実務で活用するデータエンジニア・セキュリティエンジニア）の日常業務にどう影響するか」を\n"
            "     1文追加する\n"
            "2. 関連トピックの横断: 複数の記事に共通するトレンドがあれば言及する\n"
            "3. 語尾の単調さ解消: 同じ語尾が3回以上連続していたら変える\n"
            "4. 1文が40字を超えていたら分割する\n\n"
            "## 禁止事項\n"
            "- 情報を追加・捏造しない（原稿にある情報だけで改善）\n"
            "- セクション構造は変更しない\n"
            "- リンクの追加・削除はしない\n"
            "- 以下の表現は使わない: "
            "「注目が集まっています」「が重要です」「が求められています」「注意が必要です」"
            "「対策が急務です」「が進んでいます」「が加速しています」「今後の動向に注目」"
            "「引き続き注視」「が期待されます」「が見込まれます」\n\n"
            "改善後のブリーフィング全文のみを出力してください。\n\n"
            f"## 原稿\n\n{draft}"
        )
        logger.info("Stage 3: refining briefing (deepening analysis)")
        refined = self._call_gemini(prompt, use_pro=True)
        return refined or draft

    # ------------------------------------------------------------------
    # Deterministic post-processing (no LLM calls)
    # ------------------------------------------------------------------

    _BANNED_PHRASES = [
        "注目が集まっています",
        "注目が集まって",
        "が重要です",
        "が求められています",
        "の可能性があります",
        "注意が必要です",
        "対策が急務です",
        "が進んでいます",
        "が加速しています",
        "今後の動向に注目",
        "引き続き注視",
        "が期待されます",
        "が見込まれます",
    ]

    @staticmethod
    def _section_has_link(section_text: str) -> bool:
        """Check if a section contains at least one 📎 markdown link."""
        return bool(re.search(r"📎\s*\[.*?\]\(https?://.*?\)", section_text))

    @staticmethod
    def _market_section_has_numbers(section_text: str) -> bool:
        """Check if market section contains actual numeric data."""
        return bool(re.search(
            r"\d+[,.]?\d*\s*%|"           # percentages like 3.5%
            r"(?:S&P|NASDAQ|日経|TOPIX|USD/JPY|ドル円)\s*[\d,]+|"  # index values
            r"\$\s*[\d,]+|"                # dollar amounts
            r"[\d,]+\s*(?:円|ドル|bps)",   # yen/dollar/bps amounts
            section_text,
        ))

    def _post_process_briefing(self, text: str) -> str:
        """Deterministic quality checks applied after LLM refinement."""
        sections = re.split(r"(^## .+$)", text, flags=re.MULTILINE)
        result_parts: list[str] = []
        banned_found: list[str] = []

        i = 0
        while i < len(sections):
            part = sections[i]
            # Check if this is a section header
            if part.startswith("## "):
                header = part
                body = sections[i + 1] if i + 1 < len(sections) else ""
                combined = header + body

                # Drop sections without links (except 今後の注目 which may not need them)
                if "🔮" not in header and not self._section_has_link(combined):
                    logger.warning(
                        "Post-process: dropping section without links: %s",
                        header.strip(),
                    )
                    i += 2
                    continue

                # Market section: inject data-insufficient notice if no numbers
                if "マーケット" in header and not self._market_section_has_numbers(body):
                    body = "\nデータ不足：該当記事に具体的数値の記載なし\n" + body
                    logger.info("Post-process: added data-insufficient notice to market section")

                result_parts.append(header)
                result_parts.append(body)
                i += 2
            else:
                result_parts.append(part)
                i += 1

        processed = "".join(result_parts)

        # Remove banned phrases from text (sentence-level cleanup)
        for phrase in self._BANNED_PHRASES:
            if phrase in processed:
                processed = processed.replace(phrase, "")
                banned_found.append(f"'{phrase}'")
        if banned_found:
            logger.info(
                "Post-process: removed banned phrases: %s",
                ", ".join(banned_found),
            )
        # Clean up artifacts from phrase removal
        processed = re.sub(r"[ \t]{2,}", " ", processed)  # double spaces
        processed = re.sub(r"\n\s*-\s*\n", "\n", processed)  # empty bullet points
        processed = re.sub(r"\n{3,}", "\n\n", processed)  # excessive blank lines
        # Remove broken sentence fragments (very short text ending with 。)
        processed = re.sub(r"(?m)^(.{1,5}。)\s*$", "", processed)

        # Check for duplicate URLs across highlight and other sections
        highlight_urls: set[str] = set()
        in_highlight = False
        for line in processed.split("\n"):
            if "🔥" in line and line.startswith("## "):
                in_highlight = True
            elif line.startswith("## "):
                in_highlight = False
            if in_highlight:
                for url_match in re.finditer(r"\(https?://[^\s)]+\)", line):
                    highlight_urls.add(url_match.group())

        if highlight_urls:
            dup_count = 0
            for url in highlight_urls:
                # Count occurrences outside highlight section
                all_occurrences = processed.count(url)
                if all_occurrences > 1:
                    dup_count += 1
            if dup_count:
                logger.warning(
                    "Post-process: %d URL(s) appear in both highlights and other sections",
                    dup_count,
                )

        return processed


def _cluster_articles(
    articles: list[Article], sim_threshold: float = 0.5,
) -> list[list[int]]:
    """Group articles into topic clusters using Union-Find on keyword similarity.

    Returns a list of clusters, each cluster is a list of article indices.
    """
    n = len(articles)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        for j in range(i + 1, n):
            jaccard, overlap = keyword_similarity(articles[i].title, articles[j].title)
            if jaccard >= sim_threshold and overlap >= 2:
                union(i, j)

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        clusters.setdefault(root, []).append(i)
    return list(clusters.values())


def _deduplicate_clusters(
    articles: list[Article], clusters: list[list[int]],
) -> list[Article]:
    """From each cluster, keep only the article with the longest summary."""
    result: list[Article] = []
    for cluster in clusters:
        best_idx = max(cluster, key=lambda i: len(articles[i].summary))
        result.append(articles[best_idx])
    return result


def generate_briefing(articles: list[Article], api_key: str | None = None) -> str:
    """Generate a curated briefing. Returns empty string if no API key."""
    if not api_key:
        logger.warning("No API key provided, skipping briefing generation")
        return ""
    if not articles:
        logger.warning("No articles provided, skipping briefing generation")
        return ""

    # Topic dedup: cluster similar articles and keep the best from each cluster
    clusters = _cluster_articles(articles)
    deduped = _deduplicate_clusters(articles, clusters)
    multi_clusters = sum(1 for c in clusters if len(c) > 1)
    logger.info(
        "Topic clustering: %d articles → %d unique topics (%d clusters merged)",
        len(articles), len(deduped), multi_clusters,
    )

    summarizer = GeminiSummarizer(api_key=api_key)
    result = summarizer.generate_briefing(deduped)
    if not result:
        logger.error(
            "Briefing generation failed after all retries for %d articles",
            len(deduped),
        )
    return result or ""


def get_summarizer(api_key: str | None = None) -> Summarizer:
    """Factory: returns GeminiSummarizer if API key is available, else Passthrough."""
    if api_key:
        return GeminiSummarizer(api_key=api_key)
    return PassthroughSummarizer()
