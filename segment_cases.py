import json
import re
from pathlib import Path


RAW_PAGES_PATH = "data/raw_pages.json"
OUTPUT_PATH = "data/raw_cases.json"

MIN_CASE_LENGTH = 60
MAX_CASE_LENGTH = 450

# 1ページから大量に作らないための安全上限
# ただし、明確に異なる危険トピックなら複数作る
MAX_CASES_PER_PAGE = 5

# 通常抽出で0件だったときだけ使う救済抽出の上限
MAX_SIGNAL_CASES = 3


# ============================================================
# 基本整形
# ============================================================

def clean_text(text):
    text = str(text)
    text = text.replace("\u3000", " ")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    text = re.sub(r"。{2,}", "。", text)
    return text.strip()


def clean_inline_text(text):
    text = clean_text(text)
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_sentences(text):
    text = clean_inline_text(text)
    sentences = []

    for sentence in re.split(r"(?<=[。！？])", text):
        sentence = clean_inline_text(sentence)
        if sentence:
            sentences.append(sentence)

    return sentences


def contains_any(text, words):
    return any(word in text for word in words)


def trim_to_limit(text, max_length=MAX_CASE_LENGTH):
    text = clean_inline_text(text)

    if len(text) <= max_length:
        return text

    result = ""

    for sentence in split_sentences(text):
        if len(result) + len(sentence) <= max_length:
            result += sentence
        else:
            break

    result = clean_inline_text(result)

    if result:
        return result

    return text[:max_length]


# ============================================================
# 汎用的に除外したい文
# 特定URLではなく、どのサイトでも混ざりやすい
# メニュー・一覧・対策・FAQ・問い合わせを落とす
# ============================================================

NOISE_WORDS = [
    # サイト共通のナビゲーション・メニュー
    "HOME >",
    "ホーム >",
    "ニュース記事集",
    "ニュース 緊急情報",
    "協議会からのお知らせ",
    "プライバシーポリシー",
    "コンテンツ利用について",
    "ニュースレター登録",
    "お問い合わせ",
    "相談窓口",
    "関連リンク",
    "参考情報",
    "ページの先頭",
    "更新履歴",
    "Copyright",
    "このページに関するお問い合わせ",
    "サイトマップ",
    "推奨環境",

    # 組織紹介・パンフレット系
    "組織概要",
    "会長挨拶",
    "運営委員紹介",
    "メンバー",
    "入会案内",
    "パンフレット",
    "活動 WG活動",

    # 説明・資料一覧系
    "報告書類",
    "ガイドライン",
    "月次報告書",
    "協議会WG報告書",
    "消費者の皆様へ",
    "サービス事業者の皆様へ",
    "マンガでわかる",
    "STOP. THINK. CONNECT",

    # 記事一覧・例一覧だけの見出し
    "メール・SMSの文面例",
    "フィッシングサイトの例",
    "過去の緊急情報",
    "一覧"
]


AFTERCARE_WORDS = [
    # 注意・対策・確認を促す文
    "ご注意ください",
    "注意してください",
    "確認してください",
    "相談してください",
    "連絡してください",
    "削除してください",
    "通報してください",
    "ご報告ください",
    "心がけてください",
    "推奨します",
    "検討してください",

    # 被害後対応
    "パスワードを変更",
    "パスワードの変更",
    "不正送金の有無",
    "銀行に相談",
    "警察に相談",
    "IPAに相談",
    "対策として",
    "被害にあった場合",
    "不審な場合は",
    "アクセスしない",
    "入力しない",
    "利用しないでください",
    "アクセスしなおす",
    "公式アプリやブラウザーのブックマーク",

    # FAQ・説明寄り
    "よくある質問",
    "よくあるご質問",
    "被害にはつながりません",
    "影響はありません",
    "インストールしていなければ",
    "何の操作も入力もせず",
    "入力した内容に応じた対処方法"
]


DEFINITION_WORDS = [
    "フィッシングとは",
    "とは実在する組織を騙って",
    "フィッシングの報告",
    "なりすまし送信メール対策",
    "今すぐできるフィッシング対策"
]


