# 【アプリ名（）】

ITパスポートおよび基本情報技術者試験の学習をサポートするWebアプリケーションです。

## 🌟 主な機能
* **資格試験対策クイズ**: ITパスポート・基本情報技術者試験の過去問データ（JSON）を用いたクイズ機能
* **学習ダッシュボード**: 学習の進捗や正答率を視覚的に確認
* **分散学習（SRS）ロジック**: 効率的な記憶定着のための出題アルゴリズムを利用

## 🛠 使用技術
* **フロントエンド・バックエンド**: Python, Streamlit
* **データベース・クラウド**: AWS (DynamoDB等) / `boto3` を用いた連携
* **データ処理**: Pandas, NumPy
* **その他**: 複数AIモデルAPI

## 📂 ディレクトリ構成
```text
.
├── app.py                  # アプリケーションのメインファイル
├── aws_db.py               # AWS DynamoDB等との連携用モジュール
├── dashboard.py            # 学習状況可視化ダッシュボード
├── quiz_page.py            # クイズ出題・AI評価画面
├── srs_logic.py            # 分散学習（Spaced Repetition System）ロジック
├── requirements.txt        # 必要なPythonパッケージ一覧
├── images/                 # 画像リソース
└── FEA5-7_ALL_QA.json 等   # 過去問データセット (JSON)