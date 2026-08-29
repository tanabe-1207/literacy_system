import json
import os
import time
import copy
import re
from pathlib import Path


# -----------------------------
# Gemini設定
# -----------------------------
try:
    from google import genai
    GEMINI_AVAILABLE = True
except Exception:
    genai = None
    GEMINI_AVAILABLE = False


# -----------------------------
# ファイル設定
# -----------------------------
INPUT_PATH = Path("data/generated_problem_candidates.json")
OUTPUT_PATH = Path("data/refined_candidates.json")


# -----------------------------
# AI整形の設定
# -----------------------------
MODELS_TO_TRY = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash"
]

MIN_TEXT_LENGTH = 60
MAX_TEXT_LENGTH = 380

SLEEP_SECONDS = 1.0
MAX_RETRIES_PER_MODEL = 2

# AI出力が検証に失敗したとき、修正プロンプトで再試行する回数
MAX_VALIDATION_REPAIR_ATTEMPTS = 1


# -----------------------------
# カテゴリ別 evidence 判定用キーワード
# -----------------------------
CATEGORY_EVIDENCE_HINTS = {
    "金銭・送金要求": [
        "支払い",
        "支払",
        "送金",
        "振込",
        "口座",
        "請求",
        "料金",
        "金額",
        "納付",
        "PayPay",
        "手続き"
    ],
    "個人情報要求": [
        "電話番号",
        "認証コード",
        "確認コード",
        "パスワード",
        "暗証番号",
        "カード番号",
        "セキュリティコード",
        "住所",
        "氏名",
        "個人情報",
        "入力"
    ],
    "URL偽装": [
        "リンク",
        "URL",
        "サイト",
        "ログイン",
        "入力画面",
        "回答はこちら",
        "アクセス",
        "誘導"
    ],
    "なりすまし": [
        "よそおう",
        "装う",
        "かたる",
        "なりすまし",
        "国勢調査",
        "PayPay",
        "銀行",
        "日本年金機構",
        "取引先",
        "担当者",
        "社長"
    ],
    "緊急性誘導": [
        "至急",
        "今すぐ",
        "本日中",
        "期限",
        "24時間以内",
        "最終通知",
        "最終確認",
        "停止",
        "差押",
        "罰則",
        "未回答"
    ],
    "フェイクニュース": [
        "投稿",
        "拡散",
        "主張",
        "実際",
        "発言",
        "演説",
        "異なる",
        "事実",
        "X",
        "SNS"
    ],
    "感情的表現": [
        "真っ赤な嘘",
        "アホらし",
        "嬉しい",
        "許せない",
        "怖い",
        "不安",
        "怒り",
        "悪さ",
        "飛び上がる"
    ],
    "誇張表現": [
        "必ず",
        "絶対",
        "誰でも",
        "完全に",
        "世界でも認められて",
        "飛び上がる",
        "100%",
        "だけで"
    ],
    "出典不明": [
        "出典",
        "根拠",
        "情報源",
        "公式発表",
        "確認できない",
        "報道"
    ],
    "画像のミスリード": [
        "画像",
        "写真",
        "動画",
        "スクリーンショット",
        "別の時期",
        "別の場所",
        "AI生成"
    ],
    "統計の悪用": [
        "調査",
        "アンケート",
        "割合",
        "サンプル",
        "対象者",
        "人数",
        "%"
    ],
    "添付ファイルの危険性": [
        "添付",
        "ファイル",
        ".exe",
        ".zip",
        ".docm",
        ".xlsm",
        "開いて"
    ]
}


# 問題文に残ると「解説文」「注意喚起文」に見えやすい語
BAD_PROBLEM_TEXT_WORDS = [
    "注意してください",
    "注意しましょう",
    "控えてください",
    "応じないようにしましょう",
    "絶対に応じないようにしましょう",
    "進めないようにしましょう",
    "削除するだけで問題ない",
    "危険です",
    "大変危険です",
    "危険である",
    "確認されています",
    "報告されています",
    "検証する",
    "検証しました",
    "不正確です",
    "誤りです",
    "フィッシングメール",
    "フィッシング詐欺",
    "フィッシングサイト",
    "詐欺の手口",
    "詐欺です"
]