def is_noise_text(text):
    text = clean_inline_text(text)

    if contains_any(text, NOISE_WORDS):
        return True

    if contains_any(text, AFTERCARE_WORDS):
        return True

    if contains_any(text, DEFINITION_WORDS):
        return True

    # 日付つき記事一覧が複数並ぶものを除外
    date_article_count = len(
        re.findall(r"20\d{2}年\d{1,2}月\d{1,2}日[^。]{0,80}フィッシング", text)
    )

    if date_article_count >= 2:
        return True

    # パンくず・メニューが多いものを除外
    if text.count(">") >= 2:
        return True

    return False


def remove_figure_descriptions(text):
    text = clean_inline_text(text)

    text = re.sub(r"（図\d+）", "", text)
    text = re.sub(r"\(図\d+\)", "", text)
    text = re.sub(r"図\d+[:：].*?。", "", text)
    text = re.sub(r"（?赤(?:色|い)破線部分）?", "", text)

    return clean_inline_text(text)


def remove_bad_sentences(text):
    kept = []

    for sentence in split_sentences(text):
        if is_noise_text(sentence):
            continue

        kept.append(sentence)

    return clean_inline_text("".join(kept))


def remove_duplicate_sentences(text):
    sentences = split_sentences(text)
    seen = set()
    kept = []

    for sentence in sentences:
        normalized = re.sub(r"\s+", "", sentence)

        if normalized in seen:
            continue

        seen.add(normalized)
        kept.append(sentence)

    return clean_inline_text("".join(kept))


def preprocess_case_text(text):
    text = clean_inline_text(text)
    text = remove_figure_descriptions(text)
    text = remove_bad_sentences(text)
    text = remove_duplicate_sentences(text)

    text = re.sub(r"^本文\s*", "", text)
    text = re.sub(r"^概要\s*", "", text)
    text = re.sub(r"^事例\s*", "事例", text)

    return clean_inline_text(text)


# ============================================================
# 危険トピック判定
# category判定ではなく、
# 「問題にできる攻撃・誤情報の構造があるか」を見る
# ============================================================

def get_topic_keys(text):
    text = clean_inline_text(text)
    topics = set()

    spoof_words = [
        "なりすまし",
        "なりすました",
        "かたる",
        "騙る",
        "よそおう",
        "装う",
        "名乗る",
        "偽のメール",
        "偽メール",
        "正規のメールアドレス",
        "サポート担当者",
        "取引先の担当者"
    ]

    url_words = [
        "URL",
        "リンク",
        "http://",
        "https://",
        "偽サイト",
        "フィッシングサイト",
        "偽のサイト",
        "誘導先",
        "ログインページ",
        "本物そっくりのサイト"
    ]

    credential_words = [
        "パスワード",
        "ID",
        "認証コード",
        "確認コード",
        "暗証番号",
        "カード番号",
        "クレジットカード",
        "セキュリティコード",
        "住所",
        "電話番号",
        "個人情報",
        "アカウント情報",
        "ログイン情報",
        "ギフト券番号",
        "シリアル番号",
        "PINコード"
    ]

    money_words = [
        "支払い",
        "支払",
        "送金",
        "振込",
        "口座",
        "振込先",
        "指定口座",
        "納付",
        "未納",
        "請求",
        "料金",
        "PayPay",
        "金銭",
        "ギフトカード"
    ]

    urgency_words = [
        "至急",
        "今すぐ",
        "本日中",
        "24時間以内",
        "48時間以内",
        "最終通知",
        "最終確認",
        "停止",
        "永久停止",
        "差押",
        "執行予告",
        "期限内",
        "緊急",
        "lose access"
    ]

    attachment_words = [
        "添付ファイル",
        "添付",
        ".exe",
        ".zip",
        ".docm",
        ".xlsm",
        ".bat",
        "ファイルを開"
    ]

    fake_claim_words = [
        "誤り",
        "不正確",
        "事実ではない",
        "事実と異なる",
        "実際には",
        "否定しました",
        "確認できません",
        "偽情報",
        "誤情報",
        "デマ",
        "AIで生成されたもの"
    ]

    image_words = [
        "画像",
        "写真",
        "動画",
        "映像",
        "スクリーンショット",
        "AI生成",
        "AIで生成",
        "偽画像",
        "SynthID",
        "別の時期",
        "別の場所",
        "過去の画像",
        "過去の写真"
    ]

    stats_words = [
        "統計",
        "調査対象",
        "サンプル",
        "少人数",
        "割合",
        "%",
        "％",
        "9割",
        "90%",
        "全体ではなく",
        "一部の対象"
    ]

    source_words = [
        "出典不明",
        "出典が不明",
        "根拠が不明",
        "公式発表ではない",
        "公式発表や報道に基づくものではない",
        "情報源が不明"
    ]

    emotional_words = [
        "許せない",
        "怖い",
        "危険",
        "恐怖",
        "差別",
        "根こそぎ消される",
        "拡散希望",
        "怒り",
        "真っ赤な嘘"
    ]

    exaggeration_words = [
        "絶対",
        "必ず",
        "誰でも",
        "100%",
        "世界一",
        "史上最悪",
        "完全に",
        "一瞬で",
        "1週間で100万円",
        "全員"
    ]

    if contains_any(text, spoof_words):
        topics.add("spoofing")

    if contains_any(text, url_words):
        topics.add("url")

    if contains_any(text, credential_words):
        topics.add("credential")

    if contains_any(text, money_words):
        topics.add("money")

    if contains_any(text, urgency_words):
        topics.add("urgency")

    if contains_any(text, attachment_words):
        topics.add("attachment")

    if contains_any(text, fake_claim_words):
        topics.add("fake_claim")

    if contains_any(text, image_words):
        topics.add("image")

    if contains_any(text, stats_words):
        topics.add("statistics")

    if contains_any(text, source_words):
        topics.add("source_missing")

    if contains_any(text, emotional_words):
        topics.add("emotion")

    if contains_any(text, exaggeration_words):
        topics.add("exaggeration")

    return topics


