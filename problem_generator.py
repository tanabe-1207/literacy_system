import json
import re
import random
from pathlib import Path


# -----------------------------
# SudachiPy設定
# -----------------------------
try:
    from sudachipy import Dictionary, SplitMode

    tokenizer_obj = Dictionary().create()
    SPLIT_MODE = SplitMode.C
    SUDACHI_AVAILABLE = True

except Exception:
    tokenizer_obj = None
    SPLIT_MODE = None
    SUDACHI_AVAILABLE = False


# -----------------------------
# ファイル設定
# -----------------------------
RAW_CASES_PATH = "data/raw_cases.json"
EXPLANATIONS_PATH = "data/explanations.json"
CATEGORY_RULES_PATH = "data/category_rules.json"
OUTPUT_PATH = "data/generated_problem_candidates.json"


# -----------------------------
# 基本設定
# -----------------------------
QUESTION_TEXT = "この文章で特に注意すべき危険要素を選択してください。"

MIN_TEXT_LENGTH = 50
MAX_TEXT_LENGTH = 450

# 商用デモ・発表で使いやすいように、正解カテゴリは基本2個までにする。
# 3個以上は学習者が迷いやすく、要確認にも回りやすいため。
MAX_ANSWER_CATEGORIES = 2

CHOICE_COUNT = 5

# 「そのまま追加できる候補7割、要確認3割」を目指すための方針
# auto_ready: validation_statusがvalidで、かつ品質フラグがない候補
# review: 正解なし・曖昧カテゴリ単独・根拠が弱い候補
AUTO_READY_TARGET_NOTE = "auto_ready を増やしつつ、危ない候補だけ review に回す設定"

# Trueにすると形態素解析結果も出力する。通常はFalseでよい。
DEBUG_TOKENS = False


# -----------------------------
# explanations.json が読めない場合の保険
# -----------------------------
DEFAULT_CATEGORIES = [
    "URL偽装",
    "緊急性誘導",
    "個人情報要求",
    "なりすまし",
    "フェイクニュース",
    "誇張表現",
    "出典不明",
    "画像のミスリード",
    "統計の悪用",
    "添付ファイルの危険性",
    "感情的表現",
    "金銭・送金要求"
]


# -----------------------------
# typeごとの優先カテゴリ
# -----------------------------
TYPE_PRIORITY = {
    "phishing": [
        "URL偽装",
        "個人情報要求",
        "なりすまし",
        "緊急性誘導",
        "金銭・送金要求",
        "添付ファイルの危険性",
        "感情的表現",
        "誇張表現",
        "出典不明",
        "フェイクニュース",
        "画像のミスリード",
        "統計の悪用"
    ],
    "fake_news": [
        "統計の悪用",
        "フェイクニュース",
        "出典不明",
        "画像のミスリード",
        "感情的表現",
        "誇張表現",
        "なりすまし",
        "URL偽装",
        "個人情報要求",
        "緊急性誘導",
        "金銭・送金要求",
        "添付ファイルの危険性"
    ]
}


# -----------------------------
# カテゴリごとの最低スコア
# 低すぎると誤検出、高すぎると候補が増えないため、7:3を目指して中間にする。
# -----------------------------
CATEGORY_MIN_SCORE = {
    "URL偽装": 2,
    "緊急性誘導": 2,
    "個人情報要求": 2,
    "なりすまし": 2,
    "金銭・送金要求": 2,
    "添付ファイルの危険性": 2,

    # 誤検出しやすいカテゴリは少し厳しめ
    "フェイクニュース": 3,
    "統計の悪用": 3,
    "出典不明": 3,
    "画像のミスリード": 4,
    "誇張表現": 4,
    "感情的表現": 3
}


# -----------------------------
# evidenceを短く抜き出すためのカテゴリ別ヒント
# -----------------------------
CATEGORY_EVIDENCE_HINTS = {
    "URL偽装": [
        "URL", "リンク", "ログイン", "サイト", "ドメイン", "誘導", "アクセス", "偽サイト"
    ],
    "緊急性誘導": [
        "24時間以内", "48時間以内", "本日中", "至急", "今すぐ", "最終確認",
        "最終通知", "差押", "期限", "停止", "未納"
    ],
    "個人情報要求": [
        "パスワード", "暗証番号", "認証コード", "確認コード", "クレジットカード番号",
        "カード番号", "セキュリティコード", "住所", "電話番号", "個人情報", "入力"
    ],
    "なりすまし": [
        "なりすまし", "なりすました", "よそおう", "かたる", "装う",
        "偽のメール", "日本年金", "日本年金機構", "社長", "担当者", "取引先"
    ],
    "フェイクニュース": [
        "不正確", "誤り", "事実ではない", "実際には", "実際の", "異なる",
        "確認できない", "否定", "拡散", "投稿", "主張"
    ],
    "統計の悪用": [
        "9割", "96％", "96%", "300件", "調査対象", "対象", "全体",
        "一部", "サンプル", "調査結果", "割合", "母集団"
    ],
    "画像のミスリード": [
        "画像", "写真", "動画", "映像", "スクリーンショット",
        "別の時期", "別の場所", "過去", "無関係", "AI生成", "加工", "切り抜き"
    ],
    "誇張表現": [
        "必ず", "絶対", "誰でも", "確実に", "100%", "世界一",
        "史上最悪", "完全に", "一瞬で", "すぐに稼げる", "飛び上がるぐらい"
    ],
    "出典不明": [
        "出典", "根拠", "情報源", "公式発表", "確認できない", "出所不明", "根拠が不明"
    ],
    "添付ファイルの危険性": [
        "添付ファイル", "添付", "ファイル", ".exe", ".zip", ".docm", ".xlsm", "開いて"
    ],
    "感情的表現": [
        "許せない", "恐怖", "不安", "怒り", "怖い", "大問題",
        "真っ赤な嘘", "アホらし", "最悪", "ひどい"
    ],
    "金銭・送金要求": [
        "送金", "振込", "口座", "支払い", "支払", "納付", "料金",
        "保険料", "未納", "請求", "PayPay"
    ]
}


