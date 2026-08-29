import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


# =============================
# パス設定
# =============================
BASE_DIR = Path(__file__).parent

DATA_DIR = BASE_DIR / "data"

SOURCE_URLS_PATH = DATA_DIR / "source_urls.json"
APPROVED_PATH = DATA_DIR / "approved_candidates.json"
REVIEW_PATH = DATA_DIR / "review_candidates.json"
PROBLEMS_PATH = DATA_DIR / "problems.json"


# =============================
# 基本関数
# =============================
def load_json(path, default=None):
    if default is None:
        default = []

    if not path.exists():
        return default

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_file_version(path):
    """
    JSONファイルの更新時刻を取得する。
    Streamlitの入力欄keyに入れることで、
    JSONが更新されたときに古い入力状態が残らないようにする。
    """

    if not path.exists():
        return "no_file"

    return str(int(path.stat().st_mtime))


def clear_candidate_editor_state():
    """
    候補編集画面の古い入力状態を削除する。
    JSONを再読み込みしたいときに使う。
    """

    prefixes = ("approved_", "review_")

    keys_to_delete = []

    for key in st.session_state.keys():
        if key.startswith(prefixes):
            keys_to_delete.append(key)

    for key in keys_to_delete:
        del st.session_state[key]

def decode_process_output(data):
    """
    subprocess の出力を文字化けしにくい形でデコードする。
    Windows環境では cp932 になる場合があるため、複数の文字コードを試す。
    """

    if not data:
        return ""

    encodings = [
        "utf-8",
        "cp932",
        "shift_jis"
    ]

    for encoding in encodings:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass

    return data.decode("utf-8", errors="replace")


def run_script(script_name):
    """
    Pythonスクリプトを実行する。
    Streamlit上で実行ログが文字化けしないように、
    子プロセスの出力をUTF-8に統一する。
    """

    script_path = BASE_DIR / script_name

    if not script_path.exists():
        return False, f"{script_name} が見つかりません。"

    env = os.environ.copy()

    # 子プロセス側のPython出力をUTF-8に統一する
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env
    )

    output = result.stdout if result.stdout else ""

    return result.returncode == 0, output


def default_source_rows():
    return [
        {
            "id": 1,
            "source": "IPA",
            "type": "phishing",
            "title": "",
            "url": ""
        },
        {
            "id": 2,
            "source": "フィッシング対策協議会",
            "type": "phishing",
            "title": "",
            "url": ""
        },
        {
            "id": 3,
            "source": "JFC",
            "type": "fake_news",
            "title": "",
            "url": ""
        }
    ]


def get_source_rows_for_editor():
    """
    source_urls.json があれば読み込む。
    なければ初期テンプレートを出す。
    """

    saved = load_json(SOURCE_URLS_PATH, default=[])

    if not saved:
        return default_source_rows()

    # 既存データをテンプレート3行に戻して表示しやすくする
    template = default_source_rows()

    for row in template:
        for saved_row in saved:
            if row["id"] == saved_row.get("id"):
                row["source"] = saved_row.get("source", row["source"])
                row["type"] = saved_row.get("type", row["type"])
                row["title"] = saved_row.get("title", "")
                row["url"] = saved_row.get("url", "")

    return template


def save_source_urls_from_editor(rows):
    """
    URLが空の行は保存しない。
    つまり、空欄なら問題生成対象にしない。
    """

    cleaned = []

    for index, row in enumerate(rows, start=1):
        source = str(row.get("source", "")).strip()
        problem_type = str(row.get("type", "")).strip()
        title = str(row.get("title", "")).strip()
        url = str(row.get("url", "")).strip()

        if not url:
            continue

        cleaned.append({
            "id": index,
            "source": source,
            "type": problem_type,
            "title": title,
            "url": url
        })

    save_json(SOURCE_URLS_PATH, cleaned)

    return cleaned


def candidates_to_summary(candidates):
    rows = []

    for item in candidates:
        rows.append({
            "id": item.get("id"),
            "source": item.get("source", ""),
            "type": item.get("type", ""),
            "title": item.get("title", ""),
            "answer": "、".join(item.get("answer", [])),
            "difficulty": item.get("difficulty", ""),
            "text": item.get("text", "")[:80]
        })

    return pd.DataFrame(rows)


