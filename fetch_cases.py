import json
import re
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup


# -----------------------------
# ファイル設定
# -----------------------------
SOURCE_URLS_PATH = "data/source_urls.json"
OUTPUT_PATH = "data/raw_pages.json"

# Webページ本文が長すぎる場合の上限
MAX_PAGE_TEXT_LENGTH = 12000


# -----------------------------
# HTML取得
# -----------------------------
def fetch_html(url):
    """URLからHTMLを取得する。"""

    headers = {
        "User-Agent": "Mozilla/5.0 literacy-learning-system/1.0"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=20
    )

    response.raise_for_status()
    response.encoding = response.apparent_encoding

    return response.text


# -----------------------------
# テキスト整形
# -----------------------------
def clean_text(text):
    """余分な空白や改行を整理する。"""

    text = text.replace("\u3000", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.strip()

    return text


# -----------------------------
# HTMLから本文抽出
# -----------------------------
def extract_text_from_html(html):
    """HTMLから本文らしいテキストを抽出する。"""

    soup = BeautifulSoup(html, "html.parser")

    # 不要なタグを削除
    for tag in soup([
        "script",
        "style",
        "noscript",
        "header",
        "footer",
        "nav",
        "aside"
    ]):
        tag.decompose()

    # main / article があれば優先
    article_area = soup.find("article")
    main_area = soup.find("main")

    if article_area is not None:
        target = article_area
    elif main_area is not None:
        target = main_area
    else:
        target = soup.body if soup.body is not None else soup

    text_parts = []

    # 見出し・段落・リストを中心に取得
    for tag in target.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        text = clean_text(tag.get_text(" ", strip=True))

        if text == "":
            continue

        # 短すぎるメニュー文字を除外
        if len(text) < 8:
            continue

        text_parts.append(text)

    # 重複を除去しつつ順番を維持
    text_parts = list(dict.fromkeys(text_parts))

    joined_text = "。".join(text_parts)
    joined_text = clean_text(joined_text)

    return joined_text


# -----------------------------
# raw_pages形式に変換
# -----------------------------
def build_raw_page(source_item, extracted_text):
    """source_urls.jsonの情報と抽出テキストからraw_pages用データを作る。"""

    original_length = len(extracted_text)
    is_truncated = False

    if original_length > MAX_PAGE_TEXT_LENGTH:
        extracted_text = extracted_text[:MAX_PAGE_TEXT_LENGTH]
        is_truncated = True

    return {
        "id": source_item["id"],
        "source": source_item.get("source", ""),
        "type": source_item.get("type", ""),
        "title": source_item.get("title", ""),
        "url": source_item.get("url", ""),
        "text": extracted_text,
        "text_length": len(extracted_text),
        "original_text_length": original_length,
        "is_truncated": is_truncated,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


# -----------------------------
# メイン処理
# -----------------------------
def main():
    Path("data").mkdir(exist_ok=True)

    source_path = Path(SOURCE_URLS_PATH)

    if not source_path.exists():
        print(f"{SOURCE_URLS_PATH} が見つかりません。")
        print("先に data/source_urls.json を作成してください。")
        return

    with open(SOURCE_URLS_PATH, "r", encoding="utf-8") as f:
        source_urls = json.load(f)

    raw_pages = []

    for item in source_urls:
        url = item["url"]

        print("=" * 70)
        print(f"取得中: {item.get('title', '')}")
        print(f"URL: {url}")

        try:
            html = fetch_html(url)
            extracted_text = extract_text_from_html(html)

            if extracted_text == "":
                print("本文を抽出できませんでした。")
                continue

            raw_page = build_raw_page(item, extracted_text)
            raw_pages.append(raw_page)

            print("抽出成功")
            print("文字数:", raw_page["text_length"])
            print("元の文字数:", raw_page["original_text_length"])
            print("切り詰め:", raw_page["is_truncated"])
            print("本文プレビュー:")
            print(raw_page["text"][:300] + "...")

        except Exception as e:
            print("取得失敗:", e)

    output_path = Path(OUTPUT_PATH)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(raw_pages, f, ensure_ascii=False, indent=2)

    print("=" * 70)
    print(f"Webページ本文データを出力しました: {OUTPUT_PATH}")
    print("次は segment_cases.py で、長い本文を事例単位に分割します。")


if __name__ == "__main__":
    main()