# 問題文から除外したい「記事側の説明・図説明・対処説明」
# これらは危険要素そのものではなく、記事の解説や被害後の案内であることが多い。
NON_QUIZ_SENTENCE_KEYWORDS = [
    "図9",
    "図10",
    "図11",
    "図12",
    "赤色破線",
    "赤い破線",
    "図中",
    "以下では",
    "本記事では",
    "検証します",
    "解説します",
    "見抜くポイント",
    "相談する",
    "銀行に相談",
    "警察に相談",
    "IPAに相談",
    "必要な対処",
    "不正送金の有無",
    "パスワードの変更",
    "削除してください",
    "アクセスしない",
    "入力しない",
    "連絡しない",
    "確認してください",
    "注意喚起",
    "対処について"
]

# 文章に含まれていると、攻撃文ではなく「被害後の対応説明」である可能性が高い表現。
ADVICE_CONTEXT_KEYWORDS = [
    "パスワードの変更",
    "不正送金の有無",
    "必要な対処",
    "銀行に相談",
    "警察に相談",
    "IPAに相談",
    "相談してください",
    "確認してください",
    "削除してください",
    "アクセスしない",
    "入力しない",
    "連絡しない"
]


# -----------------------------
# 基本関数
# -----------------------------
def load_json(path, default=None):
    if default is None:
        default = []

    if not path.exists():
        print(f"{path} が見つかりません。")
        return default

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clean_text(text):
    text = str(text)
    text = text.replace("\u3000", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_for_compare(text):
    text = clean_text(text)
    remove_chars = [
        " ",
        "　",
        "、",
        "。",
        "・",
        "/",
        "「",
        "」",
        "（",
        "）",
        "(",
        ")",
        "：",
        ":"
    ]

    for char in remove_chars:
        text = text.replace(char, "")

    return text


def text_contains_evidence(text, evidence):
    if not evidence:
        return False

    text = clean_text(text)
    evidence = clean_text(evidence)

    if evidence in text:
        return True

    return normalize_for_compare(evidence) in normalize_for_compare(text)


def load_api_key():
    """
    APIキーを読み込む。
    優先順位：
    1. 環境変数 GEMINI_API_KEY
    2. .streamlit/secrets.toml
    """

    env_key = os.getenv("GEMINI_API_KEY")

    if env_key:
        return env_key

    secrets_path = Path(".streamlit/secrets.toml")

    if not secrets_path.exists():
        return ""

    try:
        text = secrets_path.read_text(encoding="utf-8")

        match = re.search(
            r'GEMINI_API_KEY\s*=\s*["\'](.+?)["\']',
            text
        )

        if match:
            return match.group(1).strip()

        return ""

    except Exception as e:
        print("secrets.toml の読み込みに失敗しました:", e)
        return ""


# -----------------------------
# 事前整形
# -----------------------------

def split_sentences_for_quiz(text):
    """日本語の句点を中心に文単位へ分ける。"""

    text = clean_text(text)
    sentences = []

    for sentence in re.split(r"(?<=。)", text):
        sentence = clean_text(sentence)
        if sentence:
            sentences.append(sentence)

    return sentences


def contains_any(text, words):
    return any(word in text for word in words)


def is_figure_or_caption_sentence(sentence):
    """図番号・キャプション・赤色破線など、記事の図説明を判定する。"""

    sentence = clean_text(sentence)

    if re.search(r"図\d+[:：]", sentence):
        return True

    if re.search(r"図\d+", sentence) and contains_any(sentence, ["赤色破線", "赤い破線", "クリックすると", "ジャンプ", "表示される"]):
        return True

    if contains_any(sentence, ["赤色破線", "赤い破線"]):
        return True

    return False


def is_advice_or_article_meta_sentence(sentence):
    """
    記事の解説・対処説明・注意喚起文を判定する。
    攻撃者が焦らせる「至急」と、記事側の「至急パスワード変更」を区別するため、
    「至急」単独では削除しない。
    """

    sentence = clean_text(sentence)

    if is_figure_or_caption_sentence(sentence):
        return True

    if contains_any(sentence, ADVICE_CONTEXT_KEYWORDS):
        return True

    if contains_any(sentence, ["本記事では", "以下では", "解説します", "検証します", "見抜くポイント"]):
        return True

    return False


def remove_non_quiz_sentences(text):
    """
    問題文に不要な、図説明・被害後の対処説明・記事の解説文を削る。
    これにより、対処説明中の「至急」などを緊急性誘導として拾う誤判定を減らす。
    """

    text = clean_text(text)

    # 文中の図参照だけは先に削る
    text = re.sub(r"（図\d+）", "", text)
    text = re.sub(r"\(図\d+\)", "", text)

    sentences = split_sentences_for_quiz(text)
    kept = []

    for sentence in sentences:
        if is_advice_or_article_meta_sentence(sentence):
            continue
        kept.append(sentence)

    if not kept:
        return clean_text(text)

    return clean_text("".join(kept))


def trim_quiz_text(text, max_chars=360):
    """
    問題文が長すぎる場合、文単位で自然に短くする。
    AIに渡す下書きが長すぎると、図説明や対処説明が混ざりやすいため。
    """

    text = clean_text(text)

    if len(text) <= max_chars:
        return text

    kept = []
    total = 0

    for sentence in split_sentences_for_quiz(text):
        if total + len(sentence) > max_chars:
            break
        kept.append(sentence)
        total += len(sentence)

    if kept:
        return clean_text("".join(kept))

    return text[:max_chars].rstrip("、。 ") + "。"


def preclean_text_for_quiz(text):
    """
    AIに渡す前に、問題に不要な記事表現を落とす。
    ここで図説明・被害後の対処説明・注意喚起文を削ることで、
    「至急パスワード変更」などを緊急性誘導として拾う誤りを減らす。
    """

    text = clean_text(text)

    # 先頭の「事例1：タイトル。」のような見出しを弱める
    text = re.sub(r"^事例\d+[:：]", "", text)
    text = re.sub(r"^本事例は、", "", text)

    # 図参照・図説明・被害後の対処説明を文単位で削る
    text = remove_non_quiz_sentences(text)

    # よくある誤字
    text = text.replace("お愿い", "お願い")
    text = text.replace("怪しいと感じで", "怪しいと感じて")

    # AIに渡す下書きが長すぎると、解説文を巻き込みやすいので短くする
    text = trim_quiz_text(text, max_chars=360)

    return clean_text(text)

def remove_question_like_text(text):
    """
    textには設問文を入れず、事例本文だけにする。
    """

    text = clean_text(text)

    remove_patterns = [
        r"この事例から考えられる脅威のカテゴリとして適切なものを選びなさい。",
        r"この事例から考えられる危険要素として適切なものを選びなさい。",
        r"この文章で特に注意すべき危険要素を選択してください。",
        r"適切なものを選びなさい。",
        r"危険要素を選択してください。",
        r"カテゴリとして適切なものを選択してください。",
        r"この事例から考えられる脅威のカテゴリとして適切なものを選んでください。",
        r"この事例から考えられる危険要素として適切なものを選んでください。"
    ]

    for pattern in remove_patterns:
        text = re.sub(pattern, "", text)

    return clean_text(text)


def postprocess_quiz_text(text):
    """
    AI出力後にも、設問文・図説明・対処説明が残っていれば削る。
    """

    text = remove_question_like_text(text)
    text = remove_non_quiz_sentences(text)
    text = clean_text(text)

    text = text.strip(" 、。")
    if text and not text.endswith("。"):
        text += "。"

    return clean_text(text)


# -----------------------------
# evidence補助
# -----------------------------
def extract_sentence_containing(text, keywords):
    text = clean_text(text)
    sentences = split_sentences_for_quiz(text)

    for sentence in sentences:
        sentence = clean_text(sentence)

        if not sentence:
            continue

        if is_advice_or_article_meta_sentence(sentence):
            continue

        for keyword in keywords:
            if keyword in sentence:
                return sentence

    return ""

def extract_short_phrase(text, keywords, window=35):
    text = clean_text(text)

    for keyword in keywords:
        index = text.find(keyword)

        if index == -1:
            continue

        start = max(0, index - window)
        end = min(len(text), index + len(keyword) + window)

        phrase = text[start:end]
        phrase = phrase.strip("、。 ")

        return phrase

    return ""


def extract_evidence_by_category(text, category):
    """
    AIが出したevidenceが弱い場合に、整形後textから取り直す。
    """

    text = clean_text(text)
    keywords = CATEGORY_EVIDENCE_HINTS.get(category, [])

    sentence = extract_sentence_containing(text, keywords)

    if sentence:
        if len(sentence) > 90:
            short_phrase = extract_short_phrase(sentence, keywords)
            if short_phrase:
                return short_phrase

        return sentence

    return ""


def evidence_has_category_hint(category, evidence):
    """
    evidenceがカテゴリの根拠として最低限の語を含むか確認する。
    例：金銭・送金要求なら「支払い」「送金」などが欲しい。
    """

    evidence = clean_text(evidence)
    hints = CATEGORY_EVIDENCE_HINTS.get(category, [])

    if not hints:
        return True

    return any(keyword in evidence for keyword in hints)


def repair_answer_details(refined_text, answer_details):
    """
    evidenceが長すぎる、またはカテゴリの根拠として弱い場合に、
    カテゴリ別キーワードから根拠を取り直す。
    """

    repaired_details = []

    for detail in answer_details:
        if not isinstance(detail, dict):
            repaired_details.append(detail)
            continue

        new_detail = copy.deepcopy(detail)

        category = new_detail.get("category", "")
        evidence = clean_text(new_detail.get("evidence", ""))

        needs_repair = False

        if not evidence:
            needs_repair = True

        if evidence and not text_contains_evidence(refined_text, evidence):
            needs_repair = True

        if evidence and len(evidence) > 90:
            needs_repair = True

        if evidence and is_advice_or_article_meta_sentence(evidence):
            needs_repair = True

        if evidence and not evidence_has_category_hint(category, evidence):
            needs_repair = True

        if needs_repair:
            repaired_evidence = extract_evidence_by_category(refined_text, category)

            if repaired_evidence:
                new_detail["evidence"] = repaired_evidence

        repaired_details.append(new_detail)

    return repaired_details


# -----------------------------
# Gemini返答処理
# -----------------------------
def extract_json_from_response(text):
    """
    Geminiの返答からJSON部分だけを取り出す。
    """

    text = str(text).strip()

    if text.startswith("```"):
        text = re.sub(r"^```json", "", text.strip(), flags=re.IGNORECASE)
        text = re.sub(r"^```", "", text.strip())
        text = re.sub(r"```$", "", text.strip())

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and start < end:
        text = text[start:end + 1]

    return json.loads(text)


def normalize_refined_details(candidate, refined):
    """
    AIがanswer_detailsの順番を変えた場合でも、元のanswer順に戻す。
    """

    original_answer = candidate.get("answer", [])
    refined_details = refined.get("answer_details", [])

    if not isinstance(refined_details, list):
        return refined

    detail_map = {}

    for detail in refined_details:
        if not isinstance(detail, dict):
            continue

        category = detail.get("category")

        if category:
            detail_map[category] = detail

    if set(detail_map.keys()) == set(original_answer):
        refined["answer_details"] = [
            detail_map[category]
            for category in original_answer
        ]

    return refined


# -----------------------------
# プロンプト
# -----------------------------
def build_type_instruction(problem_type):
    if problem_type == "phishing":
        return """
この候補は、フィッシング・詐欺・セキュリティ注意喚起系です。

元記事の「注意してください」「危険です」という説明文をそのまま使わず、
学習者が実際に受け取ったメール・SMS・通知・Web画面の内容のような問題文にしてください。

良い問題文の形：
「〇〇に関するメールが届きました。本文には、〜するよう書かれています。」
「リンクを開くと、〜の入力を求める画面が表示されました。」
「表示された画面では、〜の手続きを進めるよう求められています。」

禁止：
元記事にない金額、期限、URL、アカウント停止、サービス停止などを作らない。
"""

    if problem_type == "fake_news":
        return """
この候補は、フェイクニュース・誤情報系です。

元記事の解説をそのまま使わず、
学習者がSNS投稿や拡散された主張を読んで判断する問題文にしてください。

良い問題文の形：
「Xで、〜という投稿が拡散しました。」
「投稿では〜と主張されています。一方で、実際の発言では〜と述べられていました。」
「投稿には〜のような反応も見られました。」

禁止：
「誤りです」「不正確です」「検証する」など、答えや解説が見えすぎる表現を問題文に入れない。
"""

    return """
元記事の説明文をそのまま使わず、学習者が危険要素を判断するための短い事例文にしてください。
"""


def make_prompt(candidate):
    """
    AIに渡す初回プロンプト。
    answer/category/choices は変更禁止。
    """

    original_text = clean_text(candidate.get("text", ""))
    precleaned_text = preclean_text_for_quiz(original_text)

    answer = candidate.get("answer", [])
    category = candidate.get("category", [])
    choices = candidate.get("choices", [])
    answer_details = candidate.get("answer_details", [])
    title = candidate.get("title", "")
    source = candidate.get("source", "")
    problem_type = candidate.get("type", "")

    type_instruction = build_type_instruction(problem_type)

    prompt = f"""
あなたは情報リテラシー学習用クイズの編集者です。

次のWeb由来の文章を、学習者が「危険要素」を判断するための問題文に作り直してください。

重要：
正解カテゴリは、すでにルールベース処理で決定済みです。
あなたは正解カテゴリを判定してはいけません。
あなたは answer / category / choices を変更してはいけません。
あなたの役割は、問題文・根拠・理由を教材として自然に整えることだけです。

{type_instruction}

【AIに任せること】
- textを、学習者が判断するための自然な事例文にする
- Web記事の注意喚起文・説明文を、問題として読める文章に変える
- evidenceを、整形後textから短く抜き出す
- reasonを、学習者に分かりやすい1〜2文に整える

【必ず削る内容】
- 図番号、図の説明、赤色破線などのキャプション
- 被害後の対処説明
- 「至急パスワードの変更」「不正送金の有無を確認」「銀行に相談する」などの案内
- 「検証します」「解説します」「見抜くポイント」などの記事側の説明
- 相談窓口、注意喚起、対策アドバイス

【重要な区別】
- 攻撃者のメール・SMS・画面にある「至急」「本日中」は緊急性誘導の根拠として残す
- しかし、記事側の「至急パスワードを変更する」「銀行に相談する」は対処説明なので問題文にもevidenceにも入れない

【AIが絶対にしてはいけないこと】
- answerを変更しない
- categoryを変更しない
- choicesを変更しない
- 正解カテゴリを追加しない
- 正解カテゴリを削除しない
- 本文にない重大な事実を作らない
- 元記事にない期限、金額、URL、アカウント停止、サービス停止などを作らない
- textに「選びなさい」「選択してください」などの設問文を入れない

【問題文textの条件】
- 80〜260字程度を目安にする
- 最大でも380字以内にする
- 「注意してください」「危険です」「応じないようにしましょう」のような注意喚起文にしない
- 「フィッシング」「詐欺」「誤りです」「不正確です」のように答えが見えすぎる語は入れない
- ただし、正解カテゴリを判断できる根拠は必ず残す
- 問題文は「メールが届いた」「リンクを開いた」「投稿が拡散した」など、判断対象の事例として書く
- 見出し、図番号、記事の説明、結論、対策アドバイスはできるだけ削る

【evidenceの条件】
- evidenceは、整形後textの中に実際に存在する表現をそのまま抜き出す
- 10〜60字程度にする
- カテゴリの根拠として分かりやすい表現にする
- 例：金銭・送金要求なら「支払い」「送金」「請求」などを含む表現
- 例：個人情報要求なら「電話番号」「認証コード」「入力」などを含む表現
- 例：URL偽装なら「リンク」「サイト」「ログイン画面」などを含む表現
- 本文にない表現を作らない

【reasonの条件】
- reasonは、なぜそのカテゴリに該当するのかを学習者向けに説明する
- 1〜2文にする
- できるだけ「〜しているため」「〜させようとしているため」という形にする
- 「〜に該当します」だけで終わらせない

【出力JSON形式】
必ず次の形式のJSONだけを出力してください。
Markdown、説明文、コードブロックは禁止です。

{{
  "text": "整形後の問題文",
  "answer_details": [
    {{
      "category": "カテゴリ名",
      "evidence": "整形後text内に存在する短い根拠表現",
      "reason": "理由"
    }}
  ]
}}

【元タイトル】
{title}

【出典】
{source}

【元の問題文】
{original_text}

【AIが主に使う下書き】
{precleaned_text}

注意：原則として「AIが主に使う下書き」をもとに作成してください。
元の問題文にだけ含まれる図説明・対処説明・記事の解説文は使わないでください。

【選択肢】
{json.dumps(choices, ensure_ascii=False)}

【正解カテゴリ】
{json.dumps(answer, ensure_ascii=False)}

【category】
{json.dumps(category, ensure_ascii=False)}

【現在のanswer_details】
{json.dumps(answer_details, ensure_ascii=False, indent=2)}
"""

    return prompt.strip()


def make_repair_prompt(candidate, previous_refined, errors):
    """
    AI出力が検証に失敗した場合に、修正させるプロンプト。
    """

    base_prompt = make_prompt(candidate)

    repair_prompt = f"""
{base_prompt}

前回の出力は次の理由で不採用になりました。
エラー内容をすべて修正して、もう一度JSONだけを出力してください。

【前回の出力】
{json.dumps(previous_refined, ensure_ascii=False, indent=2)}

【修正すべきエラー】
{json.dumps(errors, ensure_ascii=False, indent=2)}

特に注意：
- 問題文を注意喚起文にしない
- evidenceは短くする
- evidenceはカテゴリの根拠として分かりやすい語を含める
- evidenceは必ず整形後textに含まれる表現にする
- answer/category/choicesは絶対に変えない
"""

    return repair_prompt.strip()


def make_text_only_prompt(candidate):
    """
    answerが空の候補用。
    答えは作らせず、reviewで読みやすい問題文だけ整える。
    """

    original_text = clean_text(candidate.get("text", ""))
    precleaned_text = preclean_text_for_quiz(original_text)
    title = candidate.get("title", "")
    source = candidate.get("source", "")
    problem_type = candidate.get("type", "")
    type_instruction = build_type_instruction(problem_type)

    prompt = f"""
あなたは情報リテラシー学習用クイズの編集者です。

この候補は、まだ正解カテゴリが決まっていません。
そのため、あなたは正解カテゴリを作ってはいけません。
answer、category、choices、answer_detailsは作らないでください。

行うことは、元記事の文章を、管理者が確認しやすい「問題文らしい事例文」に整えることだけです。

{type_instruction}

【条件】
- textだけを出力する
- 80〜260字程度
- 記事の注意喚起文ではなく、学習者が判断する事例文にする
- 「注意してください」「危険です」「誤りです」「不正確です」など、答えや解説が見えすぎる語は避ける
- 元記事にない重大な事実は作らない
- 出力はJSONのみ

【出力JSON形式】
{{
  "text": "整形後の問題文"
}}

【元タイトル】
{title}

【出典】
{source}

【元の問題文】
{original_text}

【AIが主に使う下書き】
{precleaned_text}

注意：原則として「AIが主に使う下書き」をもとに作成してください。
元の問題文にだけ含まれる図説明・対処説明・記事の解説文は使わないでください。
"""

    return prompt.strip()


# -----------------------------
# 検証
# -----------------------------
def validate_problem_text_style(text):
    errors = []

    text = clean_text(text)

    for word in BAD_PROBLEM_TEXT_WORDS:
        if word in text:
            errors.append(f"問題文が注意喚起文・解説文に見えます。避けたい語: {word}")

    for word in NON_QUIZ_SENTENCE_KEYWORDS:
        if word in text:
            errors.append(f"問題文に図説明・対処説明が残っています。避けたい語: {word}")

    # 「〜しましょう」は基本的に問題文ではなく指導文になりやすい
    if "しましょう" in text:
        errors.append("問題文に『しましょう』が含まれており、注意喚起文のように見えます。")

    if "してください" in text:
        errors.append("問題文に『してください』が含まれており、設問・注意喚起文のように見えます。")

    return errors


def validate_refined(candidate, refined):
    """
    AIの出力が安全に使えるか確認する。
    evidenceは補修したうえで、カテゴリ根拠としても確認する。
    """

    errors = []

    original_answer = candidate.get("answer", [])
    original_choices = candidate.get("choices", [])
    original_category = candidate.get("category", [])

    refined_text = postprocess_quiz_text(refined.get("text", ""))
    refined_details = refined.get("answer_details", [])

    refined["text"] = refined_text

    if not refined_text:
        errors.append("AI整形後のtextが空です。")

    if len(refined_text) < MIN_TEXT_LENGTH:
        errors.append("AI整形後のtextが短すぎます。")

    if len(refined_text) > MAX_TEXT_LENGTH:
        errors.append("AI整形後のtextが長すぎます。")

    errors.extend(validate_problem_text_style(refined_text))

    if not isinstance(refined_details, list):
        errors.append("answer_detailsがリスト形式ではありません。")
        refined_details = []

    refined_categories = [
        detail.get("category")
        for detail in refined_details
        if isinstance(detail, dict)
    ]

    if refined_categories != original_answer:
        errors.append("answer_detailsのカテゴリ順または内容が元のanswerと一致しません。")

    if original_answer != original_category:
        errors.append("元候補のanswerとcategoryが一致していません。")

    if len(original_choices) != 5:
        errors.append("元候補のchoicesが5個ではありません。")

    if set(original_answer) - set(original_choices):
        errors.append("元候補のanswerがchoicesに含まれていません。")

    refined_details = repair_answer_details(refined_text, refined_details)
    refined["answer_details"] = refined_details

    for detail in refined_details:
        if not isinstance(detail, dict):
            errors.append("answer_details内の要素がdictではありません。")
            continue

        category = detail.get("category", "")
        evidence = clean_text(detail.get("evidence", ""))
        reason = clean_text(detail.get("reason", ""))

        if category not in original_answer:
            errors.append(f"元のanswerにないカテゴリが含まれています: {category}")

        if not evidence:
            errors.append(f"evidenceが空です: {category}")

        if evidence and not text_contains_evidence(refined_text, evidence):
            errors.append(f"evidenceが整形後textに含まれていません: {category} / {evidence}")

        if evidence and len(evidence) > 90:
            errors.append(f"evidenceが長すぎます: {category} / {evidence}")

        if evidence and is_advice_or_article_meta_sentence(evidence):
            errors.append(f"evidenceに図説明・対処説明が含まれています: {category} / {evidence}")

        if evidence and not evidence_has_category_hint(category, evidence):
            errors.append(f"evidenceがカテゴリの根拠として弱いです: {category} / {evidence}")

        if not reason:
            errors.append(f"reasonが空です: {category}")

        if reason and len(reason) > 160:
            errors.append(f"reasonが長すぎます: {category}")

    return errors


def validate_text_only_refined(refined):
    errors = []
    text = postprocess_quiz_text(refined.get("text", ""))
    refined["text"] = text

    if not text:
        errors.append("AI整形後のtextが空です。")

    if len(text) < MIN_TEXT_LENGTH:
        errors.append("AI整形後のtextが短すぎます。")

    if len(text) > MAX_TEXT_LENGTH:
        errors.append("AI整形後のtextが長すぎます。")

    errors.extend(validate_problem_text_style(text))

    return errors


# -----------------------------
# 反映・失敗処理
# -----------------------------
def apply_refinement(candidate, refined, model_name):
    """
    元のcandidateにAI整形結果を反映する。
    answer / category / choices は絶対に変更しない。
    """

    new_candidate = copy.deepcopy(candidate)

    new_candidate["original_text_before_ai_refine"] = candidate.get("text", "")
    new_candidate["text"] = postprocess_quiz_text(
        refined.get("text", candidate.get("text", ""))
    )
    new_candidate["answer_details"] = refined.get(
        "answer_details",
        candidate.get("answer_details", [])
    )

    new_candidate["ai_refined"] = True
    new_candidate["ai_refine_status"] = "refined"
    new_candidate["ai_refine_model"] = model_name
    new_candidate["ai_refine_warnings"] = []

    return new_candidate


def apply_text_only_refinement(candidate, refined, model_name):
    """
    answerが空の候補に対して、問題文だけを整える。
    正解カテゴリは作らない。
    """

    new_candidate = copy.deepcopy(candidate)

    new_candidate["original_text_before_ai_refine"] = candidate.get("text", "")
    new_candidate["text"] = postprocess_quiz_text(
        refined.get("text", candidate.get("text", ""))
    )

    new_candidate["ai_refined"] = False
    new_candidate["ai_text_refined"] = True
    new_candidate["ai_refine_status"] = "text_refined_no_answer"
    new_candidate["ai_refine_model"] = model_name
    new_candidate["ai_refine_warnings"] = [
        "正解カテゴリは作成せず、問題文だけAIで整形しました。"
    ]

    return new_candidate


def mark_not_refined(candidate, status, warnings):
    """
    AI整形できなかった場合も候補は残す。
    ただし、古い文章を無理に rule_refined として成功扱いしない。
    """

    new_candidate = copy.deepcopy(candidate)
    new_candidate["ai_refined"] = False
    new_candidate["ai_refine_status"] = status
    new_candidate["ai_refine_warnings"] = warnings

    return new_candidate


# -----------------------------
# Gemini呼び出し
# -----------------------------
def is_quota_error(error_message):
    lower = error_message.lower()
    return (
        "resource_exhausted" in lower
        or "quota" in lower
        or "429" in lower
    )


def is_retryable_error(error_message):
    lower = error_message.lower()
    return (
        "503" in lower
        or "overloaded" in lower
        or "unavailable" in lower
        or "timeout" in lower
        or "temporarily" in lower
    )


def call_gemini_json(client, prompt):
    """
    複数モデルを試しながらGeminiを呼び出す。
    """

    last_error = None

    for model_name in MODELS_TO_TRY:
        for attempt in range(1, MAX_RETRIES_PER_MODEL + 1):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )

                response_text = getattr(response, "text", "")

                if not response_text:
                    raise ValueError("Geminiの返答が空でした。")

                refined = extract_json_from_response(response_text)

                return refined, model_name, None

            except Exception as e:
                error_message = str(e)
                last_error = error_message

                if is_quota_error(error_message):
                    return None, model_name, f"API利用制限に達しました: {error_message}"

                if is_retryable_error(error_message):
                    wait_time = SLEEP_SECONDS * attempt
                    print(f"一時的なエラーのため再試行します: model={model_name}, attempt={attempt}")
                    time.sleep(wait_time)
                    continue

                break

    return None, "", f"AI整形に失敗しました: {last_error}"


