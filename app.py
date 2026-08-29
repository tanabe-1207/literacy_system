import json
import html
import sqlite3
from pathlib import Path
from datetime import datetime
import random

import streamlit as st

try:
    from google import genai
except ImportError:
    genai = None

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# -----------------------------
# ページ設定
# -----------------------------
st.set_page_config(
    page_title="情報リテラシー学習支援システム",
    page_icon="📘",
    layout="wide"
)


# -----------------------------
# 見た目調整
# -----------------------------
st.markdown("""
<style>
.block-container {
    padding-top: 1.0rem;
    padding-bottom: 1.5rem;
    max-width: 1200px;
}

/* タイトル */
.main-title {
    font-size: 25px;
    font-weight: 800;
    margin-bottom: 0.15rem;
    white-space: normal;
    line-height: 1.35;
}
.sub-title {
    color: #555;
    font-size: 15px;
    margin-bottom: 0.8rem;
}

/* サイドバーをコンパクトに */
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    margin-top: 0.4rem;
    margin-bottom: 0.4rem;
}
section[data-testid="stSidebar"] [data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 8px 10px;
}
section[data-testid="stSidebar"] .stProgress {
    margin-top: -8px;
    margin-bottom: 6px;
}
.sidebar-small {
    font-size: 13px;
    color: #4b5563;
    line-height: 1.4;
}

/* 小さな説明 */
.small-note {
    font-size: 13px;
    color: #666;
}

/* 弱点推定カード */
.weak-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 10px 11px;
    margin-bottom: 9px;
}
.weak-title {
    font-size: 14px;
    font-weight: 800;
    color: #111827;
    margin-bottom: 3px;
}
.weak-label-red {
    display: inline-block;
    background: #fee2e2;
    color: #991b1b;
    border-radius: 999px;
    padding: 2px 8px;
    font-size: 12px;
    font-weight: 800;
    margin-right: 5px;
}
.weak-label-yellow {
    display: inline-block;
    background: #fef3c7;
    color: #92400e;
    border-radius: 999px;
    padding: 2px 8px;
    font-size: 12px;
    font-weight: 800;
    margin-right: 5px;
}
.weak-meta {
    font-size: 12px;
    color: #64748b;
    line-height: 1.5;
}
.sidebar-jump-button {
    display: block;
    text-align: center;
    text-decoration: none;
    background: #2563eb;
    color: white !important;
    border-radius: 10px;
    padding: 9px 10px;
    font-weight: 800;
    margin: 8px 0 10px 0;
}
.sidebar-jump-button:hover {
    background: #1d4ed8;
    color: white !important;
}

/* 判定表示 */
.result-tag {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 999px;
    font-size: 13px;
    font-weight: 700;
    margin: 3px 4px 3px 0;
    background: #f3f4f6;
    border: 1px solid #e5e7eb;
}
.detail-card {
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 13px 15px;
    margin-bottom: 10px;
    background: #ffffff;
}
.detail-title {
    font-size: 17px;
    font-weight: 800;
    margin-bottom: 8px;
}
.detail-label {
    font-size: 13px;
    color: #64748b;
    font-weight: 700;
    margin-top: 8px;
}
.detail-text {
    font-size: 14px;
    color: #111827;
    line-height: 1.6;
}

/* AIチャット */
.chat-empty {
    color: #64748b;
    background: #ffffff;
    border: 1px dashed #93c5fd;
    padding: 12px;
    border-radius: 12px;
    font-size: 14px;
}
.bubble-row-user {
    display: flex;
    justify-content: flex-end;
    margin: 8px 0;
}
.bubble-row-ai {
    display: flex;
    justify-content: flex-start;
    margin: 8px 0;
}
.bubble-user {
    max-width: 78%;
    background: #2563eb;
    color: white;
    padding: 10px 13px;
    border-radius: 16px 16px 4px 16px;
    line-height: 1.6;
    font-size: 14px;
}
.bubble-ai {
    max-width: 78%;
    background: white;
    color: #111827;
    padding: 10px 13px;
    border-radius: 16px 16px 16px 4px;
    line-height: 1.6;
    font-size: 14px;
    border: 1px solid #e5e7eb;
}
.input-guide {
    background: #eff6ff;
    border: 1px solid #93c5fd;
    color: #1e40af;
    border-radius: 12px;
    padding: 9px 11px;
    font-size: 13px;
    font-weight: 700;
    margin-bottom: 8px;
}
</style>
""", unsafe_allow_html=True)


# -----------------------------
# ランダム出題・問題バー管理
# -----------------------------

def init_random_quiz_order(problems):
    """
    問題の出題順をランダムに決める。
    SQLiteに保存した状態があれば、リロード後も同じ位置から再開する。
    """

    if len(problems) == 0:
        st.session_state.quiz_order = []
        st.session_state.current_quiz_pos = 0
        st.session_state.current_index = 0
        return

    need_reset = (
        "quiz_order" not in st.session_state
        or len(st.session_state.quiz_order) != len(problems)
        or set(st.session_state.quiz_order) != set(range(len(problems)))
    )

    if need_reset:
        saved_state = load_quiz_state(problems)

        if saved_state is not None:
            st.session_state.quiz_order = saved_state["quiz_order"]
            st.session_state.current_quiz_pos = saved_state["current_quiz_pos"]
            st.session_state.current_index = st.session_state.quiz_order[st.session_state.current_quiz_pos]
        else:
            st.session_state.quiz_order = list(range(len(problems)))
            random.shuffle(st.session_state.quiz_order)
            st.session_state.current_quiz_pos = 0
            st.session_state.current_index = st.session_state.quiz_order[0]
            save_quiz_state()

    if "current_quiz_pos" not in st.session_state:
        st.session_state.current_quiz_pos = 0

    if "current_index" not in st.session_state:
        st.session_state.current_index = st.session_state.quiz_order[st.session_state.current_quiz_pos]


