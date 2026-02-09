# AI Daily Researcher

AI分野の最新情報を毎日自動収集し、HTML形式のレポートを生成してGitHub Pagesで公開するツール。

## レポート

https://ydev0927.github.io/airesercher/index.html

## セットアップ

### 前提条件

- [uv](https://docs.astral.sh/uv/) がインストール済み
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) がインストール済み（Claude Max プラン）

### インストール

```bash
git clone https://github.com/ydev0927/airesercher.git
cd airesercher
uv sync
```

### Teams通知の設定（任意）

Teams通知を有効にするには、プロジェクトルートに `.env` ファイルを作成してください。
このファイルは `.gitignore` に含まれているため、gitにはコミットされません。

```bash
cp .env.example .env
```

`.env` を編集してWebhook URLを設定:

```
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/xxxxx
```

未設定の場合、Teams通知はスキップされ、それ以外の処理は正常に動作します。

## 使い方

### 手動実行

```bash
# 本番実行（情報収集 → HTML生成 → git push → Teams通知）
uv run python daily_research.py

# テスト実行（情報収集 → HTML生成のみ、git push/Teams通知なし）
uv run python daily_research.py --test-html

# テスト実行（1カテゴリーのみ収集、結果をコンソール出力）
uv run python daily_research.py --test-collect
```

本番実行は当日分のレポートが既に存在する場合スキップされます。
再実行したい場合は `docs/YYYY-MM-DD.html` を削除してから実行してください。

### 実行時間の目安

- 全体: 約4分（3カテゴリー x 約1分）
- 1カテゴリー: 30-90秒

## 情報収集カテゴリーのカスタマイズ

`config.yaml` を編集することで、収集する情報の内容を自由に調整できます。

### カテゴリーの変更

```yaml
categories:
  ai_tech:
    name: "AI技術"                    # レポート上の表示名
    query: "AI・機械学習の最新技術動向" # Claude に渡す検索クエリ
  ai_security:
    name: "AIセキュリティ"
    query: "AIに関するセキュリティ（脅威、脆弱性、対策、規制）"
  ai_business:
    name: "AIビジネス"
    query: "AI関連のビジネス動向（企業、投資、M&A、活用事例）"
```

- **name**: HTMLレポートのセクション見出しに使われます
- **query**: Claude CLIに渡される検索指示です。自然言語で記述してください

### カテゴリーの追加・削除

カテゴリーは自由に追加・削除できます:

```yaml
categories:
  # 既存カテゴリーを変更
  ai_tech:
    name: "AI技術"
    query: "AI・機械学習の最新技術動向（新モデル、フレームワーク、論文）"

  # 新しいカテゴリーを追加
  cloud:
    name: "クラウド"
    query: "AWS、Azure、GCPのクラウドサービス最新動向"

  web_dev:
    name: "Web開発"
    query: "フロントエンド・バックエンドの最新フレームワークや技術トレンド"

  # カテゴリーを削除する場合は、該当ブロックを丸ごと消す
```

### その他の設定

```yaml
topics_per_category: 7       # 1カテゴリーあたりの収集トピック数
retry_max: 3                 # 失敗時のリトライ回数
retry_interval_sec: 1800     # リトライ間隔（秒）
claude_timeout_sec: 300      # Claude CLI のタイムアウト（秒）
```

## ファイル構成

```
airesercher/
├── daily_research.py    # メインスクリプト
├── config.yaml          # 収集カテゴリーと設定（編集可）
├── .env                 # Webhook URL等の秘密情報（git管理外）
├── .env.example         # .env のテンプレート
├── templates/
│   ├── report.html      # 日次レポートテンプレート
│   └── index.html       # トップページテンプレート
├── docs/                # GitHub Pages 公開ディレクトリ
│   ├── index.html       # トップページ（自動生成）
│   └── YYYY-MM-DD.html  # 日次レポート（自動生成）
└── logs/                # 実行ログ（git管理外）
```

## 技術スタック

- Python (uv)
- Claude CLI + WebSearch
- Jinja2 + Bootstrap 5
- GitHub Pages
- Microsoft Teams Webhook (Adaptive Card)
