import json
import copy
from pathlib import Path


GENERATED_PATH = Path("data/refined_candidates.json")
APPROVED_PATH = Path("data/approved_candidates.json")
REVIEW_PATH = Path("data/review_candidates.json")
DISCARDED_PATH = Path("data/discarded_candidates.json")
EXPLANATIONS_PATH = Path("data/explanations.json")


# -----------------------------
# 自動承認の基準
# -----------------------------
MIN_TEXT_LENGTH = 60
MAX_TEXT_LENGTH = 450
MIN_TOP_SCORE = 5
MAX_ANSWER_COUNT = 2
CHOICE_COUNT = 5

# API制限でAI整形できなかった候補でも、
# 形式・品質が十分なら自動承認を許可する。
# ただし validation_failed や skipped_no_answer は許可しない。
AUTO_APPROVE_QUOTA_ERROR_IF_CLEAN = True


# -----------------------------
# JSON処理
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
    path.parent.mkdir(exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def as_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def contains_any(text, words):
    text = str(text)
    return any(word in text for word in words)


def contains_any_lower(text, words):
    lower_text = str(text).lower()
    return any(str(word).lower() in lower_text for word in words)


def clean_text(text):
    text = str(text)
    return " ".join(text.replace("\u3000", " ").split())


def normalize_for_compare(text):
    text = clean_text(text)

    for char in [
        " ",
        "　",
        "、",
        "。",
        "・",
        "/",
        "「",
        "」",
        "『",
        "』",
        "（",
        "）",
        "(",
        ")",
        "：",
        ":",
        "，",
        ",",
        "！",
        "!",
        "？",
        "?"
    ]:
        text = text.replace(char, "")

    return text


def text_contains_evidence(text, evidence):
    if not evidence:
        return False

    text = clean_text(text)
    evidence = clean_text(evidence)

    if evidence in text:
        return True

    normalized_text = normalize_for_compare(text)
    normalized_evidence = normalize_for_compare(evidence)

    if normalized_evidence in normalized_text:
        return True

    # AI整形後に少しだけ表現が変わった場合に備えて、
    # evidenceが短すぎなければ部分一致も許可する。
    if len(normalized_evidence) >= 12:
        return normalized_evidence[:12] in normalized_text

    return False


# -----------------------------
# カテゴリ一覧
# -----------------------------
def load_allowed_categories():
    explanations = load_json(EXPLANATIONS_PATH, default=[])

    categories = []

    for item in explanations:
        category = item.get("category")

        if category and category not in categories:
            categories.append(category)

    return categories


def get_detected_map(candidate):
    detected_map = {}

    for item in candidate.get("detected_categories", []):
        category = item.get("category")

        if category:
            detected_map[category] = item

    return detected_map


def get_detail_map(candidate):
    detail_map = {}

    for detail in candidate.get("answer_details", []):
        category = detail.get("category")

        if category:
            detail_map[category] = detail

    return detail_map


# -----------------------------
# 破棄・レビュー判定用の語彙
# -----------------------------
NON_QUIZ_TEXT_WORDS = [
    "図9",
    "図10",
    "図11",
    "図12",
    "赤色破線",
    "赤い破線",
    "不正送金の有無",
    "パスワードの変更",
    "必要な対処",
    "銀行に相談",
    "警察に相談",
    "IPAに相談",
    "検証します",
    "解説します",
    "見抜くポイント",
    "十分にご注意ください",
    "引き続きご注意ください"
]


# reviewではなく破棄してよいノイズ
DISCARD_TEXT_WORDS = [
    # FAQ・被害後対応
    "よくある質問",
    "よくあるご質問",
    "なにか被害があるか",
    "被害にはつながりません",
    "影響はありません",
    "操作なしに",
    "何の操作も入力もせず",
    "インストールしていなければ",
    "初期化等を実施してください",
    "買い替えの必要はありません",
    "対処にはなりません",

    # 対策・報告案内
    "ご報告ください",
    "報告方法",
    "入力した内容に応じた対処方法",
    "公式アプリやブラウザーのブックマーク",
    "アクセスしなおすよう心がけてください",
    "推奨します",
    "検討してください",

    # メニュー・ナビ・サイト説明
    "HOME >",
    "ホーム >",
    "組織概要",
    "会長挨拶",
    "運営委員紹介",
    "入会案内",
    "パンフレット",
    "STOP. THINK. CONNECT",
    "報告書類",
    "ガイドライン",
    "月次報告書",
    "協議会WG報告書",
    "マンガでわかる",
    "フィッシングとは",
    "今すぐできるフィッシング対策",
    "なりすまし送信メール対策",
    "フィッシングの報告",

    # 記事一覧・別イベント
    "メール・SMSの文面例",
    "フィッシングサイトの例",
    "ニュース記事集",
    "協議会からのお知らせ",
    "【報告方法】はこちら",
    "【会員限定】",
    "東京開催"
]


POST_INCIDENT_ADVICE_WORDS = [
    "不正送金の有無",
    "パスワードの変更",
    "必要な対処",
    "銀行に相談",
    "警察に相談",
    "IPAに相談",
    "相談する",
    "確認する",
    "初期化",
    "買い替え",
    "対処"
]


URGENCY_ATTACK_WORDS = [
    "24時間以内",
    "48時間以内",
    "本日中",
    "至急",
    "今すぐ",
    "最終確認",
    "最終通知",
    "差押",
    "執行予告",
    "緊急納付",
    "永久停止",
    "アカウントが停止",
    "期限内",
    "未回答の場合",
    "罰則",
    "lose access",
    "suspended",
    "action required"
]


VISUAL_MISLEAD_WORDS = [
    "AIによって生成",
    "AIで作られた",
    "AI生成",
    "生成AI",
    "偽画像",
    "偽の画像",
    "実際にはAI",
    "別の時期",
    "別の場所",
    "過去の画像",
    "過去の写真",
    "加工された",
    "切り抜き",
    "SynthID"
]


# -----------------------------
# 明らかに破棄する判定
# -----------------------------
def is_article_list_like(text):
    """
    複数の日付つき記事タイトルが並んでいるだけのものを除外する。
    """

    text = clean_text(text)

    count = 0

    # 例: 2026年05月18日 国民年金の納付依頼をよそおうフィッシング
    count += len(
        __import__("re").findall(
            r"20\d{2}年\d{1,2}月\d{1,2}日[^。]{0,90}フィッシング",
            text
        )
    )

    return count >= 2


def should_discard_candidate(candidate):
    """
    reviewに回すまでもなく、問題として使わない候補を破棄する。
    """

    text = candidate.get("text", "")
    answer = as_list(candidate.get("answer", []))
    detected_categories = as_list(candidate.get("detected_categories", []))
    validation_status = candidate.get("validation_status", "")
    ai_status = candidate.get("ai_refine_status", "")

    if not answer:
        return True, "正解カテゴリが空のため破棄します。"

    if ai_status == "skipped_no_answer":
        return True, "正解カテゴリがない候補のため破棄します。"

    if validation_status != "valid" and not detected_categories:
        return True, "検出カテゴリがなく、validでもないため破棄します。"

    if contains_any(text, DISCARD_TEXT_WORDS):
        return True, "FAQ・対策文・メニュー・記事一覧などのノイズが含まれるため破棄します。"

    if is_article_list_like(text):
        return True, "記事一覧のような文面のため破棄します。"

    if len(clean_text(text)) < MIN_TEXT_LENGTH:
        return True, "問題文が短すぎるため破棄します。"

    return False, ""


# -----------------------------
# AI整形結果の扱い
# -----------------------------
def is_quota_error(candidate):
    warnings = " ".join(
        str(w)
        for w in as_list(candidate.get("ai_refine_warnings", []))
    )

    quota_words = [
        "RESOURCE_EXHAUSTED",
        "quota",
        "Quota",
        "rate-limits",
        "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
    ]

    return contains_any(warnings, quota_words)


def should_force_review_by_ai_status(candidate):
    """
    AI整形の状態だけでreviewに回すべきかを判定する。
    API制限は候補品質と別問題なので、条件付きで通す。
    """

    reasons = []

    ai_status = candidate.get("ai_refine_status")
    ai_refined = candidate.get("ai_refined")

    if ai_status == "refined" and ai_refined is True:
        return reasons

    if ai_status == "validation_failed":
        reasons.append("AI整形後の検証に失敗したため確認が必要です。")
        return reasons

    if ai_status == "skipped_no_answer":
        reasons.append("正解カテゴリがないため確認が必要です。")
        return reasons

    if is_quota_error(candidate):
        if AUTO_APPROVE_QUOTA_ERROR_IF_CLEAN:
            return reasons

        reasons.append("AI整形がAPI制限で失敗したため確認が必要です。")
        return reasons

    if ai_status != "refined":
        reasons.append("AI整形が成功していないため確認が必要です。")

    if ai_refined is not True:
        reasons.append("ai_refined が True ではありません。")

    return reasons


# -----------------------------
# 文脈判定
# -----------------------------
def has_strong_url_spoof_context(text):
    url_words = [
        "http://",
        "https://",
        "URL",
        "リンク",
        "下記URL",
        "記載されたURL",
        "URLからアクセス",
        "URLをタップ",
        "URLへのリンク",
        "フィッシングサイト",
        "偽サイト",
        "ログインページ"
    ]

    action_words = [
        "タップ",
        "クリック",
        "アクセス",
        "誘導",
        "開く",
        "ログイン",
        "確認するよう",
        "指定してください",
        "入力",
        "求められ"
    ]

    return contains_any(text, url_words) and contains_any(text, action_words)


def has_spoof_context(text):
    words = [
        "なりすまし",
        "なりすました",
        "よそおう",
        "装う",
        "かたる",
        "偽のメール",
        "偽SMS",
        "偽のSMS",
        "名乗る",
        "佐川急便",
        "日本郵便",
        "ヤマト運輸",
        "au",
        "ドコモ",
        "OpenAI",
        "ChatGPT",
        "日本年金",
        "日本年金機構",
        "社長になりすまし",
        "担当者になりすまし"
    ]

    return contains_any(text, words)


def has_credential_context(text):
    words = [
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
        "PINコード",
        "入力"
    ]

    return contains_any(text, words)


def has_money_context(text):
    words = [
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

    return contains_any(text, words)


def has_fake_news_context(text):
    words = [
        "拡散",
        "投稿",
        "Xで",
        "SNS",
        "誤り",
        "不正確",
        "事実ではない",
        "事実と異なる",
        "AIで生成",
        "AIによって生成",
        "偽情報",
        "誤情報",
        "デマ"
    ]

    return contains_any(text, words)


def has_exaggeration_context(text):
    words = [
        "絶対",
        "必ず",
        "誰でも",
        "100%",
        "世界一",
        "史上最悪",
        "完全に",
        "一瞬で",
        "全員",
        "根こそぎ",
        "過激"
    ]

    return contains_any(text, words)


# -----------------------------
# evidence品質
# -----------------------------
def check_answer_details_quality(candidate):
    reasons = []

    text = candidate.get("text", "")
    answer = as_list(candidate.get("answer", []))
    answer_details = as_list(candidate.get("answer_details", []))

    for detail in answer_details:
        if not isinstance(detail, dict):
            reasons.append("answer_details の形式が正しくありません。")
            continue

        category = detail.get("category", "")
        evidence = detail.get("evidence", "")

        if not evidence:
            reasons.append(f"evidence が空です: {category}")
            continue

        if len(evidence) > 110:
            reasons.append(f"evidenceが長すぎます: {category}")

        if evidence and not text_contains_evidence(text, evidence):
            reasons.append(f"evidenceが問題文に含まれていません: {category}")

        if contains_any(evidence, NON_QUIZ_TEXT_WORDS):
            reasons.append(f"evidenceに図説明・被害後の対処説明が含まれています: {category}")

    # 緊急性誘導は攻撃文の中の焦らせる表現が必要
    if "緊急性誘導" in answer:
        joined_evidence = " ".join(
            detail.get("evidence", "")
            for detail in answer_details
            if isinstance(detail, dict)
        )

        if contains_any(joined_evidence, POST_INCIDENT_ADVICE_WORDS):
            reasons.append("緊急性誘導の根拠が攻撃文ではなく、被害後の対処説明になっています。")

        if not contains_any_lower(text, URGENCY_ATTACK_WORDS):
            reasons.append("緊急性誘導の根拠になる期限・停止・差押などの表現が弱いです。")

    # 画像のミスリードは画像があるだけでは弱い
    if "画像のミスリード" in answer:
        if not contains_any(text, VISUAL_MISLEAD_WORDS):
            reasons.append("画像のミスリードとしては、AI生成・偽画像・別文脈などの根拠が弱いです。")

    return reasons


# -----------------------------
# カテゴリ優先度補正
# -----------------------------
def extract_emotional_evidence(text):
    candidates = [
        "ぜったいにまずい",
        "許せない",
        "恐怖",
        "危険",
        "不安",
        "怒り",
        "怖い",
        "助けて",
        "拡散希望"
    ]

    for word in candidates:
        if word in text:
            start = max(0, text.find(word) - 20)
            end = min(len(text), text.find(word) + len(word) + 40)
            return text[start:end]

    return "感情を強く刺激する表現が含まれています。"


def fix_category_priority(candidate):
    """
    誇張表現と感情的表現が両方検出されている場合、
    文脈によっては感情的表現を優先する。
    ID固定ではなく内容ベースで修正する。
    """

    fixed = copy.deepcopy(candidate)

    answer = as_list(fixed.get("answer", []))
    related = as_list(fixed.get("related_categories", []))
    text = fixed.get("text", "")

    detected_map = get_detected_map(fixed)
    detail_map = get_detail_map(fixed)

    emotional_words = [
        "ぜったいにまずい",
        "許せない",
        "恐怖",
        "危険です",
        "大変です",
        "助けて",
        "拡散希望",
        "不安",
        "怒り",
        "怖い"
    ]

    has_emotional_context = contains_any(text, emotional_words)

    if (
        "誇張表現" in answer
        and "感情的表現" in detected_map
        and has_emotional_context
    ):
        answer = [
            "感情的表現" if item == "誇張表現" else item
            for item in answer
        ]

        answer = list(dict.fromkeys(answer))

        if "誇張表現" not in related:
            related.append("誇張表現")

        fixed["answer"] = answer
        fixed["category"] = answer
        fixed["related_categories"] = related

        new_details = []

        for ans in answer:
            if ans in detail_map:
                new_details.append(detail_map[ans])

            elif ans == "感情的表現":
                new_details.append({
                    "category": "感情的表現",
                    "evidence": extract_emotional_evidence(text),
                    "reason": "不安や怒りなどの感情を強く刺激し、冷静な事実確認をしにくくしているため。"
                })

        fixed["answer_details"] = new_details

    return fixed


# -----------------------------
# 形式チェック
# -----------------------------
def check_basic_format(candidate, allowed_categories):
    reasons = []

    text = candidate.get("text", "")
    choices = as_list(candidate.get("choices", []))
    answer = as_list(candidate.get("answer", []))
    category = as_list(candidate.get("category", []))
    answer_details = as_list(candidate.get("answer_details", []))

    if len(text) < MIN_TEXT_LENGTH:
        reasons.append("問題文が短すぎます。")

    if len(text) > MAX_TEXT_LENGTH:
        reasons.append("問題文が長すぎます。")

    if len(answer) == 0:
        reasons.append("正解カテゴリがありません。")

    if len(answer) > MAX_ANSWER_COUNT:
        reasons.append("正解カテゴリが多すぎます。")

    if len(choices) != CHOICE_COUNT:
        reasons.append("選択肢が5個ではありません。")

    if set(answer) - set(choices):
        reasons.append("正解カテゴリが選択肢に含まれていません。")

    if len(answer) == len(choices) and len(answer) > 0:
        reasons.append("選択肢がすべて正解になっています。")

    if answer != category:
        reasons.append("answer と category が一致していません。")

    for ans in answer:
        if ans not in allowed_categories:
            reasons.append(f"explanations.json に存在しないカテゴリです: {ans}")

    detail_categories = [
        detail.get("category")
        for detail in answer_details
        if isinstance(detail, dict)
    ]

    for ans in answer:
        if ans not in detail_categories:
            reasons.append(f"answer_details に説明がないカテゴリです: {ans}")

    for detail in answer_details:
        if not isinstance(detail, dict):
            reasons.append("answer_details の形式が正しくありません。")
            continue

        if not detail.get("category"):
            reasons.append("answer_details の category が空です。")

        if not detail.get("evidence"):
            reasons.append(f"evidence が空です: {detail.get('category', '')}")

        if not detail.get("reason"):
            reasons.append(f"reason が空です: {detail.get('category', '')}")

    return reasons


# -----------------------------
# 品質チェック
# -----------------------------
def check_quality(candidate):
    reasons = []

    text = candidate.get("text", "")
    answer = as_list(candidate.get("answer", []))
    detected_map = get_detected_map(candidate)

    if candidate.get("validation_status") != "valid":
        reasons.append("problem_generator.py 側で valid ではありません。")

    # スコアが低くても、AI整形後の本文に強い文脈があれば許可する
    top_scores = []

    for ans in answer:
        detected = detected_map.get(ans, {})
        score = detected.get("score", 0)
        top_scores.append(score)

    if top_scores and max(top_scores) < MIN_TOP_SCORE:
        has_context = False

        for ans in answer:
            if ans == "URL偽装" and has_strong_url_spoof_context(text):
                has_context = True
            elif ans == "なりすまし" and has_spoof_context(text):
                has_context = True
            elif ans == "個人情報要求" and has_credential_context(text):
                has_context = True
            elif ans == "金銭・送金要求" and has_money_context(text):
                has_context = True
            elif ans == "フェイクニュース" and has_fake_news_context(text):
                has_context = True
            elif ans == "誇張表現" and has_exaggeration_context(text):
                has_context = True

        if not has_context:
            reasons.append("検出スコアが低く、根拠が弱い可能性があります。")

    if "URL偽装" in answer:
        if not has_strong_url_spoof_context(text):
            reasons.append("URL偽装の根拠になるURL誘導表現が弱いです。")

        detected = detected_map.get("URL偽装", {})
        score = detected.get("score", 0)

        # scoreだけでは落とさない。
        # 本文に強いURL誘導文脈があれば承認可能。
        if score < 6 and not has_strong_url_spoof_context(text):
            reasons.append("URL偽装の検出スコアが低いです。")

    if "なりすまし" in answer:
        if not has_spoof_context(text):
            reasons.append("なりすましの根拠になる表現が弱いです。")

    if "個人情報要求" in answer:
        if not has_credential_context(text):
            reasons.append("個人情報要求の根拠になる入力情報が弱いです。")

    if "金銭・送金要求" in answer:
        if not has_money_context(text):
            reasons.append("金銭・送金要求の根拠になる支払い・送金表現が弱いです。")

    if "フェイクニュース" in answer:
        if not has_fake_news_context(text):
            reasons.append("フェイクニュースとしての拡散・誤情報の文脈が弱いです。")

    if "誇張表現" in answer:
        if not has_exaggeration_context(text):
            reasons.append("誇張表現の根拠になる強い表現が弱いです。")

    # 注意喚起だけの短文は弱い
    advice_only_words = [
        "十分にご注意ください",
        "引き続きご注意ください",
        "確認されています"
    ]

    if len(text) < 80 and contains_any(text, advice_only_words):
        reasons.append("注意喚起文のみで、問題文としては弱い可能性があります。")

    return reasons


# -----------------------------
# 出力用整形
# -----------------------------
def simplify_candidate_for_approved(candidate):
    keep_fields = [
        "id",
        "type",
        "question",
        "text",
        "choices",
        "answer",
        "category",
        "related_categories",
        "difficulty",
        "answer_details",
        "source",
        "title",
        "url",
        "source_page_id",
        "auto_generated",
        "review_required",
        "validation_status",
        "validation_errors",
        "ai_refined",
        "ai_refine_status",
        "ai_refine_model",
        "ai_refine_warnings"
    ]

    simplified = {}

    for field in keep_fields:
        if field in candidate:
            simplified[field] = candidate[field]

    simplified["auto_approval_status"] = "approved"
    simplified["auto_approval_reasons"] = []

    return simplified


def mark_for_review(candidate, reasons):
    reviewed = copy.deepcopy(candidate)
    reviewed["auto_approval_status"] = "needs_review"
    reviewed["auto_approval_reasons"] = reasons

    return reviewed


def mark_for_discard(candidate, reason):
    discarded = copy.deepcopy(candidate)
    discarded["auto_approval_status"] = "discarded"
    discarded["discard_reason"] = reason

    return discarded


# -----------------------------
# メイン処理
# -----------------------------
def main():
    candidates = load_json(GENERATED_PATH, default=[])
    allowed_categories = load_allowed_categories()

    if not candidates:
        print(f"{GENERATED_PATH} に候補がありません。")
        return

    if not allowed_categories:
        print(f"{EXPLANATIONS_PATH} からカテゴリを読み込めませんでした。")
        return

    approved = []
    review = []
    discarded = []

    for candidate in candidates:
        fixed_candidate = fix_category_priority(candidate)

        discard, discard_reason = should_discard_candidate(fixed_candidate)

        if discard:
            discarded.append(mark_for_discard(fixed_candidate, discard_reason))
            continue

        reasons = []

        reasons.extend(should_force_review_by_ai_status(fixed_candidate))
        reasons.extend(check_basic_format(fixed_candidate, allowed_categories))
        reasons.extend(check_answer_details_quality(fixed_candidate))
        reasons.extend(check_quality(fixed_candidate))

        reasons = list(dict.fromkeys(reasons))

        if reasons:
            review.append(mark_for_review(fixed_candidate, reasons))
        else:
            approved.append(simplify_candidate_for_approved(fixed_candidate))

    save_json(APPROVED_PATH, approved)
    save_json(REVIEW_PATH, review)
    save_json(DISCARDED_PATH, discarded)

    print("=" * 60)
    print("自動承認処理が完了しました。")
    print(f"承認済み: {len(approved)} 件 → {APPROVED_PATH}")
    print(f"要確認: {len(review)} 件 → {REVIEW_PATH}")
    print(f"破棄: {len(discarded)} 件 → {DISCARDED_PATH}")

    if review:
        print("-" * 60)
        print("要確認になった候補:")

        for item in review:
            print(f"ID {item.get('id')}: {item.get('title', '')}")
            for reason in item.get("auto_approval_reasons", []):
                print(f"  - {reason}")

    if discarded:
        print("-" * 60)
        print("破棄された候補:")

        for item in discarded:
            print(f"ID {item.get('id')}: {item.get('title', '')}")
            print(f"  - {item.get('discard_reason', '')}")


if __name__ == "__main__":
    main()