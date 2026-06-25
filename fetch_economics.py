"""
Economics Bot - 経済・金融ニュース自動収集・配信スクリプト
毎朝7時(JST)に経済ニュースを取得し、Claudeで重要度順にランキングしてHTMLを生成する
"""

import os
import json
import requests
import anthropic
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

JST = timezone(timedelta(hours=9))

JAPANESE_QUERIES = [
    "日経平均",
    "米国経済",
    "FRB 金利",
    "株価指数",
    "市場動向",
    "金融ニュース",
    "為替レート",
    "インフレ 経済",
]

ENGLISH_QUERIES = [
    "Nikkei stock market Japan",
    "US economy Federal Reserve interest rates",
    "stock market index S&P",
    "financial markets global",
    "inflation economy",
]


def fetch_news(query: str, language: str, page_size: int = 10) -> list[dict]:
    """News API で指定クエリのニュースを取得する"""
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "language": language,
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "apiKey": NEWS_API_KEY,
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "ok":
            print(f"  [WARN] API エラー ({query}): {data.get('message', '不明')}")
            return []
        return data.get("articles", [])
    except requests.exceptions.Timeout:
        print(f"  [WARN] タイムアウト: {query}")
        return []
    except requests.exceptions.HTTPError as e:
        print(f"  [WARN] HTTP エラー ({query}): {e}")
        return []
    except Exception as e:
        print(f"  [WARN] 取得失敗 ({query}): {e}")
        return []


def fetch_all_news() -> list[dict]:
    """全クエリのニュースを収集し、重複を除去して返す（日本語優先）"""
    all_articles: list[dict] = []
    seen_urls: set[str] = set()

    print("▶ 日本語ニュースを取得中...")
    for query in JAPANESE_QUERIES:
        articles = fetch_news(query, language="ja", page_size=10)
        added = 0
        for article in articles:
            url = article.get("url", "")
            title = article.get("title", "")
            if not url or not title or url in seen_urls:
                continue
            # ゴミ記事を除外（タイトルが [Removed] など）
            if title.strip() in ("[Removed]", ""):
                continue
            seen_urls.add(url)
            article["_query"] = query
            article["_lang"] = "ja"
            all_articles.append(article)
            added += 1
        print(f"  '{query}': {added}件追加")

    print("▶ 英語ニュースを取得中（補足）...")
    for query in ENGLISH_QUERIES:
        articles = fetch_news(query, language="en", page_size=5)
        added = 0
        for article in articles:
            url = article.get("url", "")
            title = article.get("title", "")
            if not url or not title or url in seen_urls:
                continue
            if title.strip() in ("[Removed]", ""):
                continue
            seen_urls.add(url)
            article["_query"] = query
            article["_lang"] = "en"
            all_articles.append(article)
            added += 1
        print(f"  '{query}': {added}件追加")

    print(f"\n合計 {len(all_articles)} 件収集")
    return all_articles


def rank_news_with_claude(articles: list[dict]) -> list[dict]:
    """Claude (claude-sonnet-4-6) で記事を重要度順にランキングする"""
    if not articles:
        return []

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Claudeに渡す一覧を整形（最大60件）
    lines = []
    for i, a in enumerate(articles[:60], 1):
        title = a.get("title", "タイトルなし") or "タイトルなし"
        desc = (a.get("description") or "")[:120]
        source = (a.get("source") or {}).get("name", "不明")
        lang = "日本語" if a.get("_lang") == "ja" else "English"
        query = a.get("_query", "")
        lines.append(
            f"{i}. [{source} / {lang} / {query}]\n"
            f"   タイトル: {title}\n"
            f"   概要: {desc}"
        )

    articles_text = "\n\n".join(lines)

    prompt = f"""あなたは経済・金融の専門アナリストです。
以下のニュース一覧から、投資家・市場関係者にとって最も重要な記事を上位20件選び、重要度順にランキングしてください。

【重要度の基準】
1. 中央銀行（FRB・日銀）の政策変更・発言
2. 主要経済指標の発表（GDP・CPI・雇用統計など）
3. 株価・為替への直接的な影響
4. 企業の重要な決算・M&A・経営判断
5. 国際的な経済リスク・地政学リスク
※ 日本語ニュースを同程度の重要性なら優先してください

【ニュース一覧】
{articles_text}

【出力形式】
JSON形式のみで返してください。説明文・コードブロック不要。
{{
  "ranked": [
    {{
      "index": 1,
      "reason": "重要である理由（30字以内・日本語）"
    }},
    ...
  ]
}}
indexは上記リストの番号（1始まり）です。"""

    print("▶ Claude でランキング中...")
    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = message.content[0].text.strip()

        # JSONブロックが含まれる場合は抽出
        if "```" in response_text:
            parts = response_text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    response_text = part
                    break

        result = json.loads(response_text)
        ranked_list = result.get("ranked", [])

        output = []
        for item in ranked_list[:20]:
            idx = item.get("index", 0)
            reason = item.get("reason", "")
            if 1 <= idx <= len(articles):
                article = articles[idx - 1].copy()
                article["_reason"] = reason
                output.append(article)

        print(f"ランキング完了: 上位 {len(output)} 件を選出")
        return output

    except json.JSONDecodeError as e:
        print(f"  [WARN] JSON パース失敗: {e}\n  → 元の順序で上位20件を返します")
        return articles[:20]
    except anthropic.APIError as e:
        print(f"  [ERROR] Claude API エラー: {e}")
        return articles[:20]
    except Exception as e:
        print(f"  [ERROR] ランキング処理エラー: {e}")
        return articles[:20]