def find_candidate_index(candidates, candidate_id):
    for index, item in enumerate(candidates):
        if item.get("id") == candidate_id:
            return index

    return None


def as_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def normalize_candidate(candidate):
    """
    編集後の候補を最低限整える。
    answer と category は一致させる。
    """

    choices = as_list(candidate.get("choices", []))
    answer = as_list(candidate.get("answer", []))

    candidate["choices"] = choices
    candidate["answer"] = answer
    candidate["category"] = answer
    candidate["difficulty"] = int(candidate.get("difficulty", 2))

    return candidate


# =============================
# 候補編集UI
# =============================
def edit_candidate_ui(candidate, key_prefix):
    """
    1件の候補を編集するUI。
    text、choices、answer、difficulty、answer_detailsを編集できる。
    """

    edited = dict(candidate)

    st.markdown("#### 問題文")

    edited["text"] = st.text_area(
        "text",
        value=edited.get("text", ""),
        height=130,
        key=f"{key_prefix}_text"
    )

    st.markdown("#### 選択肢")

    choices_text = "\n".join(as_list(edited.get("choices", [])))

    choices_text = st.text_area(
        "choices（1行に1つ）",
        value=choices_text,
        height=110,
        key=f"{key_prefix}_choices"
    )

    choices = [
        line.strip()
        for line in choices_text.splitlines()
        if line.strip()
    ]

    edited["choices"] = choices

    default_answer = [
        ans for ans in as_list(edited.get("answer", []))
        if ans in choices
    ]

    edited["answer"] = st.multiselect(
        "正解カテゴリ answer",
        options=choices,
        default=default_answer,
        key=f"{key_prefix}_answer"
    )

    edited["category"] = edited["answer"]

    edited["difficulty"] = st.selectbox(
        "難易度",
        options=[1, 2, 3],
        index=max(0, min(2, int(edited.get("difficulty", 2)) - 1)),
        key=f"{key_prefix}_difficulty"
    )

    st.markdown("#### 根拠と理由 answer_details")

    old_details = as_list(edited.get("answer_details", []))
    detail_map = {}

    for detail in old_details:
        if isinstance(detail, dict):
            detail_map[detail.get("category", "")] = detail

    new_details = []

    for ans in edited["answer"]:
        old_detail = detail_map.get(ans, {})

        with st.container(border=True):
            st.markdown(f"**{ans}**")

            evidence = st.text_input(
                "evidence",
                value=old_detail.get("evidence", ""),
                key=f"{key_prefix}_{ans}_evidence"
            )

            reason = st.text_area(
                "reason",
                value=old_detail.get("reason", ""),
                height=80,
                key=f"{key_prefix}_{ans}_reason"
            )

            new_details.append({
                "category": ans,
                "evidence": evidence,
                "reason": reason
            })

    edited["answer_details"] = new_details

    return normalize_candidate(edited)