# -----------------------------
# ストップワード
# -----------------------------
STOPWORDS = {
    "これ", "それ", "あれ", "ここ", "そこ", "ため", "よう", "こと",
    "もの", "さん", "する", "いる", "ある", "なる", "れる", "られる",
    "です", "ます", "ください", "について", "として",
    "為る", "下さる", "居る", "有る", "行う", "場合", "以下",
    "見る", "出来る", "言う", "おく", "成る", "仕舞う"
}


# -----------------------------
# 基本関数
# -----------------------------
def clean_text(text):
    """余分な空白や句点を整理する。"""

    text = str(text)
    text = text.replace("\u3000", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"。{2,}", "。", text)
    return text.strip()


def split_sentences(text):
    """日本語の句点で文単位に分割する。"""

    text = clean_text(text)
    sentences = []

    for sentence in re.split(r"(?<=。)", text):
        sentence = clean_text(sentence)

        if sentence:
            sentences.append(sentence)

    return sentences


def contains_any(text, words):
    return any(word in text for word in words)


def count_any(text, words):
    return sum(1 for word in words if word in text)


def get_priority_index(category, problem_type):
    priority = TYPE_PRIORITY.get(problem_type, [])

    if category in priority:
        return priority.index(category)

    return 999


# -----------------------------
# explanations.json 読み込み
# -----------------------------
def load_allowed_categories():
    """
    explanations.json から正式なカテゴリ一覧を読み込む。
    読めない場合は DEFAULT_CATEGORIES を使う。
    """

    path = Path(EXPLANATIONS_PATH)

    if not path.exists():
        print(f"{EXPLANATIONS_PATH} が見つかりません。DEFAULT_CATEGORIESを使います。")
        return DEFAULT_CATEGORIES

    try:
        with open(path, "r", encoding="utf-8") as f:
            explanations = json.load(f)

        categories = []

        for item in explanations:
            category = item.get("category")

            if category and category not in categories:
                categories.append(category)

        # 保険としてDEFAULT_CATEGORIESも追加
        for category in DEFAULT_CATEGORIES:
            if category not in categories:
                categories.append(category)

        return categories

    except Exception as e:
        print("explanations.json の読み込みに失敗しました:", e)
        return DEFAULT_CATEGORIES


# -----------------------------
# category_rules.json 読み込み
# -----------------------------
def normalize_rule(rule):
    """
    category_rules.json の各カテゴリルールを安全な形式に整える。
    strong_keywords / weak_keywords / regex / reason がなくても落ちないようにする。
    """

    if not isinstance(rule, dict):
        rule = {}

    return {
        "strong_keywords": rule.get("strong_keywords", []),
        "weak_keywords": rule.get("weak_keywords", []),
        "regex": rule.get("regex", []),
        "reason": rule.get("reason", "")
    }


def load_category_rules(allowed_categories):
    """
    data/category_rules.json から危険語ルールを読み込む。
    explanations.json に存在しないカテゴリは採用しない。
    """

    path = Path(CATEGORY_RULES_PATH)

    if not path.exists():
        print(f"{CATEGORY_RULES_PATH} が見つかりません。")
        print("先に data/category_rules.json を作成してください。")
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_rules = json.load(f)

        if not isinstance(raw_rules, dict):
            print("category_rules.json の形式が正しくありません。")
            return {}

        category_rules = {}

        for category, rule in raw_rules.items():
            if category not in allowed_categories:
                print(f"警告: explanations.json に存在しないカテゴリのため無視します: {category}")
                continue

            category_rules[category] = normalize_rule(rule)

        return category_rules

    except Exception as e:
        print("category_rules.json の読み込みに失敗しました:", e)
        return {}