def has_attack_action(text):
    """
    危険語だけでなく、実際に行動させる・拡散される表現があるか。
    これにより対策文や定義文を落としやすくする。
    """

    action_words = [
        "受信",
        "届き",
        "届いた",
        "表示され",
        "タップ",
        "クリック",
        "アクセス",
        "誘導",
        "ログイン",
        "入力",
        "入力させる",
        "求め",
        "要求",
        "請求",
        "送金",
        "振込",
        "支払い",
        "詐取",
        "開かれた",
        "聞かれ",
        "インストール",
        "拡散",
        "投稿",
        "生成された",
        "認めています"
    ]

    return contains_any(text, action_words)


def is_subject_example(text):
    """
    件名例として問題にできるか。
    """

    text = clean_inline_text(text)

    if "件名" in text:
        return True

    if "【" in text and "】" in text:
        return True

    if "lose access" in text.lower():
        return True

    return False


def topic_group_key(text, raw_page=None):
    """
    同じURLから似た問題を増やしすぎないためのキー。
    細かいtopic全部ではなく、教材上の役割でまとめる。
    """

    if raw_page:
        combined = raw_page.get("title", "") + "。" + text
    else:
        combined = text

    topics = get_topic_keys(combined)

    if "credential" in topics and "url" in topics:
        return "phishing_url_credential"

    if "money" in topics and ("url" in topics or "spoofing" in topics):
        return "phishing_money"

    if "urgency" in topics and ("spoofing" in topics or "credential" in topics or "money" in topics):
        return "phishing_urgency"

    if "spoofing" in topics and "url" in topics:
        return "phishing_spoof_url"

    if "spoofing" in topics:
        return "phishing_spoofing"

    if "attachment" in topics:
        return "phishing_attachment"

    if "image" in topics and "fake_claim" in topics:
        return "fake_image"

    if "statistics" in topics and "fake_claim" in topics:
        return "fake_statistics"

    if "source_missing" in topics and "fake_claim" in topics:
        return "fake_source"

    if "fake_claim" in topics:
        return "fake_claim"

    return "unknown"