def candidate_editor_section(file_path, title, mode):
    """
    approved_candidates.json または review_candidates.json を編集する。
    mode:
      approved
      review
    """

    st.subheader(title)

    file_version = get_file_version(file_path)

    col_reload1, col_reload2 = st.columns([1, 3])

    with col_reload1:
        if st.button("JSONを再読み込み", key=f"{mode}_reload_{file_version}"):
            clear_candidate_editor_state()
            st.rerun()

    with col_reload2:
        st.caption(f"読み込み元: {file_path}")
        st.caption(f"JSON更新バージョン: {file_version}")

    candidates = load_json(file_path, default=[])

    if not candidates:
        st.info("候補がありません。")
        return

    st.dataframe(
        candidates_to_summary(candidates),
        use_container_width=True
    )

    with st.expander("この画面が読み込んでいるJSONの中身を確認", expanded=False):
        st.json(candidates)

    candidate_ids = [
        item.get("id")
        for item in candidates
    ]

    selected_id = st.selectbox(
        "編集する候補ID",
        options=candidate_ids,
        key=f"{mode}_selected_id_{file_version}"
    )

    selected_index = find_candidate_index(candidates, selected_id)

    if selected_index is None:
        st.warning("候補が見つかりません。")
        return

    selected_candidate = candidates[selected_index]

    with st.expander("候補を編集する", expanded=True):
        edited = edit_candidate_ui(
            selected_candidate,
            key_prefix=f"{mode}_{selected_id}_{file_version}"
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("この候補を保存", key=f"{mode}_{selected_id}_{file_version}_save"):
                candidates[selected_index] = edited
                save_json(file_path, candidates)
                clear_candidate_editor_state()
                st.success("保存しました。")
                st.rerun()

        with col2:
            if mode == "review":
                if st.button("この候補を承認候補へ移動", key=f"{mode}_{selected_id}_{file_version}_approve"):
                    approved = load_json(APPROVED_PATH, default=[])

                    approved.append(edited)
                    del candidates[selected_index]

                    save_json(APPROVED_PATH, approved)
                    save_json(REVIEW_PATH, candidates)

                    clear_candidate_editor_state()
                    st.success("approved_candidates.json に移動しました。")
                    st.rerun()


# =============================
# Streamlit画面
# =============================
st.set_page_config(
    page_title="問題追加管理画面",
    page_icon="🛠️",
    layout="wide"
)

st.title("🛠️ 問題追加管理画面")

st.caption(
    "URL登録、Web収集、問題生成、AI整形、自動承認、候補修正、problems.jsonへの追加を行う管理画面です。"
)


tab_urls, tab_pipeline, tab_candidates, tab_promote = st.tabs([
    "① URL登録",
    "② 問題生成",
    "③ 候補確認・修正",
    "④ problems.jsonへ追加"
])


# =============================
# ① URL登録
# =============================
with tab_urls:
    st.header("① 収集URLの登録")

    st.write(
        "URLが空の行は保存されません。つまり、空欄のままなら問題生成対象になりません。"
    )

    st.info(
        "URLは、信頼できる注意喚起ページやファクトチェック記事を入力してください。"
        "普通のニュース記事よりも、手口・事例・判定理由が書かれているページの方が問題生成に向いています。"
    )

    with st.expander("URLを選ぶときの基本方針", expanded=False):
        st.markdown("""
このシステムでは、どのWebページでも安定して問題化できるわけではありません。  
問題生成に向いているのは、**手口・事例・注意点・根拠が具体的に書かれているページ**です。

特に、次のような情報源を使うと問題を作りやすくなります。

- フィッシング系：フィッシング対策協議会、IPA
- セキュリティ注意喚起：IPA
- フェイクニュース・誤情報：日本ファクトチェックセンター（JFC）

逆に、個人ブログやSNS投稿そのもの、まとめサイトなどは、信頼性や根拠が不明確な場合があるため避けた方がよいです。
        """)

    with st.expander("1. フィッシング系で使いやすいサイト", expanded=False):
        st.markdown("""
### フィッシング対策協議会

フィッシング対策協議会の注意喚起ページは、フィッシングメール・SMS・誘導URL・件名例などがまとまっているため、問題にしやすいです。

#### 使いやすいページの例

- 「〇〇をよそおうフィッシング」
- 「〇〇をかたるフィッシング」
- 「フィッシングメールの件名例」
- 「フィッシングサイトへの誘導URL例」
- メール本文例、SMS本文例、誘導URL例が載っているページ

#### 作りやすい問題カテゴリ

- URL偽装
- なりすまし
- 個人情報要求
- 緊急性誘導
- 金銭・送金要求

#### 検索例

~~~text
site:antiphishing.jp/news/alert "をよそおうフィッシング"
site:antiphishing.jp/news/alert "かたるフィッシング"
site:antiphishing.jp/news/alert "件名例"
site:antiphishing.jp/news/alert "誘導先のURL"
site:antiphishing.jp/news/alert "お支払い"
~~~
        """)

    with st.expander("2. セキュリティ注意喚起で使いやすいサイト", expanded=False):
        st.markdown("""
### IPA 情報セキュリティ安心相談窓口

IPAの注意喚起ページは、偽SMS、偽セキュリティ警告、サポート詐欺、不正ログインなど、利用者が注意すべき事例を扱っているため、情報リテラシー教材に向いています。

#### 使いやすいページの例

- 偽SMSに関する注意喚起
- 偽セキュリティ警告
- サポート詐欺
- 不正ログイン
- 添付ファイルやマルウェアに関する注意喚起

#### 作りやすい問題カテゴリ

- なりすまし
- 個人情報要求
- 緊急性誘導
- 添付ファイルの危険性
- 金銭・送金要求
- URL偽装

#### 検索例

~~~text
site:ipa.go.jp/security/anshin "偽SMS"
site:ipa.go.jp/security/anshin "フィッシング"
site:ipa.go.jp/security/anshin "サポート詐欺"
site:ipa.go.jp/security/anshin "偽セキュリティ警告"
site:ipa.go.jp/security/anshin "不正ログイン"
~~~
        """)

    with st.expander("3. フェイクニュース・誤情報で使いやすいサイト", expanded=False):
        st.markdown("""
### 日本ファクトチェックセンター（JFC）

JFCの記事は、SNSで拡散した情報に対して、何が誤りか、どのような根拠で判断したかが書かれているため、フェイクニュースや画像のミスリードの問題に向いています。

#### 使いやすいページの例

- 「〇〇という投稿が拡散したが誤り」
- 「画像が拡散したが、実際には別の写真」
- 「AI生成画像・動画に関する誤情報」
- 「統計や数字を誤って使った情報」
- 判定理由が具体的に書かれている記事

#### 作りやすい問題カテゴリ

- フェイクニュース
- 画像のミスリード
- 出典不明
- 誇張表現
- 統計の悪用
- 感情的表現

#### 検索例

~~~text
site:factcheckcenter.jp/fact-check "誤りです" "拡散"
site:factcheckcenter.jp/fact-check "画像" "誤り"
site:factcheckcenter.jp/fact-check "AI" "画像"
site:factcheckcenter.jp/fact-check "出典"
site:factcheckcenter.jp/fact-check "SNSで拡散"
site:factcheckcenter.jp/fact-check "判定理由"
~~~
        """)

    with st.expander("URLとして向いているページ・避けた方がよいページ", expanded=False):
        st.markdown("""
### URLとして向いているページ

次のようなページは問題生成に向いています。

- 手口が具体的に書かれているページ
- メール件名、本文例、URL例があるページ
- 何が危険なのかが説明されているページ
- ファクトチェック記事で、誤りの理由が書かれているページ
- 1ページの中に複数の事例が含まれているページ

### 避けた方がよいページ

次のようなページは、問題生成が不安定になりやすいです。

- 個人ブログ
- SNS投稿そのもの
- まとめサイト
- 広告が多いページ
- 本文が短すぎるページ
- ログインが必要なページ
- ニュース記事のように、危険要素がはっきりしないページ
- 意見や感想が中心で、事例や根拠が少ないページ

### 入力のコツ

- 最初は3つすべて埋めなくても大丈夫です。
- URLが空欄の行は保存されず、問題生成にも使われません。
- まずは「フィッシング対策協議会」「IPA」「JFC」から1件ずつ選ぶのがおすすめです。
- 問題がうまく作れない場合は、ニュース記事よりも「注意喚起」「事例」「判定理由」が書かれたページを選んでください。
        """)

    source_rows = get_source_rows_for_editor()

    df = pd.DataFrame(source_rows)

    edited_df = st.data_editor(
        df,
        use_container_width=True,
        num_rows="fixed",
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "source": st.column_config.TextColumn("source"),
            "type": st.column_config.SelectboxColumn(
                "type",
                options=["phishing", "fake_news"]
            ),
            "title": st.column_config.TextColumn("title"),
            "url": st.column_config.TextColumn("url")
        },
        key="source_urls_editor"
    )

    if st.button("source_urls.json に保存"):
        rows = edited_df.to_dict("records")
        saved_rows = save_source_urls_from_editor(rows)

        st.success(f"{len(saved_rows)} 件のURLを保存しました。")

        if saved_rows:
            st.json(saved_rows)
        else:
            st.warning("URLが入力されていないため、保存対象は0件です。")