# -----------------------------
# 形態素解析
# -----------------------------
def analyze_text(text):
    """SudachiPyで形態素解析し、重要語を抽出する。"""

    text = clean_text(text)

    tokens = []
    important_words = []

    if not SUDACHI_AVAILABLE:
        # SudachiPyが使えない場合の簡易フォールバック
        words = re.findall(r"[A-Za-z0-9一-龥ぁ-んァ-ンー]+", text)

        for word in words:
            if len(word) >= 2 and word not in STOPWORDS:
                important_words.append(word)

        important_words = list(dict.fromkeys(important_words))
        return tokens, important_words

    morphemes = tokenizer_obj.tokenize(text, SPLIT_MODE)

    for m in morphemes:
        surface = m.surface()

        try:
            normalized = m.normalized_form()
        except Exception:
            normalized = surface

        try:
            pos = m.part_of_speech()
        except Exception:
            pos = ("", "", "", "", "", "")

        pos_major = pos[0] if len(pos) > 0 else ""

        token_info = {
            "surface": surface,
            "normalized": normalized,
            "pos": list(pos)
        }

        tokens.append(token_info)

        # 名詞・動詞・形容詞を重要語として扱う
        if pos_major in ["名詞", "動詞", "形容詞"]:
            word = normalized

            if len(word) >= 2 and word not in STOPWORDS:
                important_words.append(word)

    important_words = list(dict.fromkeys(important_words))

    return tokens, important_words


# -----------------------------
# URL抽出
# -----------------------------
def extract_urls(text):
    """本文中のURLを抽出する。"""

    text = clean_text(text)
    return re.findall(r"https?://[^\s　]+", text)


# -----------------------------
# evidence 抽出
# -----------------------------
def extract_evidence_sentence(text, matched_word):
    """一致した語を含む文を evidence として取り出す。"""

    text = clean_text(text)
    matched_word = clean_text(matched_word)

    if not matched_word:
        return ""

    sentences = split_sentences(text)

    for sentence in sentences:
        if matched_word in sentence:
            return sentence

    index = text.find(matched_word)

    if index == -1:
        return matched_word

    start = max(0, index - 30)
    end = min(len(text), index + len(matched_word) + 30)

    return text[start:end]


def shorten_evidence(evidence, max_length=90):
    """evidence が長すぎる場合に短くする。"""

    evidence = clean_text(evidence)

    if len(evidence) <= max_length:
        return evidence

    return evidence[:max_length] + "..."


