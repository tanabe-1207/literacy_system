import json
import shutil
from pathlib import Path
from datetime import datetime


PROBLEMS_PATH = Path("data/problems.json")
APPROVED_PATH = Path("data/approved_candidates.json")
EXPLANATIONS_PATH = Path("data/explanations.json")
BACKUP_DIR = Path("data/backups")


REQUIRED_FIELDS = [
    "question",
    "text",
    "choices",
    "answer",
    "category",
    "difficulty",
    "answer_details"
]


def load_json(path, default=None):
    if default is None:
        default = []

    if not path.exists():
        return default

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def backup_file(path):
    if not path.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"{path.stem}_backup_{timestamp}{path.suffix}"

    shutil.copy2(path, backup_path)

    return backup_path


def load_allowed_categories():
    explanations = load_json(EXPLANATIONS_PATH, default=[])

    categories = []

    for item in explanations:
        category = item.get("category")

        if category and category not in categories:
            categories.append(category)

    return categories


def as_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def validate_candidate(candidate, allowed_categories):
    errors = []

    for field in REQUIRED_FIELDS:
        if field not in candidate:
            errors.append(f"必須項目がありません: {field}")

    text = candidate.get("text", "")
    choices = as_list(candidate.get("choices", []))
    answer = as_list(candidate.get("answer", []))
    category = as_list(candidate.get("category", []))
    answer_details = as_list(candidate.get("answer_details", []))

    if not text:
        errors.append("text が空です。")

    if len(choices) != 5:
        errors.append("choices が5個ではありません。")

    if len(answer) == 0:
        errors.append("answer が空です。")

    if len(answer) > 3:
        errors.append("answer が多すぎます。最大3個までにしてください。")

    if answer != category:
        errors.append("answer と category が一致していません。")

    if set(answer) - set(choices):
        errors.append("answer に含まれるカテゴリが choices にありません。")

    if len(answer) == len(choices):
        errors.append("choices がすべて正解になっています。")

    for ans in answer:
        if ans not in allowed_categories:
            errors.append(f"explanations.json に存在しないカテゴリです: {ans}")

    detail_categories = [
        detail.get("category")
        for detail in answer_details
        if isinstance(detail, dict)
    ]

    for ans in answer:
        if ans not in detail_categories:
            errors.append(f"answer_details に説明がないカテゴリです: {ans}")

    for detail in answer_details:
        if not isinstance(detail, dict):
            errors.append("answer_details の形式が正しくありません。")
            continue

        if not detail.get("category"):
            errors.append("answer_details の category が空です。")

        if not detail.get("evidence"):
            errors.append(f"evidence が空です: {detail.get('category', '')}")

        if not detail.get("reason"):
            errors.append(f"reason が空です: {detail.get('category', '')}")

    return errors


def normalize_problem(candidate, new_id):
    """
    approved_candidates.json の候補を problems.json 用に整える。
    既存IDと重複しないように、新しいIDを付け直す。
    """

    answer = as_list(candidate.get("answer", []))
    category = answer

    problem = {
        "id": new_id,
        "question": candidate.get(
            "question",
            "この文章で特に注意すべき危険要素を選択してください。"
        ),
        "text": candidate.get("text", ""),
        "choices": as_list(candidate.get("choices", [])),
        "answer": answer,
        "category": category,
        "difficulty": int(candidate.get("difficulty", 2)),
        "answer_details": as_list(candidate.get("answer_details", []))
    }

    # 参考情報として残しておく。app.pyで使わなくても問題ない。
    optional_fields = [
        "type",
        "source",
        "title",
        "url"
    ]

    for field in optional_fields:
        value = candidate.get(field)

        if value:
            problem[field] = value

    # 元の候補IDも残す
    problem["source_candidate_id"] = candidate.get("id")

    return problem


def get_max_problem_id(problems):
    max_id = 0

    for problem in problems:
        try:
            problem_id = int(problem.get("id", 0))
            max_id = max(max_id, problem_id)
        except Exception:
            pass

    return max_id


def main():
    problems = load_json(PROBLEMS_PATH, default=[])
    approved_candidates = load_json(APPROVED_PATH, default=[])
    allowed_categories = load_allowed_categories()

    if not approved_candidates:
        print(f"{APPROVED_PATH} に承認済み候補がありません。")
        return

    if not allowed_categories:
        print(f"{EXPLANATIONS_PATH} からカテゴリを読み込めませんでした。")
        return

    existing_texts = {
        problem.get("text", "").strip()
        for problem in problems
    }

    next_id = get_max_problem_id(problems) + 1

    added_problems = []
    skipped = []

    for candidate in approved_candidates:
        text = candidate.get("text", "").strip()
        candidate_id = candidate.get("id")

        if text in existing_texts:
            skipped.append((candidate_id, ["同じ本文の問題が既に problems.json に存在します。"]))
            continue

        errors = validate_candidate(candidate, allowed_categories)

        if errors:
            skipped.append((candidate_id, errors))
            continue

        problem = normalize_problem(candidate, next_id)

        problems.append(problem)
        added_problems.append((candidate_id, next_id))

        existing_texts.add(text)
        next_id += 1

    if not added_problems:
        print("追加できる問題はありませんでした。")
        print("スキップ内容:")

        for candidate_id, errors in skipped:
            print(f"- candidate_id={candidate_id}")
            for error in errors:
                print(f"  - {error}")

        return

    backup_path = backup_file(PROBLEMS_PATH)
    save_json(PROBLEMS_PATH, problems)

    print("=" * 60)

    if backup_path:
        print(f"バックアップを作成しました: {backup_path}")

    print(f"problems.json に問題を追加しました: {PROBLEMS_PATH}")
    print(f"追加件数: {len(added_problems)}")

    print("-" * 60)
    print("追加された問題ID:")

    for old_id, new_id in added_problems:
        print(f"candidate_id {old_id} → problem_id {new_id}")

    if skipped:
        print("-" * 60)
        print("スキップされた候補:")

        for candidate_id, errors in skipped:
            print(f"- candidate_id={candidate_id}")
            for error in errors:
                print(f"  - {error}")


if __name__ == "__main__":
    main()