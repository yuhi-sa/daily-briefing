# News Digest / ニュースダイジェスト

エンジニア兼投資家向けの自動ニュースダイジェストシステム。40以上のRSSフィードから記事を収集し、Google Gemini AIで日本語ブリーフィングを生成、Slackに毎日自動配信。

## Architecture

```
┌─ Collect (06:00 JST) ─────────────────────────────────┐
│  RSS Feeds (40+) → Parser → Dedup → Summarizer        │
│  → digests/YYYY-MM-DD.md + weekly_articles.json buffer │
└────────────────────────────────────────────────────────┘
         ↓
┌─ Digest (07:00 JST) ──────────────────────────────────────┐
│  Buffered articles → Gemini Stage 1 (select top articles)  │
│  → Full text fetch → Gemini Stage 2 (deep briefing)        │
│  → Gemini Stage 3 (quality refinement) → Post-processing   │
│  → Slack notification                                      │
└────────────────────────────────────────────────────────────┘
```

### 2-stage daily pipeline (GitHub Actions)

1. **Collect** (06:00 JST): 40以上のRSSフィードから並列取得 → URL正規化+タイトル類似度で重複排除 → `digests/YYYY-MM-DD.md`生成 → `data/weekly_articles.json`にバッファ → mainにコミット
2. **Digest** (07:00 JST): バッファ記事を読み込み → Geminiで2段階分析（トップ記事選定 → フルテキスト取得 → 深掘りブリーフィング） → 決定論的後処理（リンク検証、市場数値チェック、禁止フレーズ監視） → Slackに送信

## Briefing Sections

- **ハイライト**: 最重要ニュース3件を深掘り解説
- **AI・LLM**: モデルリリース、API変更、実用的なRAG/Agent手法
- **テクノロジー**: エンジニア向け技術動向
- **クラウド・DevOps**: AWS/GCP/Azure、CI/CD関連
- **データエンジニアリング**: データ基盤・パイプライン関連
- **セキュリティ**: CVE番号・深刻度・対応アクション付き
- **マーケット**: 具体的な指標数値（S&P500, NASDAQ, USD/JPY等）
- **今後の注目**: 決算発表、経済指標発表の予定

## Sources (40+ feeds)

| Category | Feeds |
|----------|-------|
| Engineering & Technology | ArXiv AI/ML, Hacker News, IEEE Spectrum AI, Ars Technica, MIT Technology Review, Google Developers Blog, Google AI Blog |
| Languages & Frameworks | Vercel, TypeScript, Go, Python Insider |
| Infrastructure | Kubernetes, CNCF, Kafka, MySQL, Redis, Cassandra |
| Data Engineering | dbt, Data Engineering Weekly, Databricks, AWS Big Data, Seattle Data Guy, Towards Data Science |
| Security | CISA, Krebs on Security, Schneier, The Hacker News, BleepingComputer, SANS ISC, Project Zero |
| Economy & Finance | Bloomberg Economics/Markets, Reuters, Investing.com |
| Investment & Markets | Seeking Alpha, Yahoo Finance, MarketWatch, CNBC Markets, Yahoo Finance Japan, Google News (日経平均, 米国株) |

## Usage

### Local (dry-run)

```bash
pip install -r requirements.txt

# 記事収集
python -m src.main collect --verbose

# ブリーフィング生成（Slack送信なし）
python -m src.main digest --dry-run
```

### Run tests

```bash
pytest tests/ -v
```

### GitHub Actions

1. リポジトリのSecretに `GEMINI_API_KEY` と `SLACK_WEBHOOK_URL` を設定
2. 毎日2つのワークフローが自動実行（06:00 / 07:00 JST）
3. `workflow_dispatch` で手動実行も可能

## Configuration

- `config/feeds.yml` — フィードの追加・削除・カテゴリ設定
- `SUMMARIZER_API_KEY` — Google Gemini APIキー（未設定時はLLM要約なし）
- `SLACK_WEBHOOK_URL` — Slack Incoming Webhook URL

## Tech Stack

- Python 3.12+
- Google Gemini API (要約・ブリーフィング生成)
- feedparser (RSS解析)
- Slack Incoming Webhook (通知配信)
- GitHub Actions (自動実行)