def is_good_case_text(text):
    text = preprocess_case_text(text)

    if len(text) < MIN_CASE_LENGTH:
        return False

    if len(text) > MAX_CASE_LENGTH * 2:
        return False

    if is_noise_text(text):
        return False

    return True


def is_high_quality_material(text, raw_page=None):
    """
    問題にしやすい重要箇所だけ通す。
    危険語1個だけでは通さない。
    """

    text = preprocess_case_text(text)

    if not is_good_case_text(text):
        return False

    if raw_page:
        combined = raw_page.get("title", "") + "。" + text
        page_type = raw_page.get("type", "")
        source = raw_page.get("source", "")
    else:
        combined = text
        page_type = ""
        source = ""

    topics = get_topic_keys(combined)

    # フィッシング系
    phishing_good = (
        ("spoofing" in topics and ("url" in topics or "credential" in topics or "money" in topics or "urgency" in topics))
        or ("url" in topics and "credential" in topics)
        or ("url" in topics and "money" in topics)
        or ("credential" in topics and "money" in topics)
        or ("credential" in topics and "urgency" in topics)
        or ("money" in topics and "urgency" in topics)
        or ("attachment" in topics)
    )

    # 件名例は、なりすまし・緊急性・金銭要求のどれかがあれば教材化できる
    subject_good = (
        is_subject_example(text)
        and ("spoofing" in topics or "urgency" in topics or "money" in topics)
    )

    # フィッシングのタイトルが強い場合でも、
    # 本文がメニューや報告だけなら落とす。
    title_based_spoofing = (
        source == "フィッシング対策協議会"
        and "フィッシング" in combined
        and "spoofing" in topics
        and has_attack_action(text)
    )

    # フェイクニュース系
    fake_news_good = (
        ("fake_claim" in topics and ("image" in topics or "statistics" in topics or "source_missing" in topics or "emotion" in topics or "exaggeration" in topics))
        or ("image" in topics and ("fake_claim" in topics or "source_missing" in topics))
        or ("statistics" in topics and ("fake_claim" in topics or "source_missing" in topics))
        or ("source_missing" in topics and "fake_claim" in topics)
    )

    if page_type == "phishing":
        if subject_good:
            return True

        return (phishing_good or title_based_spoofing) and has_attack_action(text)

    if page_type == "fake_news":
        return fake_news_good and has_attack_action(text)

    return (
        ((phishing_good or title_based_spoofing) and has_attack_action(text))
        or (fake_news_good and has_attack_action(text))
        or subject_good
    )


# ============================================================
# 重複判定
# ============================================================