def extract_phrase_around_keyword(text, keyword, max_length=90):
    """キーワード周辺を短い根拠として取り出す。"""

    text = clean_text(text)
    keyword = clean_text(keyword)

    if not keyword:
        return ""

    index = text.find(keyword)

    if index == -1:
        return ""

    window = max(25, max_length // 2)
    start = max(0, index - window)
    end = min(len(text), index + len(keyword) + window)

    phrase = text[start:end]
    phrase = phrase.strip("、。 ")

    if len(phrase) > max_length:
        phrase = phrase[:max_length] + "..."

    return phrase


def make_category_evidence(text, category, evidence_sentences, matched_words):
    """
    evidence候補から、カテゴリの根拠として見やすい短い表現を作る。
    まずカテゴリ別ヒント語を含む文を優先する。
    """

    text = clean_text(text)
    hints = CATEGORY_EVIDENCE_HINTS.get(category, [])

    # 1. evidence_sentencesの中でカテゴリヒント語を含むものを優先
    for sentence in evidence_sentences:
        sentence = clean_text(sentence)

        if not sentence:
            continue

        if hints and contains_any(sentence, hints):
            if len(sentence) <= 90:
                return sentence

            # 長い場合はヒント語周辺を抜く
            for hint in hints:
                if hint in sentence:
                    phrase = extract_phrase_around_keyword(sentence, hint)

                    if phrase:
                        return phrase

    # 2. 本文からカテゴリヒント語の周辺を抜く
    for hint in hints:
        if hint in text:
            phrase = extract_phrase_around_keyword(text, hint)

            if phrase:
                return phrase

    # 3. matched_words周辺を抜く
    for word in matched_words:
        phrase = extract_phrase_around_keyword(text, word)

        if phrase:
            return phrase

    # 4. 最後の保険
    for sentence in evidence_sentences:
        sentence = clean_text(sentence)

        if sentence:
            return shorten_evidence(sentence)

    return ""


# -----------------------------
# カテゴリ別の文脈チェック・補助加点
# -----------------------------
def has_required_context(category, text, matched_words, strong_hit_count, problem_type=""):
    """
    弱い誤検出を防ぐため、カテゴリごとに必要な文脈を確認する。
    7:3の目標に近づけるため、明確な文脈があるものは通し、
    「ログイン」「動画」「電話番号」だけのような弱い一致は落とす。
    """

    text = clean_text(text)
    text_lower = text.lower()

    if category == "URL偽装":
        # 「ログイン」だけではURL偽装にしない。
        # URL・リンク・偽サイトなど、誘導先の存在が分かる場合だけ採用する。
        direct_url_words = [
            "http://",
            "https://",
            "url",
            "リンク",
            "ドメイン",
            "フィッシングサイト",
            "偽サイト",
            "本物そっくりの偽サイト",
            "メールに記載されたURL",
            "本文に記載されたURL",
            "URLをクリック",
            "リンクを開"
        ]

        fake_login_context = (
            "ログイン" in text
            and contains_any(text, [
                "偽サイト",
                "本物そっくり",
                "メールに記載されたURL",
                "本文に記載されたURL",
                "URLをクリック",
                "リンクを開",
                "フィッシングサイト"
            ])
        )

        return contains_any(text_lower, ["http://", "https://", "url"]) or contains_any(text, direct_url_words) or fake_login_context

    if category == "なりすまし":
        strong_context_words = [
            "なりすました",
            "なりすまし",
            "よそおう",
            "かたる",
            "装う",
            "偽のメール",
            "正規のメールアドレス",
            "社長になりすました",
            "社長になりすまし",
            "担当者になりすました",
            "担当者になりすまし",
            "取引相手になりすます",
            "日本年金",
            "日本年金機構",
            "国勢調査への協力",
            "国勢調査",
            "証券会社を名乗る",
            "銀行を名乗る"
        ]

        return any(word in text for word in strong_context_words) or strong_hit_count >= 2

    if category == "緊急性誘導":
        strong_context_words = [
            "24時間以内",
            "48時間以内",
            "本日中",
            "至急",
            "今すぐ",
            "最終確認",
            "最終通知",
            "差押",
            "執行予告",
            "永久停止",
            "アカウントが停止",
            "期限内",
            "未回答の場合は罰則"
        ]

        return any(word in text for word in strong_context_words)

    if category == "個人情報要求":
        # 電話番号は「相手に電話するための番号」として出ることがあるため、
        # それ単独では個人情報要求にしない。
        private_core_words = [
            "パスワード",
            "暗証番号",
            "認証コード",
            "確認コード",
            "クレジットカード番号",
            "カード番号",
            "セキュリティコード",
            "住所",
            "個人情報",
            "アカウントID",
            "ユーザネーム",
            "IDやパスワード",
            "情報が詐取"
        ]

        phone_request_words = [
            "電話番号を入力",
            "電話番号の入力",
            "電話番号を求め",
            "電話番号を聞",
            "電話番号を教"
        ]

        bank_account_words = [
            "ネットバンキングにログインさせられ",
            "銀行のアプリを開こう",
            "銀行のアプリを開かせ",
            "他に口座がないか",
            "口座がないか",
            "口座情報",
            "銀行口座情報"
        ]

        return (
            contains_any(text, private_core_words)
            or contains_any(text, phone_request_words)
            or contains_any(text, bank_account_words)
        )

    if category == "フェイクニュース":
        spread_words = [
            "拡散",
            "投稿",
            "SNS",
            "Xで",
            "Twitter",
            "主張",
            "リポスト",
            "表示回数"
        ]

        correction_words = [
            "誤りです",
            "誤り",
            "誤りと判定",
            "不正確",
            "事実ではない",
            "事実はない",
            "デマ",
            "ガセネタ",
            "虚偽",
            "偽情報",
            "誤情報",
            "偽画像",
            "偽だと認め",
            "実際には",
            "実際の",
            "異なる",
            "確認できない",
            "否定",
            "全体ではなく",
            "意味ではありません",
            "誤解を招く",
            "ミスリード",
            "AIで作られた",
            "AIで作成"
        ]

        return (
            contains_any(text, spread_words)
            and contains_any(text, correction_words)
        ) or (
            problem_type == "fake_news"
            and strong_hit_count >= 1
            and contains_any(text, spread_words)
        )

    if category == "画像のミスリード":
        # 「動画が添付」だけでは採用しない。
        # 別時期・別場所・過去・無関係・加工・AI生成・偽画像などの文脈が必要。
        image_words = [
            "画像",
            "写真",
            "動画",
            "映像",
            "スクリーンショット",
            "ChatGPT",
            "GPT"
        ]

        mismatch_words = [
            "別の時期",
            "別の場所",
            "過去の",
            "数年前",
            "海外の写真",
            "無関係",
            "実際には別",
            "AI生成",
            "生成AI画像",
            "AIで作られた",
            "AIで作成",
            "作られた画像",
            "偽画像",
            "加工",
            "切り抜き",
            "文脈が異なる",
            "実際とは異なる文脈"
        ]

        return contains_any(text, image_words) and contains_any(text, mismatch_words)

    if category == "統計の悪用":
        # リポスト数や表示回数だけでは統計の悪用にしない。
        # 数字・割合 + 対象範囲のズレ がある場合に採用する。
        has_number = re.search(r"\d+\s*(%|％|割|件|人|回)", text) is not None

        scope_words = [
            "調査対象",
            "サンプル",
            "少人数",
            "対象",
            "全体",
            "一部",
            "疑わしい",
            "約300件",
            "300件",
            "調査結果",
            "全体ではなく",
            "意味ではありません",
            "母集団",
            "割合だけ",
            "経営ビザ取得者の9割",
            "9割が不正"
        ]

        return has_number and contains_any(text, scope_words)

    if category == "誇張表現":
        # 「だけで」「たった」だけでは採用しない。
        strong_words = [
            "必ず",
            "絶対",
            "誰でも",
            "確実に",
            "完全に",
            "100%",
            "世界一",
            "史上最悪",
            "一瞬で",
            "すぐに稼げる",
            "必ず成功",
            "誰でも成功",
            "100%成功",
            "飛び上がるぐらい"
        ]

        false_positive_contexts = [
            "開いただけでは被害に繋がることはない",
            "受信しただけでは",
            "アクセスしただけでは",
            "入力していない場合",
            "問題ない"
        ]

        if contains_any(text, false_positive_contexts):
            return False

        return contains_any(text, strong_words)

    if category == "出典不明":
        source_words = [
            "出典不明",
            "出典なし",
            "出典は書かれていません",
            "根拠なし",
            "情報源なし",
            "出所不明",
            "発信元不明",
            "根拠が確認できない",
            "公式な根拠がない",
            "公式発表ではない",
            "公式発表や報道に基づくものではない"
        ]

        return contains_any(text, source_words)

    if category == "添付ファイルの危険性":
        return (
            "添付ファイル" in text
            or ".exe" in text_lower
            or ".zip" in text_lower
            or ".docm" in text_lower
            or ".xlsm" in text_lower
            or ".bat" in text_lower
            or ".scr" in text_lower
            or "ファイルを開いて" in text
        )

    if category == "感情的表現":
        emotional_words = [
            "ぜったいにまずい",
            "許せない",
            "恐怖",
            "助けて",
            "拡散希望",
            "不安をあおる",
            "真っ赤な嘘",
            "アホらし",
            "ありえない",
            "最悪",
            "ひどい",
            "怖すぎる",
            "危なすぎる",
            "怒り",
            "炎上",
            "差別的",
            "悪さをする",
            "大問題",
            "飛び上がるぐらい嬉しい"
        ]

        return contains_any(text, emotional_words)

    if category == "金銭・送金要求":
        money_words = [
            "送金",
            "偽の口座",
            "偽口座",
            "振込先口座変更",
            "口座振込",
            "金銭の支払",
            "支払いへ誘導",
            "支払い画面",
            "納付依頼",
            "保険料",
            "未納",
            "指定する口座",
            "支払を要求",
            "金銭を詐取",
            "支払いを行わない",
            "請求",
            "料金",
            "PayPay"
        ]

        return contains_any(text, money_words)

    return True


def add_context_boost(category, text, matched_words, evidence_sentences, score, strong_hit_count):
    """
    category_rules.jsonに完全一致しない表現でも、文脈が明確な場合に補助加点する。
    これにより「AIで作られた画像」「他に口座がないか」などを拾える。
    """

    text = clean_text(text)

    if category == "画像のミスリード":
        phrases = [
            "AIで作られた画像",
            "AIで作成された画像",
            "AI生成画像",
            "生成AI画像",
            "偽画像"
        ]

        for phrase in phrases:
            if phrase in text and phrase not in matched_words:
                matched_words.append(phrase)
                evidence_sentences.append(extract_evidence_sentence(text, phrase))
                score += 3
                strong_hit_count += 1

    if category == "フェイクニュース":
        if contains_any(text, ["拡散", "投稿", "Xで", "Twitter", "SNS"]):
            phrases = [
                "偽画像",
                "不正確",
                "誤り",
                "事実ではない",
                "AIで作られた",
                "偽だと認め"
            ]

            for phrase in phrases:
                if phrase in text and phrase not in matched_words:
                    matched_words.append(phrase)
                    evidence_sentences.append(extract_evidence_sentence(text, phrase))
                    score += 2
                    strong_hit_count += 1

    if category == "個人情報要求":
        phrases = [
            "IDやパスワード",
            "情報が詐取",
            "ネットバンキングにログインさせられ",
            "他に口座がないか",
            "口座がないか",
            "銀行口座情報"
        ]

        for phrase in phrases:
            if phrase in text and phrase not in matched_words:
                matched_words.append(phrase)
                evidence_sentences.append(extract_evidence_sentence(text, phrase))
                score += 2
                strong_hit_count += 1

    return matched_words, evidence_sentences, score, strong_hit_count


# -----------------------------
# 危険カテゴリ検出
# -----------------------------
def detect_danger_categories(text, important_words, category_rules, problem_type=""):
    """
    危険語ルールに基づいてカテゴリ候補を抽出する。
    単なる一致ではなく、スコア・文脈チェック・type優先順位で安定化する。
    """

    text = clean_text(text)
    detected = []

    for category, rule in category_rules.items():
        matched_words = []
        evidence_sentences = []
        score = 0
        strong_hit_count = 0
        weak_hit_count = 0
        regex_hit_count = 0

        strong_keywords = rule.get("strong_keywords", [])
        weak_keywords = rule.get("weak_keywords", [])
        regex_patterns = rule.get("regex", [])

        # strong keyword
        for keyword in strong_keywords:
            keyword = str(keyword)

            if keyword.lower() in text.lower():
                matched_words.append(keyword)
                evidence_sentences.append(extract_evidence_sentence(text, keyword))
                score += 2
                strong_hit_count += 1

        # weak keyword
        for keyword in weak_keywords:
            keyword = str(keyword)

            if keyword.lower() in text.lower():
                matched_words.append(keyword)
                evidence_sentences.append(extract_evidence_sentence(text, keyword))
                score += 1
                weak_hit_count += 1

        # SudachiPy重要語との完全一致
        for word in important_words:
            for keyword in strong_keywords:
                keyword = str(keyword)

                if keyword.lower() == word.lower():
                    matched_words.append(word)
                    evidence_sentences.append(extract_evidence_sentence(text, word))
                    score += 2
                    strong_hit_count += 1

            for keyword in weak_keywords:
                keyword = str(keyword)

                if keyword.lower() == word.lower():
                    matched_words.append(word)
                    evidence_sentences.append(extract_evidence_sentence(text, word))
                    score += 1
                    weak_hit_count += 1

        # 正規表現
        for pattern in regex_patterns:
            try:
                for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                    original_match_text = match.group(0)
                    display_match_text = original_match_text

                    if len(display_match_text) > 80:
                        display_match_text = display_match_text[:80] + "..."

                    matched_words.append(display_match_text)
                    evidence_sentences.append(extract_evidence_sentence(text, original_match_text))
                    score += 3
                    strong_hit_count += 1
                    regex_hit_count += 1

            except re.error as e:
                print(f"正規表現エラー: category={category}, pattern={pattern}, error={e}")

        matched_words, evidence_sentences, score, strong_hit_count = add_context_boost(
            category=category,
            text=text,
            matched_words=matched_words,
            evidence_sentences=evidence_sentences,
            score=score,
            strong_hit_count=strong_hit_count
        )

        matched_words = list(dict.fromkeys(matched_words))

        if not matched_words:
            continue

        # カテゴリごとの文脈チェック
        if not has_required_context(
            category=category,
            text=text,
            matched_words=matched_words,
            strong_hit_count=strong_hit_count,
            problem_type=problem_type
        ):
            continue

        # typeと相性が良いカテゴリには小さなボーナス
        if category in TYPE_PRIORITY.get(problem_type, []):
            priority_index = get_priority_index(category, problem_type)

            # 上位カテゴリほど少しだけ加点
            if priority_index <= 2:
                score += 1

        min_score = CATEGORY_MIN_SCORE.get(category, 2)

        if score < min_score:
            continue

        evidence = make_category_evidence(
            text=text,
            category=category,
            evidence_sentences=evidence_sentences,
            matched_words=matched_words
        )

        if not evidence:
            continue

        confidence = score + strong_hit_count + regex_hit_count

        detected.append({
            "category": category,
            "score": score,
            "confidence": confidence,
            "strong_hit_count": strong_hit_count,
            "weak_hit_count": weak_hit_count,
            "regex_hit_count": regex_hit_count,
            "priority_index": get_priority_index(category, problem_type),
            "matched_words": matched_words,
            "evidence": evidence,
            "reason": rule.get("reason", "")
        })

    detected = sort_detected_categories(detected, problem_type)

    return detected


# -----------------------------
# カテゴリ選択
# -----------------------------
def sort_detected_categories(detected_categories, problem_type):
    """
    スコアだけでなく、typeごとの優先順位も使って並び替える。
    """

    return sorted(
        detected_categories,
        key=lambda item: (
            item.get("priority_index", 999),
            -item.get("confidence", 0),
            -item.get("score", 0)
        )
    )


def remove_conflicting_categories(detected_categories, problem_type):
    """
    誤判定しやすいカテゴリの組み合わせを整理する。
    例：fake_newsで「統計の悪用」が明確なら、「動画が添付」程度の画像のミスリードは外す。
    """

    categories = [item["category"] for item in detected_categories]

    # fake_newsで統計の悪用がある場合、画像のミスリードは本当に強いときだけ残す
    if problem_type == "fake_news" and "統計の悪用" in categories:
        new_items = []

        for item in detected_categories:
            if item["category"] == "画像のミスリード":
                # 画像のミスリードは高信頼の時だけ残す
                if item.get("confidence", 0) >= 7 and item.get("strong_hit_count", 0) >= 2:
                    new_items.append(item)
                continue

            new_items.append(item)

        detected_categories = new_items

    # phishingでフェイクニュース・統計の悪用が混ざった場合は、基本的には関連カテゴリへ落とす
    if problem_type == "phishing":
        lower_priority = {"フェイクニュース", "統計の悪用", "画像のミスリード"}

        phishing_items = [
            item for item in detected_categories
            if item["category"] not in lower_priority
        ]

        if phishing_items:
            detected_categories = phishing_items + [
                item for item in detected_categories
                if item["category"] in lower_priority
            ]

    return detected_categories


def select_answer_categories(detected_categories, problem_type=""):
    """
    検出カテゴリの中から、主な危険要素だけを正解にする。
    そのまま追加できる候補を増やすため、基本は最大2カテゴリ。
    """

    if not detected_categories:
        return [], []

    detected_categories = sort_detected_categories(detected_categories, problem_type)
    detected_categories = remove_conflicting_categories(detected_categories, problem_type)

    selected = detected_categories[:MAX_ANSWER_CATEGORIES]
    related = detected_categories[MAX_ANSWER_CATEGORIES:]

    answer_categories = [
        item["category"]
        for item in selected
    ]

    related_categories = [
        item["category"]
        for item in related
    ]

    return answer_categories, related_categories


# -----------------------------
# 選択肢生成
# -----------------------------
def make_choices(answer_categories, allowed_categories, seed_value, problem_type=""):
    """
    正解カテゴリ + ダミー選択肢で5択を作る。
    ダミーはtypeに近いカテゴリから優先して選ぶため、見栄えが自然になる。
    """

    random.seed(seed_value)

    priority = TYPE_PRIORITY.get(problem_type, [])

    priority_distractors = [
        category
        for category in priority
        if category in allowed_categories and category not in answer_categories
    ]

    other_distractors = [
        category
        for category in allowed_categories
        if category not in answer_categories and category not in priority_distractors
    ]

    random.shuffle(priority_distractors)
    random.shuffle(other_distractors)

    distractors = priority_distractors + other_distractors

    choices = answer_categories + distractors[:max(0, CHOICE_COUNT - len(answer_categories))]
    choices = choices[:CHOICE_COUNT]

    random.shuffle(choices)

    return choices


# -----------------------------
# 難易度推定
# -----------------------------
def estimate_difficulty(text, answer_categories):
    """文章の長さと正解数から難易度を決める。"""

    length = len(text)
    answer_count = len(answer_categories)

    if answer_count == 0:
        return 0

    if answer_count <= 1 and length <= 140:
        return 1

    if answer_count <= 2 and length <= 280:
        return 2

    return 3


# -----------------------------
# 品質判定
# -----------------------------
def is_ambiguous_single_answer(problem_type, answer_categories):
    """
    単独正解にすると誤判定しやすいカテゴリを判定する。
    これらはreviewへ回すが、他カテゴリとセットならvalidにできることがある。
    """

    if problem_type == "fake_news" and answer_categories in [
        ["画像のミスリード"],
        ["誇張表現"],
        ["感情的表現"]
    ]:
        return True

    return False


def make_quality_flags(candidate):
    """
    validation_errorsとは別に、自動追加するには少し危ない候補を抽出する。
    ここを厳しすぎるとvalidが減るため、明確に危ない条件だけにする。
    """

    flags = []

    problem_type = candidate.get("type", "")
    answer = candidate.get("answer", [])
    answer_details = candidate.get("answer_details", [])
    detected = candidate.get("detected_categories", [])

    if not answer:
        flags.append("正解カテゴリが空のため確認が必要です。")

    if len(answer) > MAX_ANSWER_CATEGORIES:
        flags.append("正解カテゴリが多すぎるため確認が必要です。")

    if is_ambiguous_single_answer(problem_type, answer):
        flags.append("fake_newsで曖昧カテゴリ単独のため確認が必要です。")

    # 正解カテゴリのconfidenceが低すぎる場合は確認
    confidence_by_category = {
        item.get("category"): item.get("confidence", 0)
        for item in detected
    }

    for category in answer:
        if confidence_by_category.get(category, 0) < 4:
            flags.append(f"カテゴリ根拠の信頼度が低いため確認が必要です: {category}")

    for detail in answer_details:
        evidence = clean_text(detail.get("evidence", ""))

        if not evidence:
            flags.append(f"evidenceが空です: {detail.get('category', '')}")

        if len(evidence) > 110:
            flags.append(f"evidenceが長いため確認が必要です: {detail.get('category', '')}")

    return flags


# -----------------------------
# 問題候補の検証
# -----------------------------
def validate_candidate(candidate, allowed_categories):
    """生成した問題候補の最低限の品質をチェックする。"""

    errors = []

    text = candidate.get("text", "")
    choices = candidate.get("choices", [])
    answer = candidate.get("answer", [])
    answer_details = candidate.get("answer_details", [])

    if len(text) < MIN_TEXT_LENGTH:
        errors.append("問題文が短すぎます。")

    if len(text) > MAX_TEXT_LENGTH:
        errors.append("問題文が長すぎます。")

    if len(answer) == 0:
        errors.append("危険要素を自動検出できませんでした。人間による確認が必要です。")

    if len(answer) > MAX_ANSWER_CATEGORIES:
        errors.append("正解カテゴリ数が多すぎます。")

    if len(choices) != CHOICE_COUNT:
        errors.append("選択肢が5個ではありません。")

    if set(answer) - set(choices):
        errors.append("正解カテゴリが選択肢に含まれていません。")

    if len(answer) == len(choices) and len(answer) > 0:
        errors.append("選択肢がすべて正解になっています。")

    for category in answer:
        if category not in allowed_categories:
            errors.append(f"explanations.jsonに存在しないカテゴリです: {category}")

    for detail in answer_details:
        evidence = detail.get("evidence", "")

        if not evidence:
            errors.append(f"evidenceが空です: {detail.get('category', '')}")

    return errors


# -----------------------------
# 問題候補生成
# -----------------------------
def make_problem_candidate(case, detected_categories, important_words, urls, allowed_categories):
    """抽出結果から、problems.jsonに近い形式の問題候補を作る。"""

    case_id = case.get("id")
    text = clean_text(case.get("text", ""))
    title = case.get("title", "")
    problem_type = case.get("type", "")

    answer_categories, related_categories = select_answer_categories(
        detected_categories=detected_categories,
        problem_type=problem_type
    )

    selected_details = [
        item
        for item in detected_categories
        if item["category"] in answer_categories
    ]

    # selected_detailsもanswer順に並べる
    selected_details = sorted(
        selected_details,
        key=lambda item: answer_categories.index(item["category"])
        if item["category"] in answer_categories else 999
    )

    choices = make_choices(
        answer_categories=answer_categories,
        allowed_categories=allowed_categories,
        seed_value=case_id,
        problem_type=problem_type
    )

    difficulty = estimate_difficulty(text, answer_categories)

    answer_details = []

    for item in selected_details:
        answer_details.append({
            "category": item["category"],
            "evidence": item["evidence"],
            "reason": item["reason"]
        })

    candidate = {
        "id": case_id,
        "type": problem_type,
        "question": QUESTION_TEXT,
        "text": text,
        "choices": choices,
        "answer": answer_categories,
        "category": answer_categories,
        "related_categories": related_categories,
        "difficulty": difficulty,
        "answer_details": answer_details,
        "source": case.get("source", ""),
        "title": title,
        "url": case.get("url", ""),
        "source_page_id": case.get("source_page_id"),
        "text_length": len(text),
        "important_words": important_words[:20],
        "urls": urls,
        "detected_categories": [
            {
                "category": item["category"],
                "score": item["score"],
                "confidence": item.get("confidence", 0),
                "strong_hit_count": item.get("strong_hit_count", 0),
                "weak_hit_count": item.get("weak_hit_count", 0),
                "regex_hit_count": item.get("regex_hit_count", 0),
                "matched_words": item["matched_words"],
                "evidence": item["evidence"]
            }
            for item in detected_categories
        ],
        "auto_generated": True
    }

    validation_errors = validate_candidate(candidate, allowed_categories)
    quality_flags = make_quality_flags(candidate)

    candidate["validation_status"] = "valid" if len(validation_errors) == 0 else "needs_review"
    candidate["validation_errors"] = validation_errors
    candidate["quality_flags"] = quality_flags

    # create_approved_candidates.py側で使いやすいように、事前判定を持たせる
    candidate["auto_approval_hint"] = (
        "auto_ready"
        if candidate["validation_status"] == "valid" and not quality_flags
        else "review"
    )

    candidate["review_required"] = candidate["auto_approval_hint"] != "auto_ready"

    return candidate


# -----------------------------
# メイン処理
# -----------------------------
def main():
    raw_path = Path(RAW_CASES_PATH)

    if not raw_path.exists():
        print(f"{RAW_CASES_PATH} が見つかりません。")
        print("先に py segment_cases.py を実行して data/raw_cases.json を作成してください。")
        return

    with open(RAW_CASES_PATH, "r", encoding="utf-8") as f:
        raw_cases = json.load(f)

    allowed_categories = load_allowed_categories()
    category_rules = load_category_rules(allowed_categories)

    if not category_rules:
        print("危険語ルールを読み込めなかったため、処理を終了します。")
        return

    candidates = []

    print("=" * 70)
    print("problem_generator.py 改善版を実行します。")
    print("SudachiPy:", "使用可能" if SUDACHI_AVAILABLE else "未使用（簡易解析）")
    print("カテゴリ数:", len(allowed_categories))
    print("危険語ルール数:", len(category_rules))
    print("設定:", AUTO_READY_TARGET_NOTE)

    for case in raw_cases:
        text = clean_text(case.get("text", ""))
        problem_type = case.get("type", "")

        tokens, important_words = analyze_text(text)
        urls = extract_urls(text)

        detected_categories = detect_danger_categories(
            text=text,
            important_words=important_words,
            category_rules=category_rules,
            problem_type=problem_type
        )

        candidate = make_problem_candidate(
            case=case,
            detected_categories=detected_categories,
            important_words=important_words,
            urls=urls,
            allowed_categories=allowed_categories
        )

        if DEBUG_TOKENS:
            candidate["morphological_tokens"] = tokens[:80]

        candidates.append(candidate)

        print("=" * 70)
        print(f"ID: {case.get('id')}")
        print(f"type: {problem_type}")
        print(f"タイトル: {case.get('title', '')}")
        print(f"文字数: {len(text)}")
        print("重要語:", " / ".join(important_words[:15]))

        if candidate["answer"]:
            print("正解カテゴリ:", " / ".join(candidate["answer"]))
        else:
            print("正解カテゴリ: なし")

        print(
            "関連カテゴリ:",
            " / ".join(candidate["related_categories"])
            if candidate["related_categories"]
            else "なし"
        )

        print("検証:", candidate["validation_status"])
        print("自動追加ヒント:", candidate["auto_approval_hint"])

        if candidate["validation_errors"]:
            print("検証エラー:")
            for error in candidate["validation_errors"]:
                print(" -", error)

        if candidate["quality_flags"]:
            print("品質フラグ:")
            for flag in candidate["quality_flags"]:
                print(" -", flag)

    output_path = Path(OUTPUT_PATH)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)

    auto_ready_count = sum(
        1 for item in candidates
        if item.get("auto_approval_hint") == "auto_ready"
    )

    review_count = len(candidates) - auto_ready_count

    print("=" * 70)
    print(f"問題候補を出力しました: {OUTPUT_PATH}")
    print(f"auto_ready: {auto_ready_count} 件")
    print(f"review: {review_count} 件")

    if candidates:
        auto_ready_rate = auto_ready_count / len(candidates) * 100
        print(f"auto_ready率: {auto_ready_rate:.1f}%")
        print("目標: auto_ready 約70%、review 約30%")

    print("auto_ready はそのまま追加しやすい候補です。")
    print("review は人間が確認・修正してください。")


if __name__ == "__main__":
    main()
