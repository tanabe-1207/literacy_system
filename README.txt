情報リテラシー学習支援システム 実行方法

1. 概要
本システムは、フィッシングメールやフェイクニュースの危険要素を学習するためのWebアプリケーションである。
学習者用アプリでは、問題出題、回答判定、解説表示、AI質問、弱点推定、類似問題推薦を行う。
管理画面アプリでは、URL登録、問題候補生成、候補確認・修正、problems.jsonへの追加を行う。

2. 実行環境
Windows 11
Python 3.14（64bit）

3. 必要なライブラリ
必要なライブラリは requirements.txt に記載している。
以下のコマンドでインストールできる。

py -m pip install -r requirements.txt

4. 使用している主なライブラリ
streamlit==1.58.0
google-genai==2.10.0
scikit-learn==1.9.0
requests==2.34.2
beautifulsoup4==4.15.0
SudachiPy==0.6.11
SudachiDict-core

5. 学習者用アプリの起動方法
以下のコマンドを実行する。

py -m streamlit run app.py

6. 管理画面アプリの起動方法
以下のコマンドを実行する。

py -m streamlit run admin_app.py

（おすすめURL）
情報セキュリティ安心相談窓口の相談状況［2025年第3四半期（7月～9月）］
https://www.ipa.go.jp/security/anshin/reports/2025q3outline.html

PayPayアプリでの支払いへ誘導するフィッシング (2026/04/02)
https://www.antiphishing.jp/news/alert/paypay_20260402.html

高市首相が「移民より出産増で人口減対策」と演説? 出生率向上重視しつつ、外国人労働力も否定せず
https://www.factcheckcenter.jp/fact-check/politics/did-pm-takaichi-really-advocate-for-raising-the-birth-rate-over-immigration-as-a-solution-to-population-decline/


7. Gemini APIについて
Gemini APIを利用するため、.streamlit/secrets.toml にAPIキーを設定している必要がある。
また、Gemini APIのリソース制限が発生した場合、AI質問機能や問題候補の文章整形が十分に行えなくなる可能性がある。
Webページから抽出した文章はそのままでは問題文として不自然な場合があるため、AI整形が使えないと問題生成の質が低下する点に注意。

8. 主なファイル
app.py：学習者用アプリ
admin_app.py：管理画面アプリ
fetch_cases.py：登録URLからWebページを取得する
segment_cases.py：本文から問題素材を抽出する
problem_generator.py：問題候補を生成する
refine_candidates_with_ai.py：Gemini APIで問題候補を整形する
create_approved_candidates.py：候補を承認済み・要確認・破棄に分類する
promote_candidates.py：承認済み候補をproblems.jsonに追加する

data/problems.json：本番問題データ
data/explanations.json：カテゴリ解説データ
data/category_rules.json：カテゴリ判定ルール
data/source_urls.json：問題生成に利用するURL一覧
data/literacy.db：回答履歴と出題状態を保存するSQLiteデータベース

9. 注意点
URLからの問題候補生成は、HTML本文を取得できるWebページを対象としている。
ログインが必要なページ、PDFのみのページ、画像中心のページでは、正しく問題候補を生成できない場合がある。