def normalize_for_duplicate(text):
    text = clean_inline_text(text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[、。！？「」『』（）()\[\]【】]", "", text)
    return text


def is_duplicate_like(text, used_texts):
    normalized = normalize_for_duplicate(text)

    for used in used_texts:
        if normalized in used or used in normalized:
            return True

        set_a = set(normalized)
        set_b = set(used)

        if not set_a or not set_b:
            continue

        overlap = len(set_a & set_b) / len(set_a | set_b)

        if overlap >= 0.82:
            return True

    return False


# ============================================================
# case作成
# ============================================================

def make_case(raw_page, local_id, segment_title, text, segment_method="normal"):
    text = preprocess_case_text(text)
    text = trim_to_limit(text)

    return {
        "id": local_id,
        "source_page_id": raw_page.get("id"),
        "source": raw_page.get("source", ""),
        "type": raw_page.get("type", ""),
        "title": segment_title,
        "url": raw_page.get("url", ""),
        "text": text,
        "text_length": len(text),
        "segment_method": segment_method,
        "topic_key": topic_group_key(text, raw_page)
    }


def append_case_if_important(
    cases,
    raw_page,
    case_id,
    segment_title,
    text,
    used_topic_keys,
    used_texts,
    segment_method="normal",
    allow_same_topic=False
):
    if len(cases) >= MAX_CASES_PER_PAGE:
        return case_id

    text = preprocess_case_text(text)
    text = trim_to_limit(text)

    if not is_high_quality_material(text, raw_page):
        return case_id

    topic_key = topic_group_key(text, raw_page)

    if topic_key == "unknown":
        return case_id

    if not allow_same_topic and topic_key in used_topic_keys:
        return case_id

    if is_duplicate_like(text, used_texts):
        return case_id

    cases.append(
        make_case(
            raw_page=raw_page,
            local_id=case_id,
            segment_title=segment_title,
            text=text,
            segment_method=segment_method
        )
    )

    used_topic_keys.add(topic_key)
    used_texts.append(normalize_for_duplicate(text))

    return case_id + 1


# ============================================================
# 高シグナル抽出
# 専用パターンで0件だった時だけ使う
# ============================================================

def score_signal_text(text, raw_page):
    text = preprocess_case_text(text)

    topics = get_topic_keys(raw_page.get("title", "") + "。" + text)
    score = len(topics) * 10

    priority_words = [
        "フィッシングサイト",
        "偽サイト",
        "URL",
        "リンク",
        "ログイン",
        "パスワード",
        "認証コード",
        "確認コード",
        "クレジットカード",
        "カード番号",
        "ギフト券番号",
        "入力",
        "誘導",
        "タップ",
        "クリック",
        "支払い",
        "送金",
        "振込",
        "拡散",
        "AIで生成",
        "誤り",
        "事実と異なる"
    ]

    for word in priority_words:
        if word in text:
            score += 4

    if is_noise_text(text):
        score -= 50

    return score


def find_high_signal_windows(raw_page, max_cases=MAX_SIGNAL_CASES):
    text = clean_text(raw_page.get("text", ""))
    sentences = split_sentences(text)

    candidates = []

    for i, sentence in enumerate(sentences):
        sentence = preprocess_case_text(sentence)

        if len(sentence) < 30:
            continue

        if not is_high_quality_material(sentence, raw_page):
            continue

        chunk_sentences = []

        for j in [i - 1, i, i + 1]:
            if 0 <= j < len(sentences):
                s = preprocess_case_text(sentences[j])

                if not s:
                    continue

                if is_noise_text(s):
                    continue

                if len(s) > 260 and j != i:
                    continue

                chunk_sentences.append(s)

        chunk = clean_inline_text("".join(chunk_sentences))
        chunk = trim_to_limit(chunk)

        if not is_high_quality_material(chunk, raw_page):
            continue

        candidates.append({
            "score": score_signal_text(chunk, raw_page),
            "text": chunk,
            "topic_key": topic_group_key(chunk, raw_page)
        })

    candidates.sort(key=lambda item: item["score"], reverse=True)

    selected = []
    used_topic_keys = set()
    used_texts = []

    for item in candidates:
        if len(selected) >= max_cases:
            break

        if item["topic_key"] in used_topic_keys:
            continue

        if is_duplicate_like(item["text"], used_texts):
            continue

        selected.append(item["text"])
        used_topic_keys.add(item["topic_key"])
        used_texts.append(normalize_for_duplicate(item["text"]))

    return selected


# ============================================================
# IPA向け
# ============================================================

def segment_ipa_page(raw_page, start_id):
    text = clean_text(raw_page.get("text", ""))
    inline_text = clean_inline_text(text)

    cases = []
    case_id = start_id
    used_topic_keys = set()
    used_texts = []

    # 1. 明確な「事例1：」「事例2：」形式
    pattern = r"(事例\s*\d+[:：].*?)(?=事例レポート\d|事例\s*\d+[:：]|上記以外にも|関連情報|対策|$)"
    matches = re.findall(pattern, inline_text)

    for match in matches:
        segment_text = clean_inline_text(match)
        segment_text = re.sub(r"事例レポート\d.*", "", segment_text)
        segment_text = clean_inline_text(segment_text)

        title_match = re.match(r"(事例\s*\d+[:：][^。]{1,80})", segment_text)

        if title_match:
            segment_title = title_match.group(1)
        else:
            segment_title = raw_page.get("title", "IPA事例")

        # 明確な事例形式は同じtopicでも複数許可
        case_id = append_case_if_important(
            cases=cases,
            raw_page=raw_page,
            case_id=case_id,
            segment_title=segment_title,
            text=segment_text,
            used_topic_keys=used_topic_keys,
            used_texts=used_texts,
            segment_method="ipa_case_pattern",
            allow_same_topic=True
        )

    # 2. 相談事例・被害事例・手口などのまとまり
    section_patterns = [
        r"(相談事例.*?)(?=対策|相談窓口|関連情報|参考情報|$)",
        r"(相談内容.*?)(?=対策|相談窓口|関連情報|参考情報|$)",
        r"(被害事例.*?)(?=対策|相談窓口|関連情報|参考情報|$)",
        r"(手口.*?)(?=対策|相談窓口|関連情報|参考情報|$)"
    ]

    for pattern in section_patterns:
        for match in re.findall(pattern, inline_text):
            case_id = append_case_if_important(
                cases=cases,
                raw_page=raw_page,
                case_id=case_id,
                segment_title=raw_page.get("title", "IPA抽出事例"),
                text=match,
                used_topic_keys=used_topic_keys,
                used_texts=used_texts,
                segment_method="ipa_section"
            )

    # 3. 0件だった場合だけ、高シグナル抽出
    if len(cases) == 0:
        important_windows = find_high_signal_windows(raw_page, max_cases=MAX_SIGNAL_CASES)

        for window in important_windows:
            case_id = append_case_if_important(
                cases=cases,
                raw_page=raw_page,
                case_id=case_id,
                segment_title=raw_page.get("title", "IPA抽出事例"),
                text=window,
                used_topic_keys=used_topic_keys,
                used_texts=used_texts,
                segment_method="ipa_signal"
            )

    return cases, case_id


# ============================================================
# フィッシング対策協議会向け
# ============================================================

def extract_subject_examples(inline_text, title):
    """
    件名例だけを取り出して、問題化しやすい形にまとめる。
    """

    subject_area_match = re.search(
        r"((?:メールの件名|件名例|メール件名).*?)(?=メール本文|本文例|誘導先のURL|フィッシングサイトのURL|URL|対策|$)",
        inline_text
    )

    if subject_area_match:
        subject_area = subject_area_match.group(1)
    else:
        subject_area = inline_text

    subjects = []

    # 【重要】... 形式
    subjects.extend(
        re.findall(r"【[^】]{2,50}】[^【。]{0,90}", subject_area)
    )

    # 英文件名など
    english_subjects = re.findall(
        r"(?:You['’]ll lose access to your account|Your account will be suspended|Action required[^。]{0,80})",
        subject_area,
        flags=re.IGNORECASE
    )

    subjects.extend(english_subjects)

    clean_subjects = []

    for item in subjects:
        item = clean_inline_text(item)

        if is_noise_text(item):
            continue

        if len(item) < 5:
            continue

        if item not in clean_subjects:
            clean_subjects.append(item)

    if not clean_subjects:
        return ""

    subject_text = f"{title}。次のような件名のフィッシングメールが確認されています。" + " ".join(clean_subjects[:5])

    return trim_to_limit(subject_text, 380)


def extract_url_examples(inline_text, title):
    """
    誘導先URL例を問題化しやすい形にまとめる。
    """

    url_area_match = re.search(
        r"((?:誘導先のURL|フィッシングサイトのURL|URL例|リンク).*?)(?=メールの件名|メール本文|本文例|対策|$)",
        inline_text
    )

    if url_area_match:
        url_area = url_area_match.group(1)
    else:
        url_area = inline_text

    urls = re.findall(r"https?://[^\s　「」<>]+", url_area)

    clean_urls = []

    for url in urls:
        url = url.strip("。、,，")
        if url not in clean_urls:
            clean_urls.append(url)

    if not clean_urls:
        return ""

    url_text = f"{title}。フィッシングサイトへの誘導URLとして、次のようなURLが確認されています。" + " ".join(clean_urls[:4])

    return trim_to_limit(url_text, 400)


def segment_antiphishing_page(raw_page, start_id):
    text = clean_text(raw_page.get("text", ""))
    inline_text = clean_inline_text(text)

    cases = []
    case_id = start_id
    used_topic_keys = set()
    used_texts = []

    title = raw_page.get("title", "フィッシング注意喚起")

    # 1. 概要文
    summary_patterns = [
        r"(.{0,120}(?:かたる|騙る|よそおう|装う|名乗る).*?フィッシング.*?(?:確認されています|報告されています|報告を受けています)。)",
        r"(フィッシング.*?(?:メール|SMS|ショートメッセージ|サイト).*?(?:確認されています|報告されています|報告を受けています)。)"
    ]

    for pattern in summary_patterns:
        for match in re.findall(pattern, inline_text):
            case_id = append_case_if_important(
                cases=cases,
                raw_page=raw_page,
                case_id=case_id,
                segment_title=title,
                text=match,
                used_topic_keys=used_topic_keys,
                used_texts=used_texts,
                segment_method="antiphishing_summary"
            )

    # 2. 件名例
    subject_text = extract_subject_examples(inline_text, title)

    if subject_text:
        case_id = append_case_if_important(
            cases=cases,
            raw_page=raw_page,
            case_id=case_id,
            segment_title="フィッシングメールの件名例",
            text=subject_text,
            used_topic_keys=used_topic_keys,
            used_texts=used_texts,
            segment_method="antiphishing_subject"
        )

    # 3. URL例
    url_text = extract_url_examples(inline_text, title)

    if url_text:
        case_id = append_case_if_important(
            cases=cases,
            raw_page=raw_page,
            case_id=case_id,
            segment_title="フィッシングサイトへの誘導URL例",
            text=url_text,
            used_topic_keys=used_topic_keys,
            used_texts=used_texts,
            segment_method="antiphishing_url"
        )

    # 4. 0件だった場合だけ高シグナル抽出
    if len(cases) == 0:
        important_windows = find_high_signal_windows(raw_page, max_cases=MAX_SIGNAL_CASES)

        for window in important_windows:
            case_id = append_case_if_important(
                cases=cases,
                raw_page=raw_page,
                case_id=case_id,
                segment_title=title,
                text=window,
                used_topic_keys=used_topic_keys,
                used_texts=used_texts,
                segment_method="antiphishing_signal"
            )

    return cases, case_id


# ============================================================
# JFC向け
# ============================================================

def segment_jfc_page(raw_page, start_id):
    text = clean_text(raw_page.get("text", ""))
    inline_text = clean_inline_text(text)

    cases = []
    case_id = start_id
    used_topic_keys = set()
    used_texts = []

    sentences = split_sentences(inline_text)

    # 1. 冒頭要約
    intro = "".join(sentences[:3])

    case_id = append_case_if_important(
        cases=cases,
        raw_page=raw_page,
        case_id=case_id,
        segment_title=raw_page.get("title", "JFCファクトチェック概要"),
        text=intro,
        used_topic_keys=used_topic_keys,
        used_texts=used_texts,
        segment_method="jfc_intro"
    )

    # 2. 拡散投稿
    diffusion_patterns = [
        r"((?:20\d{2}年.*?)(?:X|SNS|Twitter).*?拡散.*?。)",
        r"((?:X|SNS|Twitter).*?拡散.*?(?:誤り|不正確|AI|画像|投稿|主張).*?。)",
        r"((?:投稿|画像).*?拡散.*?(?:誤り|不正確|AI|生成|偽画像).*?。)"
    ]

    for pattern in diffusion_patterns:
        for match in re.findall(pattern, inline_text):
            case_id = append_case_if_important(
                cases=cases,
                raw_page=raw_page,
                case_id=case_id,
                segment_title="SNSで拡散した投稿内容",
                text=match,
                used_topic_keys=used_topic_keys,
                used_texts=used_texts,
                segment_method="jfc_diffusion"
            )

    # 3. AI画像・画像ミスリード
    ai_image_patterns = [
        r"((?:画像|写真|動画).*?(?:AI|生成AI|ChatGPT|GPT|SynthID|偽画像).*?。)",
        r"((?:AI|生成AI|ChatGPT|GPT|SynthID).*?(?:画像|写真|動画|スクリーンショット).*?。)"
    ]

    for pattern in ai_image_patterns:
        for match in re.findall(pattern, inline_text):
            case_id = append_case_if_important(
                cases=cases,
                raw_page=raw_page,
                case_id=case_id,
                segment_title="生成AI・画像に関する誤情報",
                text=match,
                used_topic_keys=used_topic_keys,
                used_texts=used_texts,
                segment_method="jfc_ai_image"
            )

    # 4. 判定理由
    conclusion_patterns = [
        r"((?:よって|以上から).*?(?:誤り|不正確).*?判定.*?。)",
        r"((?:公式発表|報道|確認).*?(?:基づくものではない|否定|事実はない).*?。)"
    ]

    for pattern in conclusion_patterns:
        for match in re.findall(pattern, inline_text):
            case_id = append_case_if_important(
                cases=cases,
                raw_page=raw_page,
                case_id=case_id,
                segment_title="ファクトチェックの判定理由",
                text=match,
                used_topic_keys=used_topic_keys,
                used_texts=used_texts,
                segment_method="jfc_conclusion"
            )

    # 5. 0件だった場合だけ高シグナル抽出
    if len(cases) == 0:
        important_windows = find_high_signal_windows(raw_page, max_cases=2)

        for window in important_windows:
            case_id = append_case_if_important(
                cases=cases,
                raw_page=raw_page,
                case_id=case_id,
                segment_title=raw_page.get("title", "JFC抽出事例"),
                text=window,
                used_topic_keys=used_topic_keys,
                used_texts=used_texts,
                segment_method="jfc_signal"
            )

    return cases, case_id


# ============================================================
# 汎用
# ============================================================

def segment_generic_page(raw_page, start_id):
    cases = []
    case_id = start_id
    used_topic_keys = set()
    used_texts = []

    important_windows = find_high_signal_windows(raw_page, max_cases=MAX_SIGNAL_CASES)

    for window in important_windows:
        case_id = append_case_if_important(
            cases=cases,
            raw_page=raw_page,
            case_id=case_id,
            segment_title=raw_page.get("title", "抽出事例"),
            text=window,
            used_topic_keys=used_topic_keys,
            used_texts=used_texts,
            segment_method="generic_signal"
        )

    return cases, case_id


def segment_page(raw_page, start_id):
    source = raw_page.get("source", "")

    if source == "IPA":
        return segment_ipa_page(raw_page, start_id)

    if source == "フィッシング対策協議会":
        return segment_antiphishing_page(raw_page, start_id)

    if source == "JFC":
        return segment_jfc_page(raw_page, start_id)

    return segment_generic_page(raw_page, start_id)


def main():
    raw_pages_path = Path(RAW_PAGES_PATH)

    if not raw_pages_path.exists():
        print(f"{RAW_PAGES_PATH} が見つかりません。")
        print("先に py fetch_cases.py を実行してください。")
        return

    with open(RAW_PAGES_PATH, "r", encoding="utf-8") as f:
        raw_pages = json.load(f)

    all_cases = []
    next_id = 1

    for raw_page in raw_pages:
        print("=" * 70)
        print(f"分割中: {raw_page.get('title', '')}")
        print(f"source: {raw_page.get('source', '')}")
        print(f"元の文字数: {raw_page.get('text_length', len(raw_page.get('text', '')))}")

        cases, next_id = segment_page(raw_page, next_id)
        all_cases.extend(cases)

        print(f"作成された事例数: {len(cases)}")

        for case in cases:
            print("-" * 40)
            print(f"ID: {case['id']}")
            print(f"タイトル: {case['title']}")
            print(f"分割方法: {case.get('segment_method', '')}")
            print(f"トピック: {case.get('topic_key', '')}")
            print(f"文字数: {case['text_length']}")
            print(case["text"][:160] + "...")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_cases, f, ensure_ascii=False, indent=2)

    print("=" * 70)
    print(f"事例単位に分割したデータを出力しました: {OUTPUT_PATH}")
    print(f"合計事例数: {len(all_cases)}")
    print("次は py problem_generator.py を実行して、問題候補を生成します。")


if __name__ == "__main__":
    main()