def _format_published(raw: str) -> str:
    """ISO 8601 形式の日時を JST の読みやすい形式に変換"""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.astimezone(JST).strftime("%m/%d %H:%M")
    except Exception:
        return raw[:10] if raw else ""


CATEGORY_COLORS = {
    "日経平均": "#e74c3c",
    "米国経済": "#3498db",
    "FRB 金利": "#8e44ad",
    "株価指数": "#e67e22",
    "市場動向": "#27ae60",
    "金融ニュース": "#16a085",
    "為替レート": "#2980b9",
    "インフレ 経済": "#c0392b",
    "Nikkei stock market Japan": "#e74c3c",
    "US economy Federal Reserve interest rates": "#3498db",
    "stock market index S&P": "#e67e22",
    "financial markets global": "#27ae60",
    "inflation economy": "#c0392b",
}

RANK_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def _generate_error_html(message: str) -> str:
    """エラー発生時のフォールバック HTML を生成する"""
    now = datetime.now(JST)
    return f"""<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"><title>Economics Bot - エラー</title>
<style>body{{font-family:sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;background:#f0f2f5;margin:0}}
.box{{background:#fff;border-radius:12px;padding:40px;max-width:500px;text-align:center;box-shadow:0 2px 12px rgba(0,0,0,.1)}}
h1{{color:#e74c3c;margin-bottom:16px}}p{{color:#555}}.time{{color:#aaa;font-size:.85rem;margin-top:16px}}</style>
</head>
<body><div class="box">
<h1>⚠️ 取得エラー</h1>
<p>{message}</p>
<p class="time">実行日時: {now.strftime('%Y-%m-%d %H:%M JST')}</p>
</div></body></html>"""


