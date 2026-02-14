# Daily News Digest / デイリーニュースダイジェスト

経済・エンジニアリングニュースを毎朝自動収集し、Markdownダイジェストを生成してPRとして投げるシステム。

## Architecture

```
RSS Feeds → Parser → Dedup → Summarizer → Formatter → PR
```

- **GitHub Actions cron** で毎朝 07:17 JST に自動実行（月〜金）
- **RSS** から記事取得（feedparser）
- **重複排除** URL正規化 + タイトル類似度チェック
- **Markdown** ダイジェスト生成 → `digests/YYYY-MM-DD.md`
- **PR** 自動作成（`gh` CLI）

## Sources

### Economy & Finance / 経済・金融
- Bloomberg Economics / Markets
- Reuters (via Google News)
- Investing.com

### Engineering & Technology / エンジニアリング・技術
- ArXiv AI/ML
- Hacker News (100+ points)
- IEEE Spectrum AI
- Ars Technica
- MIT Technology Review
- TechXplore

## Usage

### Local (dry-run)

```bash
pip install -r requirements.txt
python -m src.main --dry-run
```

### Run tests

```bash
pip install pytest
pytest tests/ -v
```

### GitHub Actions

1. パブリックリポジトリとしてプッシュ（Actions分数無制限）
2. `workflow_dispatch` で手動実行テスト
3. 毎朝自動でPRが作成される

## Configuration

`config/feeds.yml` でフィードの追加・削除が可能。

## Optional: LLM Summarization

`SUMMARIZER_API_KEY` 環境変数を設定すると、LLMベースの日本語要約が有効になる（未実装プレースホルダー）。