# =============================
# ② 問題生成
# =============================
with tab_pipeline:
    st.header("② 問題生成パイプライン")

    st.write("上から順番に実行するか、一括実行してください。")

    scripts = [
        ("1. Webページ取得", "fetch_cases.py"),
        ("2. 事例分割", "segment_cases.py"),
        ("3. 問題候補生成", "problem_generator.py"),
        ("4. AI/ルール整形", "refine_candidates_with_ai.py"),
        ("5. 自動承認・確認分け", "create_approved_candidates.py")
    ]

    for label, script_name in scripts:
        with st.container(border=True):
            col1, col2 = st.columns([1, 3])

            with col1:
                run_button = st.button(label, key=f"run_{script_name}")

            with col2:
                st.code(f"py {script_name}")

            if run_button:
                with st.spinner(f"{script_name} を実行中..."):
                    ok, output = run_script(script_name)

                if ok:
                    st.success(f"{script_name} が完了しました。")
                else:
                    st.error(f"{script_name} でエラーが発生しました。")

                st.text_area(
                    "実行ログ",
                    value=output,
                    height=240,
                    key=f"log_{script_name}"
                )

    st.divider()

    if st.button("一括実行する"):
        for label, script_name in scripts:
            st.subheader(label)

            with st.spinner(f"{script_name} を実行中..."):
                ok, output = run_script(script_name)

            if ok:
                st.success(f"{script_name} が完了しました。")
            else:
                st.error(f"{script_name} でエラーが発生しました。")
                st.text_area(
                    "実行ログ",
                    value=output,
                    height=240,
                    key=f"batch_log_{script_name}"
                )
                st.stop()

            st.text_area(
                "実行ログ",
                value=output,
                height=180,
                key=f"batch_log_success_{script_name}"
            )

        st.success("問題生成パイプラインが完了しました。")