def generate_html(ranked_articles: list[dict]) -> str:
    """ランキング済み記事から HTML を生成する"""
    now = datetime.now(JST)
    date_str = now.strftime("%Y年%m月%d日 %H:%M JST")
    today_str = now.strftime("%Y/%m/%d")

    cards_html = ""
    for rank, article in enumerate(ranked_articles, 1):
        title = (article.get("title") or "タイトルなし").strip()
        description = (article.get("description") or "").strip()
        url = article.get("url") or "#"
        source = (article.get("source") or {}).get("name", "不明")
        published = _format_published(article.get("publishedAt", ""))
        query = article.get("_query", "")
        lang = article.get("_lang", "")
        reason = article.get("_reason", "")
        image_url = article.get("urlToImage") or ""

        color = CATEGORY_COLORS.get(query, "#7f8c8d")
        badge = RANK_MEDALS.get(rank, f"#{rank}")
        lang_badge = (
            '<span class="badge ja">日本語</span>'
            if lang == "ja"
            else '<span class="badge en">English</span>'
        )
        image_html = (
            f'<img src="{image_url}" alt="" class="thumb" onerror="this.style.display=\'none\'">'
            if image_url
            else ""
        )
        reason_html = (
            f'<p class="reason">💡 {reason}</p>'
            if reason
            else ""
        )
        desc_short = description[:200] + ("…" if len(description) > 200 else "")

        cards_html += f"""
    <article class="card" style="border-left:4px solid {color}">
      <div class="card-head">
        <span class="rank">{badge}</span>
        <span class="cat" style="background:{color}">{query or "経済"}</span>
        {lang_badge}
        <span class="source">{source}</span>
        <span class="date">{published}</span>
      </div>
      {image_html}
      <h2><a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a></h2>
      {reason_html}
      <p class="desc">{desc_short}</p>
    </article>"""

    total = len(ranked_articles)
    ja_count = sum(1 for a in ranked_articles if a.get("_lang") == "ja")
    en_count = total - ja_count

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>経済・金融ニュース {today_str}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif;background:#f0f2f5;color:#222;line-height:1.65}}
header{{background:linear-gradient(135deg,#0d1b2a 0%,#1b2a3b 60%,#0f3460 100%);color:#fff;padding:28px 20px;text-align:center;box-shadow:0 3px 12px rgba(0,0,0,.35)}}
header h1{{font-size:1.9rem;font-weight:800;letter-spacing:.03em;margin-bottom:6px}}
header h1 em{{color:#f1c40f;font-style:normal}}
.meta{{font-size:.82rem;opacity:.75}}
.container{{max-width:900px;margin:24px auto;padding:0 16px}}
.stats{{background:#fff;border-radius:10px;padding:12px 20px;margin-bottom:20px;display:flex;gap:18px;flex-wrap:wrap;box-shadow:0 1px 5px rgba(0,0,0,.08);font-size:.88rem;color:#555}}
.stats strong{{color:#e74c3c;font-size:1rem}}
.card{{background:#fff;border-radius:10px;padding:18px 20px;margin-bottom:16px;box-shadow:0 1px 5px rgba(0,0,0,.07);transition:box-shadow .2s}}
.card:hover{{box-shadow:0 5px 18px rgba(0,0,0,.14)}}
.card-head{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}}
.rank{{font-size:1.25rem;font-weight:700;min-width:32px}}
.cat{{color:#fff;padding:2px 10px;border-radius:12px;font-size:.75rem;font-weight:700}}
.badge{{padding:2px 8px;border-radius:10px;font-size:.72rem;font-weight:600}}
.badge.ja{{background:#fff3cd;color:#856404}}
.badge.en{{background:#d1ecf1;color:#0c5460}}
.source{{font-size:.78rem;color:#999;margin-left:auto}}
.date{{font-size:.78rem;color:#bbb}}
.thumb{{width:100%;max-height:200px;object-fit:cover;border-radius:7px;margin-bottom:10px}}
h2{{font-size:1.05rem;font-weight:700;margin-bottom:8px}}
h2 a{{color:#1a1a2e;text-decoration:none}}
h2 a:hover{{color:#0f3460;text-decoration:underline}}
.reason{{font-size:.85rem;color:#555;background:#f8f9fa;padding:6px 12px;border-radius:6px;margin-bottom:8px}}
.desc{{font-size:.85rem;color:#666}}
footer{{text-align:center;padding:24px;color:#aaa;font-size:.78rem}}
@media(max-width:600px){{header h1{{font-size:1.35rem}}.stats{{gap:10px}}}}
</style>
</head>
<body>
<header>
  <h1>📈 経済・<em>金融ニュース</em> ランキング</h1>
  <p class="meta">更新: {date_str} ｜ Powered by News API &amp; Claude Sonnet</p>
</header>
<div class="container">
  <div class="stats">
    <span>本日のピックアップ: <strong>{total}件</strong></span>
    <span>日本語: <strong>{ja_count}件</strong></span>
    <span>English: <strong>{en_count}件</strong></span>
    <span>対象: 日経平均 / 米国経済 / FRB金利 / 株価指数 / 市場動向</span>
  </div>
  {cards_html}
</div>
<footer>
  このページは自動生成されています。投資判断には各ソースの原文をご確認ください。<br>
  Economics Bot ｜ Generated by Claude AI (claude-sonnet-4-6)
</footer>
</body>
</html>"""


def main() -> None:
    print("=" * 55)
    print("  Economics Bot 起動")
    print(f"  実行日時: {datetime.now(JST).strftime('%Y-%m-%d %H:%M JST')}")
    print("=" * 55)

    if not NEWS_API_KEY:
        raise EnvironmentError("NEWS_API_KEY が設定されていません")
    if not ANTHROPIC_API_KEY:
        raise EnvironmentError("ANTHROPIC_API_KEY が設定されていません")

    articles = fetch_all_news()
    if not articles:
        print("[WARN] ニュースを1件も取得できませんでした。エラーページを生成します。")
        html = _generate_error_html("ニュースを取得できませんでした。News API キーまたはネットワーク接続を確認してください。")
        Path("economics_news.html").write_text(html, encoding="utf-8")
        print("✅ エラーページを保存しました: economics_news.html")
        return

    ranked = rank_news_with_claude(articles)

    print("▶ HTML を生成中...")
    html = generate_html(ranked)

    out = Path("economics_news.html")
    out.write_text(html, encoding="utf-8")
    print(f"✅ 保存完了: {out.resolve()}")
    print("=" * 55)


if __name__ == "__main__":
    main()
