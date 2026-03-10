# ニュースレター化フォーマット提案

## 現在の出力形式

### Collect出力（`digests/YYYY-MM-DD.md`）

GitHub ActionsのCollectステージ（06:00 JST）が生成するMarkdownファイル。構造：

```markdown
# Daily News Digest / デイリーニュースダイジェスト
## 2026-02-19

## Engineering & Technology / エンジニアリング・技術

### 1. 記事タイトル
- **Source**: ソース名
- **Published**: 2026-02-19 16:00 UTC
- **Link**: https://...
- **Summary**: Gemini日本語要約テキスト

---
_Digest generated at YYYY-MM-DD HH:MM UTC | N articles from M categories_
```

カテゴリ: Engineering & Technology / Languages & Frameworks / Infrastructure / Data Engineering / Security / Economy & Finance / Investment & Markets

### Digest PRのbody（深掘りブリーフィング）

07:00 JSTのDigest PRはより構造化されたブリーフィングをPR bodyに含む：
- **ハイライト**: 最重要ニュース3件の深掘り解説
- **テクノロジー**: エンジニア向け技術動向
- **データエンジニアリング**: データ基盤・パイプライン関連
- **セキュリティ**: CVE番号・深刻度・対応アクション付き
- **マーケット**: S&P500, NASDAQ, USD/JPY, 金価格等の具体的数値
- **今後の注目**: 決算発表・経済指標発表の予定

---

## Beehiiv連携設計案

### 出力形式の変更点（Markdown → HTML変換）

現在のMarkdown出力をBeehiiv向けHTMLに変換するアダプターを追加する。変更範囲は最小限とし、既存の`formatter.py`は変更しない。

#### 変更方針
- `src/newsletter_formatter.py` を新規追加（既存formatter.pyは保持）
- Markdownの各セクションをHTML `<div>` ブロックに変換
- BeehiivのAPIが受け付けるHTML形式に準拠

#### HTMLテンプレート構造

```html
<div class="briefing-header">
  <h1>🤖 AI Daily Briefing</h1>
  <p>{date} | {article_count}件のニュース</p>
</div>

<div class="section highlight">
  <h2>📌 今日のハイライト</h2>
  <!-- 最重要ニュース3件 -->
</div>

<div class="section technology">
  <h2>💻 テクノロジー</h2>
</div>

<div class="section security">
  <h2>🔒 セキュリティ</h2>
</div>

<div class="section market">
  <h2>📈 マーケット</h2>
</div>

<div class="footer">
  <p>Blog: <a href="https://yuhi-sa.github.io">yuhi-sa.github.io</a> |
     GitHub: <a href="https://github.com/yuhi-sa">@yuhi-sa</a></p>
  <!-- Beehiivが配信停止リンクを自動付与 -->
</div>
```

### 自動投稿API: Beehiiv API v2

- **エンドポイント**: `POST /publications/{pub_id}/posts`
- **認証**: APIキー（TODO: Beehiivダッシュボードで取得 → GitHub Secret `BEEHIIV_API_KEY` に設定）
- **Publication ID**: TODO: Beehiivダッシュボードで確認 → `BEEHIIV_PUB_ID` に設定

#### APIリクエスト例

```python
import requests

def publish_to_beehiiv(html_content: str, subject: str, date_str: str) -> dict:
    # TODO: 環境変数から取得
    api_key = os.environ["BEEHIIV_API_KEY"]
    pub_id = os.environ["BEEHIIV_PUB_ID"]

    response = requests.post(
        f"https://api.beehiiv.com/v2/publications/{pub_id}/posts",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "subject": subject,
            "content": {"html": html_content},
            "status": "draft",  # まずdraftで確認してからpublishに変更
            "audience": "free",
            "send_at": None,  # 即時配信の場合はNone
        },
    )
    return response.json()
```

### cronスケジュール調整案

現在のGitHub Actionsワークフローに`newsletter`ステップを追加：

```yaml
# .github/workflows/newsletter.yml（新規追加案）
name: Newsletter Publish
on:
  schedule:
    - cron: '30 22 * * 0-4'  # 07:30 JST（月〜金）、Digest PR後30分
  workflow_dispatch:

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Publish to Beehiiv
        env:
          BEEHIIV_API_KEY: ${{ secrets.BEEHIIV_API_KEY }}
          BEEHIIV_PUB_ID: ${{ secrets.BEEHIIV_PUB_ID }}
        run: python -m src.main newsletter  # TODO: mainにnewsletterサブコマンド追加
```

---

## ニュースレターテンプレート

### Subject line
```
【AIブリーフィング】{date} — 今日の注目トピック{N}件
```
例: `【AIブリーフィング】2026-03-10 — 今日の注目トピック12件`

### Header
```
AI Daily Briefing by yuhi-sa
─────────────────────────────
エンジニア・投資家向け毎朝のAI＆技術ニュース要約
```

### Body
現在の`digests/YYYY-MM-DD.md`の内容をそのまま活用可能（Markdown→HTML変換のみ）。
Digest PRのブリーフィング本文（ハイライト・マーケット情報含む）の方が価値が高いため、
そちらをメインコンテンツとして採用することを推奨。

### Footer
```html
<hr>
<p>
  <a href="https://yuhi-sa.github.io">Blog</a> |
  <a href="https://github.com/yuhi-sa">GitHub</a>
</p>
<!-- 配信停止リンク: Beehiivが自動付与 -->
```

---

## 実装ステップ（優先順）

1. **TODO（殿の作業）**: BeehiivアカウントでAPIキーとPublication IDを取得
2. GitHub SecretにBEEHIIV_API_KEYとBEEHIIV_PUB_IDを追加
3. `src/newsletter_formatter.py`でMarkdown→HTML変換関数を実装
4. `src/main.py`に`newsletter`サブコマンドを追加
5. `.github/workflows/newsletter.yml`を新規作成
6. draftモードで動作確認後、`status: "confirmed"`に変更して本番稼働

## 注意事項

- 既存の`collect` / `digest` / `paper`パイプラインには一切変更を加えない
- まずdraftステータスで投稿し、フォーマットを目視確認してから自動publishに切り替える
- Beehiiv無料プランの制限（月2,500subscribers、月1メール）を事前確認