def set_current_problem_index(index):
    """
    current_indexを変更するときに、ランダム出題順の位置も合わせる。
    類似問題や弱点克服問題から移動した後でも問題バーがズレないようにする。
    """

    if len(problems) == 0:
        return

    index = max(0, min(index, len(problems) - 1))
    st.session_state.current_index = index

    if "quiz_order" in st.session_state and index in st.session_state.quiz_order:
        st.session_state.current_quiz_pos = st.session_state.quiz_order.index(index)

    save_quiz_state()


def reset_random_quiz_order(problems):
    """
    問題順をシャッフルし直して、最初の問題に戻す。
    """

    if len(problems) == 0:
        st.session_state.quiz_order = []
        st.session_state.current_quiz_pos = 0
        st.session_state.current_index = 0
        save_quiz_state()
        return

    st.session_state.quiz_order = list(range(len(problems)))
    random.shuffle(st.session_state.quiz_order)
    st.session_state.current_quiz_pos = 0
    st.session_state.current_index = st.session_state.quiz_order[0]
    save_quiz_state()


# -----------------------------
# データ読み込み
# -----------------------------
@st.cache_data
def load_problems():
    with open("data/problems.json", "r", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_explanations():
    with open("data/explanations.json", "r", encoding="utf-8") as f:
        explanation_list = json.load(f)

    explanations = {}
    for item in explanation_list:
        explanations[item["category"]] = item["explanation"]

    return explanations

# -----------------------------
# SQLite：回答履歴DB
# -----------------------------
DB_PATH = "data/literacy.db"


def init_db():
    """回答履歴を保存するSQLiteデータベースを作成する。"""
    Path("data").mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS answer_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_id INTEGER NOT NULL,
            category_json TEXT NOT NULL,
            answer_json TEXT NOT NULL,
            selected_json TEXT NOT NULL,
            correct INTEGER NOT NULL,
            judge_label TEXT NOT NULL,
            score_rate REAL NOT NULL,
            answered_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def save_answer_history(record):
    """1回分の回答履歴をSQLiteに保存する。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO answer_history (
            problem_id,
            category_json,
            answer_json,
            selected_json,
            correct,
            judge_label,
            score_rate,
            answered_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record["problem_id"],
        json.dumps(record["category"], ensure_ascii=False),
        json.dumps(record["answer"], ensure_ascii=False),
        json.dumps(record["selected"], ensure_ascii=False),
        1 if record["correct"] else 0,
        record["judge_label"],
        record["score_rate"],
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


def load_answer_history():
    """SQLiteから回答履歴を読み込む。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            problem_id,
            category_json,
            answer_json,
            selected_json,
            correct,
            judge_label,
            score_rate
        FROM answer_history
        ORDER BY id
    """)

    rows = cursor.fetchall()
    conn.close()

    history = []

    for row in rows:
        history.append({
            "problem_id": row[0],
            "category": json.loads(row[1]),
            "answer": json.loads(row[2]),
            "selected": json.loads(row[3]),
            "correct": bool(row[4]),
            "judge_label": row[5],
            "score_rate": row[6]
        })

    return history


def clear_answer_history_db():
    """SQLiteに保存されている回答履歴を削除する。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM answer_history")

    conn.commit()
    conn.close()


def save_app_state(key, value):
    """アプリの状態をSQLiteに保存する。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO app_state (
            key,
            value,
            updated_at
        )
        VALUES (?, ?, ?)
    """, (
        key,
        json.dumps(value, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


def load_app_state(key, default=None):
    """SQLiteからアプリの状態を読み込む。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT value
        FROM app_state
        WHERE key = ?
    """, (key,))

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return default

    try:
        return json.loads(row[0])
    except Exception:
        return default


def save_quiz_state():
    """現在のランダム出題順と問題バーの位置を保存する。"""
    if "quiz_order" not in st.session_state:
        return

    if "current_quiz_pos" not in st.session_state:
        return

    if "current_index" not in st.session_state:
        return

    save_app_state("quiz_state", {
        "quiz_order": st.session_state.quiz_order,
        "current_quiz_pos": st.session_state.current_quiz_pos,
        "current_index": st.session_state.current_index
    })


def load_quiz_state(problems):
    """保存済みの出題状態を読み込む。問題数が変わっていたら使わない。"""
    state = load_app_state("quiz_state", default=None)

    if state is None:
        return None

    quiz_order = state.get("quiz_order")
    current_quiz_pos = state.get("current_quiz_pos")

    if not isinstance(quiz_order, list):
        return None

    if len(quiz_order) != len(problems):
        return None

    if set(quiz_order) != set(range(len(problems))):
        return None

    if not isinstance(current_quiz_pos, int):
        return None

    if current_quiz_pos < 0 or current_quiz_pos >= len(problems):
        return None

    return state


problems = load_problems()
explanations = load_explanations()
init_db()

# -----------------------------
# セッション状態
# -----------------------------
if "current_index" not in st.session_state:
    st.session_state.current_index = 0

if "history" not in st.session_state:
    st.session_state.history = load_answer_history()

if "answered" not in st.session_state:
    st.session_state.answered = False

if "last_result" not in st.session_state:
    st.session_state.last_result = None

if "practice_mode" not in st.session_state:
    st.session_state.practice_mode = False

if "practice_queue" not in st.session_state:
    st.session_state.practice_queue = []

if "practice_position" not in st.session_state:
    st.session_state.practice_position = 0

if "practice_return_index" not in st.session_state:
    st.session_state.practice_return_index = None

if "practice_return_result" not in st.session_state:
    st.session_state.practice_return_result = None

if "practice_complete_message" not in st.session_state:
    st.session_state.practice_complete_message = ""

# ランダム出題順を初期化する
init_random_quiz_order(problems)

# 通常モードのときだけ、ランダム順の現在位置から問題番号を決める
if not st.session_state.practice_mode:
    st.session_state.current_index = st.session_state.quiz_order[st.session_state.current_quiz_pos]


# -----------------------------
# 基本関数
# -----------------------------
def finish_practice_and_return():
    """弱点克服モードを終了し、開始前にいた問題へ戻る。"""
    return_index = st.session_state.practice_return_index
    return_result = st.session_state.practice_return_result

    st.session_state.practice_mode = False
    st.session_state.practice_queue = []
    st.session_state.practice_position = 0
    st.session_state.practice_return_index = None
    st.session_state.practice_return_result = None

    if return_index is not None:
        set_current_problem_index(return_index)
    else:
        set_current_problem_index(st.session_state.quiz_order[0])

    if return_result is not None:
        st.session_state.answered = True
        st.session_state.last_result = return_result
    else:
        st.session_state.answered = False
        st.session_state.last_result = None

    st.session_state.practice_complete_message = "弱点克服問題をすべて解き終わりました。元の問題に戻りました。"


def next_problem():
    """通常時はランダム順の次の問題へ、弱点克服モード中はキューの次の問題へ進む。"""

    if st.session_state.practice_mode:
        next_position = st.session_state.practice_position + 1

        if next_position < len(st.session_state.practice_queue):
            st.session_state.practice_position = next_position
            st.session_state.current_index = st.session_state.practice_queue[next_position]
            st.session_state.answered = False
            st.session_state.last_result = None
        else:
            finish_practice_and_return()

    else:
        st.session_state.current_quiz_pos += 1

        # 全問出し終わったら、もう一度シャッフルして最初に戻る
        if st.session_state.current_quiz_pos >= len(st.session_state.quiz_order):
            random.shuffle(st.session_state.quiz_order)
            st.session_state.current_quiz_pos = 0

        st.session_state.current_index = st.session_state.quiz_order[st.session_state.current_quiz_pos]
        st.session_state.answered = False
        st.session_state.last_result = None

        save_quiz_state()


def move_to_problem(index):
    """単体の推薦問題を解くときは、弱点克服モードを解除して移動する。"""
    st.session_state.practice_mode = False
    st.session_state.practice_queue = []
    st.session_state.practice_position = 0
    st.session_state.practice_return_index = None
    st.session_state.practice_return_result = None

    set_current_problem_index(index)
    st.session_state.answered = False
    st.session_state.last_result = None


def start_weakness_practice(queue_indexes, return_index, return_result):
    """弱点克服用の問題を順番に解くモードを開始する。"""
    if len(queue_indexes) == 0:
        st.session_state.practice_complete_message = "出題できる弱点克服問題がありません。"
        return

    st.session_state.practice_mode = True
    st.session_state.practice_queue = queue_indexes
    st.session_state.practice_position = 0
    st.session_state.practice_return_index = return_index
    st.session_state.practice_return_result = return_result.copy() if return_result is not None else None
    st.session_state.practice_complete_message = ""

    st.session_state.current_index = queue_indexes[0]
    st.session_state.answered = False
    st.session_state.last_result = None


def reset_history():
    clear_answer_history_db()
    st.session_state.history = []
    st.session_state.answered = False
    st.session_state.last_result = None
    reset_random_quiz_order(problems)

    # AI履歴・入力欄・回答欄もまとめて削除
    keys_to_delete = []
    for key in st.session_state.keys():
        if (
            key.startswith("ai_chat_history_")
            or key.startswith("ai_pending_question_")
            or key.startswith("ai_notice_")
            or key.startswith("ai_question_input_")
            or key.startswith("answer_")
            or key.startswith("practice_")
        ):
            keys_to_delete.append(key)

    for key in keys_to_delete:
        del st.session_state[key]


def judge_answer(selected_answers, correct_answers):
    """完全正解・一部正解・不正解を判定する。"""
    selected_set = set(selected_answers)
    correct_set = set(correct_answers)

    hit_items = [item for item in correct_answers if item in selected_set]
    missed_items = [item for item in correct_answers if item not in selected_set]
    extra_items = [item for item in selected_answers if item not in correct_set]

    is_fully_correct = selected_set == correct_set
    is_partial_correct = (not is_fully_correct) and len(hit_items) > 0

    if is_fully_correct:
        judge_label = "完全正解"
        score_rate = 100.0
    elif is_partial_correct:
        judge_label = "一部正解"

        # 見抜けた正解数を基本にし、余計な選択がある場合は少し下げる
        raw_score = (len(hit_items) - len(extra_items) * 0.5) / len(correct_set) * 100
        score_rate = max(0.0, min(99.0, raw_score))
    else:
        judge_label = "不正解"
        score_rate = 0.0

    return {
        "judge_label": judge_label,
        "is_fully_correct": is_fully_correct,
        "is_partial_correct": is_partial_correct,
        "hit_items": hit_items,
        "missed_items": missed_items,
        "extra_items": extra_items,
        "score_rate": score_rate
    }


def calculate_category_stats(history):
    """カテゴリ別理解度を計算する。

    正解カテゴリを選べたかだけでなく、
    見逃したカテゴリ・余計に選んだカテゴリも弱点として扱う。
    """
    category_stats = {}

    def init_category(category):
        if category not in category_stats:
            category_stats[category] = {
                "total": 0,
                "correct": 0,
                "missed": 0,
                "extra": 0
            }

    for record in history:
        answer_categories = record.get("answer", record.get("category", []))
        selected_categories = record.get("selected", [])

        # 古い履歴形式への保険
        if "selected" not in record:
            selected_categories = answer_categories if record.get("correct", False) else []

        answer_set = set(answer_categories)
        selected_set = set(selected_categories)

        # 正解カテゴリについて、選べたか・見逃したかを記録
        for category in answer_categories:
            init_category(category)

            category_stats[category]["total"] += 1

            if category in selected_set:
                category_stats[category]["correct"] += 1
            else:
                category_stats[category]["missed"] += 1

        # 余計に選んだカテゴリも弱点として記録
        for category in selected_categories:
            if category not in answer_set:
                init_category(category)

                category_stats[category]["total"] += 1
                category_stats[category]["extra"] += 1

    return category_stats


def get_weak_categories(category_stats, threshold=80, top_n=5):
    """これまで解いた問題から、復習優先度が高いカテゴリだけを返す。"""

    weak_categories = []

    for category, stat in category_stats.items():
        total = stat["total"]
        correct = stat["correct"]
        missed = stat.get("missed", 0)
        extra = stat.get("extra", 0)

        if total == 0:
            continue

        accuracy = correct / total * 100

        # 正答率が低い・見逃しがある・余計に選んだ回数があるカテゴリを弱点候補にする
        has_problem = accuracy < threshold or missed > 0 or extra > 0

        if not has_problem:
            continue

        weakness_score = (100 - accuracy) + missed * 15 + extra * 12

        if accuracy < 60 or missed >= 2 or extra >= 2:
            level = "要復習"
        else:
            level = "注意"

        weak_categories.append({
            "category": category,
            "accuracy": accuracy,
            "total": total,
            "correct": correct,
            "missed": missed,
            "extra": extra,
            "level": level,
            "weakness_score": weakness_score
        })

    weak_categories = sorted(
        weak_categories,
        key=lambda x: x["weakness_score"],
        reverse=True
    )

    return weak_categories[:top_n]


def recommend_similar_problems(problems, target_problem_id, weak_categories, top_n=3):
    target_index = None

    for i, problem in enumerate(problems):
        if problem["id"] == target_problem_id:
            target_index = i
            break

    if target_index is None:
        return []

    texts = [problem["text"] for problem in problems]

    vectorizer = TfidfVectorizer(
        analyzer="char",
        ngram_range=(2, 4)
    )

    tfidf_matrix = vectorizer.fit_transform(texts)
    similarity_matrix = cosine_similarity(tfidf_matrix)

    target_problem = problems[target_index]
    target_categories = set(target_problem["category"])

    weak_category_names = set()
    for item in weak_categories:
        weak_category_names.add(item["category"])

    recommendations = []

    for i, candidate in enumerate(problems):
        if i == target_index:
            continue

        candidate_categories = set(candidate["category"])
        text_similarity = similarity_matrix[target_index][i]

        category_overlap = target_categories & candidate_categories
        category_bonus = 0.2 if len(category_overlap) > 0 else 0

        weak_overlap = weak_category_names & candidate_categories
        weak_bonus = 0.1 if len(weak_overlap) > 0 else 0

        recommend_score = text_similarity * 0.7 + category_bonus + weak_bonus

        recommendations.append({
            "index": i,
            "id": candidate["id"],
            "text": candidate["text"],
            "difficulty": candidate["difficulty"],
            "text_similarity": text_similarity,
            "score": recommend_score
        })

    recommendations = sorted(
        recommendations,
        key=lambda x: x["score"],
        reverse=True
    )

    return recommendations[:top_n]

def recommend_weakness_problems(problems, history, current_problem_id=None, top_n=10):
    """これまでの回答履歴から、弱点カテゴリを中心に復習問題を推薦する。

    弱点カテゴリに一致する問題を優先しつつ、
    足りない場合は一部正解・不正解・未回答の問題も候補に入れる。
    """

    if len(history) == 0:
        return [], []

    category_stats = calculate_category_stats(history)

    if len(category_stats) == 0:
        return [], []

    category_rank = []

    for category, stat in category_stats.items():
        total = stat["total"]
        correct = stat["correct"]
        missed = stat.get("missed", 0)
        extra = stat.get("extra", 0)

        if total == 0:
            continue

        accuracy = correct / total * 100
        weakness_score = (100 - accuracy) + missed * 15 + extra * 12

        category_rank.append({
            "category": category,
            "accuracy": accuracy,
            "total": total,
            "correct": correct,
            "missed": missed,
            "extra": extra,
            "weakness_score": weakness_score
        })

    category_rank = sorted(
        category_rank,
        key=lambda x: x["weakness_score"],
        reverse=True
    )

    weak_categories = [
        item["category"]
        for item in category_rank
        if item["accuracy"] < 80 or item["missed"] > 0 or item["extra"] > 0
    ]

    if len(weak_categories) == 0:
        weak_categories = [
            item["category"]
            for item in category_rank[:3]
        ]

    weak_category_set = set(weak_categories)

    problem_history = {}

    for record in history:
        problem_history[record["problem_id"]] = record

    recommendations = []

    for i, problem in enumerate(problems):
        problem_id = problem["id"]

        if current_problem_id is not None and problem_id == current_problem_id:
            continue

        problem_categories = set(problem["category"])
        overlap_categories = problem_categories & weak_category_set

        record = problem_history.get(problem_id)

        if record is None:
            answer_status = "未回答"
            status_bonus = 1.0
        elif record.get("correct", False):
            answer_status = "完全正解済み"
            status_bonus = -0.4
        elif record.get("judge_label") == "一部正解":
            answer_status = "一部正解"
            status_bonus = 1.2
        else:
            answer_status = "不正解"
            status_bonus = 1.4

        weakness_score = 0

        if len(overlap_categories) > 0:
            for category in overlap_categories:
                if category in category_stats:
                    total = category_stats[category]["total"]
                    correct = category_stats[category]["correct"]
                    missed = category_stats[category].get("missed", 0)
                    extra = category_stats[category].get("extra", 0)
                    accuracy = correct / total * 100 if total > 0 else 0

                    weakness_score += 2.0 + (100 - accuracy) / 100 + missed * 0.3 + extra * 0.25
        else:
            # 弱点カテゴリに直接一致しなくても候補には残す
            weakness_score += 0.2

        difficulty_bonus = problem.get("difficulty", 1) * 0.05
        recommend_score = weakness_score + status_bonus + difficulty_bonus

        recommendations.append({
            "index": i,
            "id": problem_id,
            "text": problem["text"],
            "difficulty": problem.get("difficulty", 1),
            "matched_categories": list(overlap_categories),
            "answer_status": answer_status,
            "score": recommend_score
        })

    recommendations = sorted(
        recommendations,
        key=lambda x: x["score"],
        reverse=True
    )

    return recommendations[:top_n], category_rank

def render_chat_message(role, content):
    safe_content = html.escape(content).replace("\n", "<br>")

    if role == "user":
        st.markdown(
            f"""
            <div class="bubble-row-user">
                <div class="bubble-user">{safe_content}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f"""
            <div class="bubble-row-ai">
                <div class="bubble-ai">{safe_content}</div>
            </div>
            """,
            unsafe_allow_html=True
        )


def render_answer_detail(detail):
    category = html.escape(detail.get("category", ""))
    evidence = html.escape(detail.get("evidence", ""))
    reason = html.escape(detail.get("reason", ""))

    st.markdown(
        f"""
        <div class="detail-card">
            <div class="detail-title">{category}</div>
            <div class="detail-label">該当箇所</div>
            <div class="detail-text">{evidence}</div>
            <div class="detail-label">理由</div>
            <div class="detail-text">{reason}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


def generate_gpt_explanation(
    user_question,
    problem_text,
    correct_categories,
    explanation_texts,
    chat_history,
    answer_details=None
):
    if genai is None:
        return "google-genai がインストールされていません。ターミナルで py -m pip install google-genai を実行してください。"

    if "GEMINI_API_KEY" not in st.secrets:
        return "Gemini APIキーが設定されていないため、AIチャットは利用できません。解説DBの内容を確認してください。"

    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

    explanation_context = ""
    for category, explanation in explanation_texts.items():
        explanation_context += f"【{category}】\n{explanation}\n\n"

    detail_context = ""
    if answer_details:
        for detail in answer_details:
            detail_context += (
                f"【{detail.get('category', '')}】\n"
                f"該当箇所: {detail.get('evidence', '')}\n"
                f"理由: {detail.get('reason', '')}\n\n"
            )

    chat_context = ""
    for message in chat_history:
        if message["role"] == "user":
            chat_context += f"利用者: {message['content']}\n"
        elif message["role"] == "assistant":
            chat_context += f"AI: {message['content']}\n"

    prompt = f"""
あなたは情報リテラシー学習を支援する先生です。

以下のルールを必ず守ってください。
- 解説DBと正解根拠の内容を根拠にして答える
- 解説DBや正解根拠にない内容は断定しない
- 正解判定は行わない
- 利用者がすでに回答した後の学習支援として説明する
- これまでの会話履歴を踏まえて、自然に続きの説明をする
- 初心者にも分かるようにやさしく説明する
- できるだけ短く、具体例を入れて説明する

【問題文】
{problem_text}

【正解カテゴリ】
{", ".join(correct_categories)}

【正解の根拠】
{detail_context}

【解説DB】
{explanation_context}

【これまでの会話】
{chat_context}

【今回の利用者の質問】
{user_question}
"""

    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite"
    ]

    last_error = None

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )

            return response.text

        except Exception as e:
            last_error = e
            error_message = str(e)

            if "RESOURCE_EXHAUSTED" in error_message or "quota" in error_message.lower():
                return (
                    "現在、生成AI APIの利用制限によりAIチャットを利用できません。\n\n"
                    "この場合でも、表示されている解説DBの内容を確認することで学習を続けられます。"
                )

            # 503や混雑の場合は次のモデルを試す
            continue

    return (
        "現在、Gemini APIが混雑している、または利用できるモデルに接続できませんでした。\n\n"
        "少し時間をおいてから、もう一度質問してください。\n\n"
        "なお、この場合でも表示されている解説DBの内容を確認することで学習を続けられます。\n\n"
        f"最後のエラー内容: {last_error}"
    )


def submit_ai_question(problem_id, input_key):
    chat_key = f"ai_chat_history_{problem_id}"
    notice_key = f"ai_notice_{problem_id}"
    pending_key = f"ai_pending_question_{problem_id}"

    if chat_key not in st.session_state:
        st.session_state[chat_key] = []

    if notice_key not in st.session_state:
        st.session_state[notice_key] = ""

    if pending_key not in st.session_state:
        st.session_state[pending_key] = ""

    user_question = st.session_state.get(input_key, "").strip()

    # text_areaのon_changeとボタンが続けて動いた場合の二重送信・空欄警告を防ぐ
    if st.session_state[pending_key] != "" and user_question == "":
        return

    if user_question == "":
        st.session_state[notice_key] = "質問を入力してください。"
        return

    st.session_state[notice_key] = ""

    # AIに渡す質問を一時保存する
    st.session_state[pending_key] = user_question

    # 入力欄を空にする
    st.session_state[input_key] = ""


# -----------------------------
# 現在の問題
# -----------------------------
current_index = st.session_state.current_index
problem = problems[current_index]


# -----------------------------
# サイドバー：学習状況
# -----------------------------
with st.sidebar:
    st.header("学習状況")

    total_answered = len(st.session_state.history)
    full_correct_count = sum(1 for h in st.session_state.history if h.get("correct", False))

    if total_answered > 0:
        full_accuracy = full_correct_count / total_answered * 100
        average_score = sum(h.get("score_rate", 100 if h.get("correct", False) else 0) for h in st.session_state.history) / total_answered
    else:
        full_accuracy = 0
        average_score = 0

    col_a, col_b = st.columns(2)

    with col_a:
        st.metric("回答数", f"{total_answered}")

    with col_b:
        st.metric("理解度", f"{average_score:.1f}%")

    st.caption(f"完全正解率：{full_accuracy:.1f}%")

    st.divider()

    if total_answered == 0:
        st.caption("問題に回答すると、理解度と弱点が表示されます。")
    else:
        category_stats = calculate_category_stats(st.session_state.history)
        weak_categories = get_weak_categories(category_stats, threshold=60)

        with st.expander("弱点推定を見る", expanded=True):
            st.caption("見逃しや余計な選択をもとに、復習した方がよいカテゴリを表示します。")

            if len(weak_categories) == 0:
                st.success("大きく低いカテゴリはありません。")
            else:
                for item in weak_categories:
                    label_class = "weak-label-red" if item["level"] == "要復習" else "weak-label-yellow"

                    st.markdown(
                        f"""
                        <div class="weak-card">
                            <div class="weak-title">
                                <span class="{label_class}">{item["level"]}</span>
                                {item["category"]}
                            </div>
                            <div class="weak-meta">
                                正解率：{item["accuracy"]:.1f}%（{item["correct"]}/{item["total"]}）<br>
                                見逃し：{item["missed"]}回 / 余計な選択：{item["extra"]}回
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                    st.progress(item["accuracy"] / 100)

        st.info(
            "弱点克服をしたい場合は、下の学習サポート欄にある「復習におすすめの類似問題」から復習できます。"
        )

        with st.expander("カテゴリ別理解度を見る", expanded=True):
            for category, stat in category_stats.items():
                total = stat["total"]
                correct = stat["correct"]
                category_accuracy = correct / total * 100

                missed = stat.get("missed", 0)
                extra = stat.get("extra", 0)

                st.markdown(
                    f'<div class="sidebar-small"><b>{category}</b>：{category_accuracy:.1f}%（{correct}/{total}）</div>',
                    unsafe_allow_html=True
                )
                st.caption(f"見逃し：{missed}回 / 余計な選択：{extra}回")
                st.progress(category_accuracy / 100)

    st.divider()

    st.button(
        "回答履歴をリセット",
        on_click=reset_history,
        use_container_width=True
    )


# -----------------------------
# ヘッダー
# -----------------------------
st.markdown(
    '<div class="main-title">情報リテラシー学習支援システム</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="sub-title">フィッシングメールやフェイクニュースの危険要素を学び、苦手分野に応じて類似問題を推薦します。</div>',
    unsafe_allow_html=True
)

if st.session_state.practice_complete_message != "":
    st.success(st.session_state.practice_complete_message)
    st.session_state.practice_complete_message = ""

if st.session_state.practice_mode:
    practice_total = len(st.session_state.practice_queue)
    practice_now = st.session_state.practice_position + 1

    st.progress(practice_now / practice_total)
    st.caption(f"弱点克服モード：{practice_now} / {practice_total}問目")
else:
    current_quiz_pos = st.session_state.current_quiz_pos
    st.progress((current_quiz_pos + 1) / len(problems))
    st.caption(f"問題 {current_quiz_pos + 1} / {len(problems)}（ランダム出題）")


# -----------------------------
# メイン：問題と結果を横並び
# -----------------------------
left_col, right_col = st.columns([1.35, 1], gap="large")


# -----------------------------
# 左側：問題
# -----------------------------
with left_col:
    with st.container(border=True):
        st.subheader("問題")

        st.write(problem["question"])
        st.info(problem["text"])

        if not st.session_state.answered:
            with st.form(key=f"question_form_{problem['id']}"):
                selected = st.multiselect(
                    "危険要素を選択してください",
                    problem["choices"],
                    key=f"answer_{problem['id']}"
                )

                submitted = st.form_submit_button(
                    "回答する",
                    use_container_width=True,
                    type="primary"
                )

            if submitted:
                judge = judge_answer(selected, problem["answer"])

                st.session_state.last_result = {
                    "problem_id": problem["id"],
                    "selected": selected,
                    "answer": problem["answer"],
                    "correct": judge["is_fully_correct"],
                    "category": problem["category"],
                    "answer_details": problem.get("answer_details", []),
                    "judge_label": judge["judge_label"],
                    "hit_items": judge["hit_items"],
                    "missed_items": judge["missed_items"],
                    "extra_items": judge["extra_items"],
                    "score_rate": judge["score_rate"]
                }

                history_record = {
                    "problem_id": problem["id"],
                    "category": problem["category"],
                    "answer": problem["answer"],
                    "selected": selected,
                    "correct": judge["is_fully_correct"],
                    "judge_label": judge["judge_label"],
                    "score_rate": judge["score_rate"]
                }

                st.session_state.history.append(history_record)
                save_answer_history(history_record)

                st.session_state.answered = True

        else:
            st.caption("この問題は回答済みです。右側で結果を確認してください。")


# -----------------------------
# 右側：結果
# -----------------------------
with right_col:
    with st.container(border=True):
        st.subheader("結果")

        if st.session_state.answered and st.session_state.last_result is not None:
            result = st.session_state.last_result

            if result["judge_label"] == "完全正解":
                st.success("完全正解です")
            elif result["judge_label"] == "一部正解":
                st.warning("一部正解です")
            else:
                st.error("不正解です")

            st.write("**あなたの回答**")
            st.write("、".join(result["selected"]) if result["selected"] else "未選択")

            st.write("**正解**")
            st.write("、".join(result["answer"]))

            if result["hit_items"]:
                st.success("見抜けた危険要素：" + "、".join(result["hit_items"]))

            if result["missed_items"]:
                st.warning("見逃した危険要素：" + "、".join(result["missed_items"]))

            if result["extra_items"]:
                st.info("余計に選んだ要素：" + "、".join(result["extra_items"]))

            next_button_label = "次の問題へ"

            if st.session_state.practice_mode:
                if st.session_state.practice_position + 1 < len(st.session_state.practice_queue):
                    next_button_label = "次の弱点克服問題へ"
                else:
                    next_button_label = "弱点克服を終了して元の問題へ戻る"

            st.button(
                next_button_label,
                on_click=next_problem,
                use_container_width=True,
                type="primary"
            )

            st.caption("解説・AI質問・類似問題は下の学習サポート欄で確認できます。")

        else:
            result = None
            st.write("問題に回答すると、ここに結果が表示されます。")
            st.caption("回答後すぐに、この場所から次の問題へ進めます。")


# -----------------------------
# 下側：学習サポート
# -----------------------------
if st.session_state.answered and st.session_state.last_result is not None:
    result = st.session_state.last_result

    st.divider()
    st.subheader("学習サポート")

    support_tab1, support_tab2, support_tab3 = st.tabs(
        ["解説を見る", "AIに質問する", "復習におすすめの類似問題"]
    )

    # -----------------------------
    # 解説を見る
    # -----------------------------
    with support_tab1:
        st.write("正解カテゴリについて、該当箇所・理由・解説DBの説明を表示します。")

        current_explanation_texts = {}
        answer_details = result.get("answer_details", [])

        if answer_details:
            st.markdown("#### 正解の根拠")
            for detail in answer_details:
                render_answer_detail(detail)

        st.markdown("#### カテゴリ解説")

        for category in result["answer"]:
            explanation_text = explanations.get(category)

            if explanation_text:
                current_explanation_texts[category] = explanation_text

                with st.container(border=True):
                    st.markdown(f"### {category}")
                    st.write(explanation_text)
            else:
                st.warning(f"{category} の解説はまだ登録されていません。")

    # -----------------------------
    # AIに質問する
    # -----------------------------
    with support_tab2:
        st.write("解説を読んでも分からない点を、AIに追加で質問できます。")
        st.caption("※AIは正解判定には使わず、解説DBの内容をもとに説明します。")

        current_explanation_texts = {}

        for category in result["answer"]:
            explanation_text = explanations.get(category)
            if explanation_text:
                current_explanation_texts[category] = explanation_text

        chat_key = f"ai_chat_history_{result['problem_id']}"
        input_key = f"ai_question_input_{result['problem_id']}"
        notice_key = f"ai_notice_{result['problem_id']}"
        pending_key = f"ai_pending_question_{result['problem_id']}"

        if chat_key not in st.session_state:
            st.session_state[chat_key] = []

        if input_key not in st.session_state:
            st.session_state[input_key] = ""

        if notice_key not in st.session_state:
            st.session_state[notice_key] = ""

        if pending_key not in st.session_state:
            st.session_state[pending_key] = ""

        chat_col, input_col = st.columns([1.45, 1], gap="large")

        # -----------------------------
        # 左側：会話履歴
        # -----------------------------
        with chat_col:
            st.markdown("#### AIとの会話履歴")

            chat_area = st.container(height=360, border=True)

            with chat_area:
                if len(st.session_state[chat_key]) == 0:
                    st.markdown(
                        '<div class="chat-empty">まだ質問はありません。右側の入力欄からAIに質問できます。</div>',
                        unsafe_allow_html=True
                    )
                else:
                    for message in st.session_state[chat_key]:
                        render_chat_message(message["role"], message["content"])

        # -----------------------------
        # 右側：質問入力欄
        # -----------------------------
        with input_col:
            with st.container(border=True):
                st.markdown("#### AIへの質問入力欄")
                st.info("解説で分からなかった点や、もう少し詳しく知りたい内容を入力してください。")

                st.text_area(
                    "質問内容",
                    key=input_key,
                    placeholder="例：なぜこの表現が危険なのですか？",
                    height=180,
                    on_change=submit_ai_question,
                    args=(
                        result["problem_id"],
                        input_key
                    )
                )

                st.caption("ボタン、または Ctrl + Enter で送信できます。")

                if st.session_state[notice_key] != "":
                    st.warning(st.session_state[notice_key])

                st.button(
                    "AIに送信する",
                    key=f"send_ai_question_{result['problem_id']}",
                    on_click=submit_ai_question,
                    args=(
                        result["problem_id"],
                        input_key
                    ),
                    use_container_width=True,
                    type="primary"
                )

                # -----------------------------
                # AI回答生成中の処理
                # ボタンの下に spinner を表示する
                # -----------------------------
                if st.session_state[pending_key] != "":
                    user_question = st.session_state[pending_key]

                    st.session_state[chat_key].append({
                        "role": "user",
                        "content": user_question
                    })

                    with st.spinner("AIが回答を作成しています..."):
                        ai_answer = generate_gpt_explanation(
                            user_question=user_question,
                            problem_text=problem["text"],
                            correct_categories=result["answer"],
                            explanation_texts=current_explanation_texts,
                            chat_history=st.session_state[chat_key],
                            answer_details=result.get("answer_details", [])
                        )

                    st.session_state[chat_key].append({
                        "role": "assistant",
                        "content": ai_answer
                    })

                    st.session_state[pending_key] = ""
                    st.rerun()

                st.divider()

                if st.button(
                    "この問題のAI履歴を削除する",
                    key=f"clear_ai_chat_{result['problem_id']}",
                    use_container_width=True
                ):
                    st.session_state[chat_key] = []
                    st.session_state[notice_key] = ""
                    st.session_state[pending_key] = ""
                    st.rerun()

    # -----------------------------
    # 類似問題推薦
    # -----------------------------
    with support_tab3:
        st.write("今回の問題に似た問題と、これまでの回答履歴から見た弱点克服用の問題を推薦します。")

        category_stats = calculate_category_stats(st.session_state.history)
        weak_categories = get_weak_categories(category_stats, threshold=60)

        # -----------------------------
        # 1. 今回の問題に似た問題
        # -----------------------------
        st.markdown("### 今回の問題に似た復習問題")

        similar_recommendations = recommend_similar_problems(
            problems=problems,
            target_problem_id=result["problem_id"],
            weak_categories=weak_categories,
            top_n=3
        )

        if len(similar_recommendations) == 0:
            st.info("今回の問題に似た問題は見つかりませんでした。")
        else:
            similar_cols = st.columns(3)

            for rank, rec in enumerate(similar_recommendations, start=1):
                with similar_cols[rank - 1]:
                    with st.container(border=True):
                        st.markdown(f"#### 類似問題 {rank}")
                        st.info(rec["text"])
                        st.caption(
                            f"難易度：{rec['difficulty']} / "
                            f"文章類似度：{rec['text_similarity']:.3f}"
                        )

                        st.button(
                            "この問題を解く",
                            key=f"similar_current_{result['problem_id']}_{rec['id']}",
                            on_click=move_to_problem,
                            args=(rec["index"],),
                            use_container_width=True
                        )

        st.divider()

        # -----------------------------
        # 2. 弱点克服用の問題
        # -----------------------------
        st.markdown('<div id="weakness-practice-area"></div>', unsafe_allow_html=True)
        st.markdown("### 弱点克服のためのおすすめ問題")

        if len(st.session_state.history) == 0:
            st.info("回答履歴がまだないため、弱点克服用の問題は表示できません。")
        else:
            max_recommend_count = max(1, len(problems) - 1)

            recommend_count = st.slider(
                "表示する問題数",
                min_value=1,
                max_value=max_recommend_count,
                value=1,
                step=1
            )

            weakness_recommendations, category_rank = recommend_weakness_problems(
                problems=problems,
                history=st.session_state.history,
                current_problem_id=result["problem_id"],
                top_n=recommend_count
            )

            if len(category_rank) > 0:
                st.write("**現在、復習を優先したいカテゴリ**")

                weak_texts = []

                for item in category_rank[:3]:
                    weak_texts.append(
                        f"{item['category']}：{item['accuracy']:.1f}%"
                    )

                st.caption(" / ".join(weak_texts))

            if len(weakness_recommendations) == 0:
                st.info("現在の回答履歴では、弱点克服用として表示できる問題がありません。")
                st.caption("問題数を増やすと、より多くの弱点克服問題を推薦できます。")
            else:
                weakness_queue_indexes = [
                    rec["index"]
                    for rec in weakness_recommendations
                ]

                st.button(
                    f"このおすすめ問題を順番に解く（{len(weakness_queue_indexes)}問）",
                    key=f"start_weakness_practice_{result['problem_id']}_{recommend_count}",
                    on_click=start_weakness_practice,
                    args=(
                        weakness_queue_indexes,
                        current_index,
                        result
                    ),
                    use_container_width=True,
                    type="primary"
                )

                st.caption("選んだ問題数分だけ順番に出題し、すべて解き終わると元の問題に戻ります。")

                for rank, rec in enumerate(weakness_recommendations, start=1):
                    with st.container(border=True):
                        col1, col2 = st.columns([3, 1])

                        with col1:
                            st.markdown(f"#### 弱点克服問題 {rank}")
                            st.info(rec["text"])

                            st.caption(
                                f"難易度：{rec['difficulty']} / "
                                f"現在の回答状況：{rec['answer_status']}"
                            )

                        with col2:
                            st.button(
                                "この問題だけ解く",
                                key=f"weakness_recommend_{result['problem_id']}_{rec['id']}",
                                on_click=move_to_problem,
                                args=(rec["index"],),
                                use_container_width=True
                            )