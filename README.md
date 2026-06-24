# 📈 Economics Bot

毎朝7時（JST）に経済・金融ニュースを自動収集し、Claude AI で重要度順にランキングして HTML ページを生成・公開するボットです。

## 機能

| 機能 | 詳細 |
|---|---|
| ニュース収集 | News API で日本語優先・24時間分を取得 |
| AI ランキング | Claude Sonnet (claude-sonnet-4-6) で重要度順に上位20件を選出 |
| HTML 生成 | `economics_news.html` を自動生成 |
| 自動実行 | GitHub Actions で毎朝 7:00 JST に実行・コミット |

### 対象カテゴリ

- 日経平均
- 米国経済
- FRB 金利
- 株価指数
- 市場動向
- 金融ニュース / 為替レート

---

## セットアップ

### 1. GitHub Secrets を登録

リポジトリの **Settings > Secrets and variables > Actions** で以下を追加：

| Secret 名 | 取得元 |
|---|---|
| `NEWS_API_KEY` | [newsapi.org](https://newsapi.org)（無料プランあり） |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |

### 2. GitHub Pages で公開（任意）

**Settings > Pages** で `main` ブランチのルート `/` を指定すると、以下 URL で閲覧できます：

```
https://briancool44.github.io/economics-bot/economics_news.html
```

---

## ローカル実行

```bash
# 依存パッケージをインストール
pip install -r requirements.txt

# .env を作成
cp .env.example .env
# .env に実際のキーを記入

# 実行
python fetch_economics.py
```

---

## ファイル構成

```
economics-bot/
├── fetch_economics.py             # メインスクリプト
├── economics_news.html            # 生成される HTML（自動更新）
├── requirements.txt
├── .env.example                   # 環境変数テンプレート
├── README.md
└── .github/
    └── workflows/
        └── daily_economics.yml    # GitHub Actions（毎朝7時 JST）
```

---

## スケジュール

| 時刻 | 処理 |
|---|---|
| 07:00 JST (UTC 22:00 前日) | News API でニュース収集 |
| | Claude でランキング（上位20件） |
| | `economics_news.html` を生成・コミット |

`workflow_dispatch` で手動実行も可能です。