# =============================
# ③ 候補確認・修正
# =============================
with tab_candidates:
    st.header("③ 候補確認・修正")

    approved_candidates = load_json(APPROVED_PATH, default=[])
    review_candidates = load_json(REVIEW_PATH, default=[])

    col1, col2 = st.columns(2)

    with col1:
        st.metric("承認済み候補", len(approved_candidates))

    with col2:
        st.metric("確認が必要な候補", len(review_candidates))

    st.divider()

    candidate_tab1, candidate_tab2 = st.tabs([
        "承認済み候補 approved",
        "確認が必要な候補 review"
    ])

    with candidate_tab1:
        candidate_editor_section(
            APPROVED_PATH,
            "承認済み候補 approved_candidates.json",
            mode="approved"
        )

    with candidate_tab2:
        candidate_editor_section(
            REVIEW_PATH,
            "確認が必要な候補 review_candidates.json",
            mode="review"
        )


# =============================
# ④ problems.jsonへ追加
# =============================
with tab_promote:
    st.header("④ problems.jsonへ追加")

    problems = load_json(PROBLEMS_PATH, default=[])
    approved_candidates = load_json(APPROVED_PATH, default=[])

    st.metric("現在の問題数", len(problems))
    st.metric("追加候補数", len(approved_candidates))

    st.warning(
        "この操作を行うと、approved_candidates.json の候補を problems.json に追加します。"
    )

    if st.button("承認済み候補を problems.json に追加する"):
        with st.spinner("promote_candidates.py を実行中..."):
            ok, output = run_script("promote_candidates.py")

        if ok:
            st.success("problems.json への追加が完了しました。")
        else:
            st.error("promote_candidates.py でエラーが発生しました。")

        st.text_area(
            "実行ログ",
            value=output,
            height=300,
            key="promote_log"
        )

    st.divider()

    st.subheader("現在の problems.json の概要")

    if problems:
        summary_rows = []

        for p in problems:
            summary_rows.append({
                "id": p.get("id"),
                "type": p.get("type", ""),
                "source": p.get("source", "manual"),
                "title": p.get("title", ""),
                "answer": "、".join(p.get("answer", [])),
                "text": p.get("text", "")[:80]
            })

        st.dataframe(
            pd.DataFrame(summary_rows),
            use_container_width=True
        )
    else:
        st.info("problems.json が空です。")