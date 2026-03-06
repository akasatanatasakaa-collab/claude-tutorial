# 請求書・領収書 → MFクラウド会計インポートシステム（会計事務所向け）

Google Driveに保存された請求書・領収書をGemini APIで読み取り、
**顧客ごとの過去の仕訳パターン・暗黙知**を参考にMoneyForwardクラウド会計のインポート用CSVを自動生成する。

## 会計事務所向けの設計思想

手島春樹氏（税理士法人SoLabo）が指摘するように、仕訳は証憑を見ただけでは決まらない。
「なぜその勘定科目か」「なぜその税区分か」は顧客ごとの暗黙知に依存する。

このシステムでは：
- **顧客ごとに仕訳履歴を分離管理**（A社の癖がB社に混ざらない）
- **暗黙知をルールとして明文化**し、Gemini APIのプロンプトに注入
- 処理するたびに新しい取引先パターンを**自動学習**

## システム構成

```
invoice_import/
├── main.py              # メインスクリプト
├── client_manager.py    # 顧客管理モジュール
├── drive_client.py      # Google Drive連携
├── gemini_reader.py     # Gemini API読み取り（顧客ルール反映）
├── mf_exporter.py       # MF仕訳CSV生成 + 履歴管理
├── config.json          # グローバル設定
├── requirements.txt     # 依存パッケージ
└── clients/             # 顧客別データ
    ├── company_a/
    │   ├── client_config.json    # 顧客設定（Driveフォルダ等）
    │   ├── journal_history.json  # この顧客の仕訳パターン + ルール
    │   └── output/               # CSV出力先
    ├── company_b/
    │   ├── ...
```

## セットアップ

### 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. Google Drive API の設定

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成
2. Google Drive API を有効化
3. OAuth 2.0 クライアントIDを作成し `credentials.json` を配置

### 3. Gemini API の設定

```bash
export GEMINI_API_KEY=your_api_key_here
```

## 使い方

### 顧客の登録

```bash
# 新規顧客を作成（Google DriveフォルダIDを指定）
python main.py --create-client company_a --name "株式会社A" --drive-folder "1abc..."

# 顧客一覧を確認
python main.py --list-clients
```

### 仕訳の処理

```bash
# Google Driveから取得して処理
python main.py --client company_a

# ローカルファイルを直接処理
python main.py --client company_a --local invoice1.pdf receipt.png
```

### 暗黙知の管理（重要）

顧客ごとの「仕訳の癖」をルールとして登録する。
このルールはGemini APIのプロンプトに注入され、読み取り精度が向上する。

```bash
# ルールの追加
python main.py --client company_a --add-rule "交際費は5,000円以下でも全て交際費（会議費は使わない）"
python main.py --client company_a --add-rule "Amazonの購入は全て消耗品費で処理"
python main.py --client company_a --add-rule "社長の携帯料金は通信費ではなく役員報酬の付随費用"
python main.py --client company_a --add-rule "売上の入金は全て売掛金の消込（売上計上はしない）"

# ルール一覧の確認
python main.py --client company_a --list-rules
```

### マッピングの管理

```bash
# 取引先→勘定科目のマッピングを手動追加
python main.py --client company_a --add-mapping "AWS" "通信費" "クラウドサービス"
python main.py --client company_a --add-mapping "オフィスデポ" "消耗品費"

# マッピング一覧の確認
python main.py --client company_a --list-mappings
```

## 処理フロー

```
1. --client で顧客を指定
2. Google Drive（顧客別フォルダ）からファイルを取得
3. 顧客の暗黙知ルール + 過去マッピングをGemini APIのプロンプトに注入
4. Gemini APIで画像/PDFから請求書情報を抽出
5. 顧客固有のjournal_history.jsonと照合し勘定科目を自動マッピング
6. MFクラウド会計のインポート用CSVを顧客別ディレクトリに出力
7. 新しい取引先を顧客の仕訳履歴に自動追加（学習）
```

## 暗黙知をどう扱うか

手島氏の指摘する「AIだけでは記帳が自動化できない」理由への対処：

| 課題 | このシステムでの対応 |
|------|---------------------|
| 勘定科目の判断は顧客ごとに違う | `clients/*/journal_history.json` で顧客別に管理 |
| 判断基準が明文化されていない | `--add-rule` で暗黙知を形式知として記録 |
| 同じ取引先でも科目が変わる | ルールで条件分岐を記述可能 |
| ベテランの頭の中にしかない | ルールとして蓄積し、担当者が変わっても引き継げる |
| AIは答えにブレがある | 過去マッピングをプロンプトに注入し一貫性を確保 |
