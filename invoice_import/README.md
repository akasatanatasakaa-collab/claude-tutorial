# 請求書・領収書 → MFクラウド会計インポートシステム

Google Driveに保存された請求書・領収書をGemini APIで読み取り、
過去の仕訳履歴を参考にMoneyForwardクラウド会計のインポート用CSVを自動生成するシステム。

## システム構成

```
invoice_import/
├── main.py              # メインスクリプト（エントリーポイント）
├── drive_client.py      # Google Drive連携モジュール
├── gemini_reader.py     # Gemini API請求書読み取りモジュール
├── mf_exporter.py       # MF仕訳CSV生成 + 仕訳履歴管理
├── config.json          # 設定ファイル
├── journal_history.json # 過去の仕訳マッピング履歴
├── requirements.txt     # 依存パッケージ
└── output/              # 生成されたCSVの出力先
```

## セットアップ

### 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. Google Drive API の設定

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成
2. Google Drive API を有効化
3. OAuth 2.0 クライアントIDを作成し、`credentials.json` をダウンロード
4. `credentials.json` を `invoice_import/` ディレクトリに配置
5. `config.json` の `watch_folder_id` に監視対象のGoogle DriveフォルダIDを設定

### 3. Gemini API の設定

```bash
export GEMINI_API_KEY=your_api_key_here
```

[Google AI Studio](https://aistudio.google.com/) からAPIキーを取得できます。

## 使い方

### Google Driveから取得して処理

```bash
python main.py
```

### ローカルファイルを直接処理

```bash
python main.py --local invoice1.pdf receipt.png
```

### 仕訳マッピングの管理

```bash
# 登録済みマッピング一覧
python main.py --list-mappings

# マッピングを手動追加
python main.py --add-mapping "取引先名" "勘定科目"
python main.py --add-mapping "取引先名" "勘定科目" "補助科目" "貸方科目" "税区分"
```

## 処理フロー

```
1. Google Driveの指定フォルダからファイルを取得（またはローカルファイル指定）
2. Gemini APIで画像/PDFから請求書情報を抽出（取引先、日付、金額など）
3. journal_history.json の過去仕訳と照合し、勘定科目を自動マッピング
4. MFクラウド会計のインポート用CSVを生成
5. 新しい取引先を仕訳履歴に自動追加（学習機能）
```

## 生成されるCSVの形式

MFクラウド会計の「仕訳帳」→「インポート」で取り込めるCSV形式です。

| 項目 | 説明 |
|------|------|
| 取引No | 連番 |
| 取引日 | YYYY/MM/DD |
| 借方勘定科目 | 過去仕訳から自動設定 |
| 借方補助科目 | 過去仕訳から自動設定 |
| 借方取引先 | 請求書から抽出 |
| 借方税区分 | 過去仕訳から自動設定 |
| 借方金額 | 請求書から抽出 |
| 貸方勘定科目 | 過去仕訳から自動設定 |
| 貸方金額 | 請求書から抽出 |
| 摘要 | 取引先名 + 品目 |
| メモ | 元ファイル名 |

## 仕訳マッピングの仕組み

`journal_history.json` に取引先ごとの仕訳パターンを保持しています。

- **完全一致** → そのまま適用
- **部分一致** → 取引先名に既存キーが含まれていれば適用
- **あいまい一致** → 類似度60%以上で最も近いものを適用
- **マッチなし** → デフォルト設定（雑費）を適用

処理後、新しい取引先は自動的に履歴に追加されます。