def refine_answered_candidate(client, candidate):
    """
    answerがある候補をAIで問題文らしく整形する。
    validationに失敗した場合は、修正プロンプトで再試行する。
    """

    prompt = make_prompt(candidate)

    refined = None
    model_name = ""

    for repair_attempt in range(0, MAX_VALIDATION_REPAIR_ATTEMPTS + 1):
        refined, model_name, error = call_gemini_json(client, prompt)

        if error:
            return mark_not_refined(
                candidate,
                status="error",
                warnings=[error]
            )

        refined = normalize_refined_details(candidate, refined)

        if "text" in refined:
            refined["text"] = postprocess_quiz_text(refined["text"])

        errors = validate_refined(candidate, refined)

        if not errors:
            return apply_refinement(candidate, refined, model_name)

        if repair_attempt < MAX_VALIDATION_REPAIR_ATTEMPTS:
            prompt = make_repair_prompt(candidate, refined, errors)
            continue

        return mark_not_refined(
            candidate,
            status="validation_failed",
            warnings=errors
        )

    return mark_not_refined(
        candidate,
        status="validation_failed",
        warnings=["不明な理由でAI整形に失敗しました。"]
    )


def refine_no_answer_candidate(client, candidate):
    """
    answerが空の候補は、AIに答えを作らせず、問題文だけ整える。
    """

    prompt = make_text_only_prompt(candidate)

    refined, model_name, error = call_gemini_json(client, prompt)

    if error:
        return mark_not_refined(
            candidate,
            status="skipped_no_answer",
            warnings=[
                "正解カテゴリがないためanswer_detailsは作成していません。",
                error
            ]
        )

    errors = validate_text_only_refined(refined)

    if errors:
        return mark_not_refined(
            candidate,
            status="skipped_no_answer",
            warnings=[
                "正解カテゴリがないためanswer_detailsは作成していません。"
            ] + errors
        )

    return apply_text_only_refinement(candidate, refined, model_name)


