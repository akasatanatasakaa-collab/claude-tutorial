"""
請求書・領収書 → MFクラウド会計インポートCSV変換システム

使い方:
    # Google Driveから取得して処理
    python main.py

    # ローカルファイルを直接指定して処理
    python main.py --local invoice1.pdf invoice2.png

    # 過去の仕訳マッピング一覧を表示
    python main.py --list-mappings

    # マッピングを手動追加
    python main.py --add-mapping "取引先名" "勘定科目"
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from drive_client import fetch_invoices
from gemini_reader import process_files
from mf_exporter import (
    generate_mf_csv,
    load_journal_history,
    map_to_journal,
    update_journal_history,
)

# 設定ファイルのパス
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
HISTORY_PATH = BASE_DIR / "journal_history.json"


def load_config() -> dict:
    """設定ファイルを読み込む"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def run_drive_mode(config: dict):
    """Google Driveモード: ドライブからファイルを取得して処理"""
    print("=== Google Driveからファイルを取得 ===")
    download_dir = str(BASE_DIR / "downloads")
    file_paths = fetch_invoices(config, download_dir)

    if not file_paths:
        print("処理するファイルがありません。")
        return

    run_processing(config, file_paths)


def run_local_mode(config: dict, file_paths: list[str]):
    """ローカルモード: 指定されたファイルを直接処理"""
    print("=== ローカルファイルを処理 ===")

    # ファイル存在チェック
    valid_paths = []
    for fp in file_paths:
        if os.path.exists(fp):
            valid_paths.append(fp)
        else:
            print(f"警告: ファイルが見つかりません: {fp}")

    if not valid_paths:
        print("処理するファイルがありません。")
        return

    run_processing(config, valid_paths)


def run_processing(config: dict, file_paths: list[str]):
    """ファイル処理の共通ロジック"""
    # 1. Gemini APIで請求書データを抽出
    print(f"\n=== {len(file_paths)}件のファイルを解析 ===")
    invoice_data_list = process_files(config, file_paths)

    # 2. 過去の仕訳履歴を読み込み
    print("\n=== 仕訳マッピング ===")
    history = load_journal_history(str(HISTORY_PATH))

    # 3. 抽出データを仕訳にマッピング
    journals = []
    for invoice_data in invoice_data_list:
        journal = map_to_journal(invoice_data, history)
        journals.append(journal)

    # 4. 結果のプレビュー表示
    print("\n=== 仕訳プレビュー ===")
    print("-" * 80)
    for j in journals:
        print(f"日付: {j['date']}")
        print(f"  借方: {j['debit_account']}/{j['debit_sub_account']} ¥{j['amount']:,}")
        print(f"  貸方: {j['credit_account']}/{j['credit_sub_account']} ¥{j['amount']:,}")
        print(f"  摘要: {j['summary']}")
        print(f"  元ファイル: {j['source_file']}")
        print("-" * 80)

    # 5. CSV出力
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = str(BASE_DIR / config["mf_export"]["output_dir"])
    output_path = os.path.join(output_dir, f"mf_import_{timestamp}.csv")
    encoding = config["mf_export"].get("encoding", "utf-8")

    generate_mf_csv(journals, output_path, encoding)

    # 6. 仕訳履歴を更新（学習）
    print("\n=== 仕訳履歴の更新 ===")
    update_journal_history(str(HISTORY_PATH), journals)

    print(f"\n完了！ CSVファイル: {output_path}")
    print("このファイルをMFクラウド会計の「仕訳帳」→「インポート」から取り込んでください。")


def list_mappings():
    """登録済みの仕訳マッピング一覧を表示"""
    history = load_journal_history(str(HISTORY_PATH))
    mappings = history.get("mappings", {})

    if not mappings:
        print("登録済みのマッピングはありません。")
        return

    print("=== 登録済み仕訳マッピング ===")
    print(f"{'取引先名':<25} {'借方科目':<15} {'補助科目':<15} {'税区分':<15}")
    print("-" * 70)
    for vendor, m in sorted(mappings.items()):
        print(
            f"{vendor:<25} {m['debit_account']:<15} "
            f"{m.get('debit_sub_account', ''):<15} {m['tax_category']:<15}"
        )


def add_mapping(vendor: str, debit_account: str, debit_sub: str = "",
                credit_account: str = "普通預金", tax_category: str = "課税仕入 10%"):
    """仕訳マッピングを手動追加する"""
    history = load_journal_history(str(HISTORY_PATH))
    mappings = history.get("mappings", {})

    mappings[vendor] = {
        "debit_account": debit_account,
        "debit_sub_account": debit_sub,
        "credit_account": credit_account,
        "credit_sub_account": "",
        "tax_category": tax_category,
        "memo": "",
    }

    history["mappings"] = mappings
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

    print(f"マッピングを追加しました: {vendor} → {debit_account}")


def main():
    parser = argparse.ArgumentParser(
        description="請求書・領収書 → MFクラウド会計インポートCSV変換"
    )
    parser.add_argument(
        "--local", nargs="+", metavar="FILE",
        help="ローカルファイルを直接指定して処理（Google Driveを使わない）"
    )
    parser.add_argument(
        "--list-mappings", action="store_true",
        help="登録済みの仕訳マッピング一覧を表示"
    )
    parser.add_argument(
        "--add-mapping", nargs="+", metavar="ARG",
        help="マッピングを追加: 取引先名 借方勘定科目 [借方補助科目] [貸方勘定科目] [税区分]"
    )

    args = parser.parse_args()

    # マッピング一覧表示
    if args.list_mappings:
        list_mappings()
        return

    # マッピング追加
    if args.add_mapping:
        if len(args.add_mapping) < 2:
            print("エラー: 取引先名と借方勘定科目は必須です。")
            print("使い方: --add-mapping 取引先名 借方勘定科目 [借方補助科目] [貸方勘定科目] [税区分]")
            sys.exit(1)
        add_mapping(*args.add_mapping[:5])
        return

    config = load_config()

    # ローカルモードまたはDriveモード
    if args.local:
        run_local_mode(config, args.local)
    else:
        run_drive_mode(config)


if __name__ == "__main__":
    main()