def refine_one_candidate(client, candidate):
    """
    1件分の候補をAIで整形する。
    """

    if not candidate.get("answer"):
        return mark_not_refined(
            candidate,
            status="skipped_no_answer",
            warnings=["正解カテゴリがないためAI整形をスキップしました。"]
        )

    if not candidate.get("answer_details"):
        return mark_not_refined(
            candidate,
            status="skipped_no_answer_details",
            warnings=["answer_detailsがないためAI整形をスキップしました。"]
        )

    return refine_answered_candidate(client, candidate)


# -----------------------------
# メイン処理
# -----------------------------
def main():
    candidates = load_json(INPUT_PATH, default=[])

    if not candidates:
        print(f"{INPUT_PATH} に候補がありません。")
        return

    if not GEMINI_AVAILABLE:
        print("google-genai がインストールされていません。")
        print("次を実行してください: py -m pip install google-genai")
        return

    api_key = load_api_key()

    if not api_key:
        print("GEMINI_API_KEY が見つかりません。")
        print(".streamlit/secrets.toml または環境変数に GEMINI_API_KEY を設定してください。")
        return

    client = genai.Client(api_key=api_key)

    refined_candidates = []

    print("=" * 70)
    print("AIによる問題文整形を開始します。")
    print(f"入力: {INPUT_PATH}")
    print(f"出力: {OUTPUT_PATH}")
    print(f"件数: {len(candidates)}")
    print("試行モデル:", " → ".join(MODELS_TO_TRY))

    for index, candidate in enumerate(candidates, start=1):
        candidate_id = candidate.get("id")
        title = candidate.get("title", "")

        print("-" * 70)
        print(f"{index}/{len(candidates)} ID={candidate_id} {title}")

        refined = refine_one_candidate(client, candidate)
        refined_candidates.append(refined)

        print("結果:", refined.get("ai_refine_status"))

        if refined.get("ai_refine_model"):
            print("使用モデル:", refined.get("ai_refine_model"))

        if refined.get("ai_refine_warnings"):
            print("警告:")
            for warning in refined.get("ai_refine_warnings", []):
                print(" -", warning)

        time.sleep(SLEEP_SECONDS)

    save_json(OUTPUT_PATH, refined_candidates)

    refined_count = sum(
        1 for item in refined_candidates
        if item.get("ai_refined") is True
    )

    text_refined_count = sum(
        1 for item in refined_candidates
        if item.get("ai_refine_status") == "text_refined_no_answer"
    )

    failed_count = len(refined_candidates) - refined_count - text_refined_count

    print("=" * 70)
    print("AI整形が完了しました。")
    print(f"AI整形成功: {refined_count} 件")
    print(f"正解なし候補の問題文整形: {text_refined_count} 件")
    print(f"未整形・要確認: {failed_count} 件")
    print(f"出力ファイル: {OUTPUT_PATH}")
    print("次に data/refined_candidates.json を確認してください。")


if __name__ == "__main__":
    main()