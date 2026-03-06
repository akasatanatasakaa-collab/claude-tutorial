"""
請求書・領収書 → MFクラウド会計インポートCSV変換システム（会計事務所向け・Google Drive完結）

使い方:
    # 顧客一覧を表示
    python main.py --list-clients

    # 新規顧客を登録
    python main.py --create-client company_a --name "株式会社A" --drive-folder "GoogleDriveのフォルダID"

    # 顧客を指定してGoogle Driveから処理（CSV生成→Driveアップロード→処理済み移動）
    python main.py --client company_a

    # 顧客を指定してローカルファイルを処理
    python main.py --client company_a --local invoice1.pdf invoice2.png

    # 顧客の仕訳マッピング一覧を表示
    python main.py --client company_a --list-mappings

    # 顧客のマッピングを手動追加
    python main.py --client company_a --add-mapping "取引先名" "勘定科目"

    # 顧客固有のルール（暗黙知）を追加
    python main.py --client company_a --add-rule "交際費は5,000円以下でも全て交際費で処理（会議費は使わない）"

    # 顧客のルール一覧を表示
    python main.py --client company_a --list-rules

    # 処理ログを表示
    python main.py --client company_a --show-log
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from client_manager import (
    add_client_rule,
    append_processing_log,
    build_client_drive_config,
    check_duplicate_files,
    create_client,
    get_client_history_path,
    get_client_output_dir,
    get_client_rules,
    list_clients,
    load_client_config,
    load_processing_log,
)
from drive_client import fetch_invoices, upload_csv_and_move_sources
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


def load_config() -> dict:
    """グローバル設定ファイルを読み込む"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def run_drive_mode(config: dict, client_id: str):
    """Google Driveモード: Drive上で入力→処理→出力を完結させる"""
    client_config = load_client_config(client_id)
    client_name = client_config.get("client_name", client_id)

    print(f"=== [{client_name}] Google Driveからファイルを取得 ===")

    # グローバル設定に顧客のDriveフォルダ設定をマージ
    merged_config = build_client_drive_config(config, client_config)

    download_dir = str(BASE_DIR / "downloads" / client_id)
    file_paths, drive_files, service = fetch_invoices(merged_config, download_dir)

    if not file_paths:
        print("処理するファイルがありません。")
        return

    # 重複チェック
    file_names = [Path(fp).name for fp in file_paths]
    duplicates = check_duplicate_files(client_id, file_names)
    if duplicates:
        print(f"\n⚠ 以下のファイルは過去に処理済みです:")
        for d in duplicates:
            print(f"  - {d}")
        print("スキップして続行します。")
        # 重複ファイルを除外
        filtered = [(fp, df) for fp, df in zip(file_paths, drive_files)
                     if Path(fp).name not in duplicates]
        if not filtered:
            print("新しいファイルがありません。")
            return
        file_paths, drive_files = zip(*filtered)
        file_paths = list(file_paths)
        drive_files = list(drive_files)

    # Driveファイルのリンクをファイルパスと紐づけるマップを作成
    drive_link_map = {}
    for fp, df in zip(file_paths, drive_files):
        drive_link_map[Path(fp).name] = df.get("webViewLink", "")

    # 処理実行
    csv_path, journals, invoice_data_list = run_processing(
        config, client_id, file_paths, drive_link_map=drive_link_map
    )

    if csv_path and journals:
        # CSVをDriveにアップロード & 処理済みファイルをリネーム+移動
        print("\n=== Google Driveに反映 ===")
        upload_csv_and_move_sources(
            service, merged_config, csv_path, drive_files,
            invoice_data_list=invoice_data_list,
        )

        # 処理ログに記録
        source_names = [Path(fp).name for fp in file_paths]
        append_processing_log(client_id, source_names, Path(csv_path).name, journals)

        print(f"\n完了！")
        print(f"  CSVファイル → Drive「MFインポート/」フォルダにアップロード済み")
        print(f"  処理済み請求書 → Drive「処理済み/」フォルダに移動済み")
        print(f"MFクラウド会計の「仕訳帳」→「インポート」からDrive上のCSVを取り込んでください。")


def run_local_mode(config: dict, client_id: str, file_paths: list[str]):
    """ローカルモード: 指定されたファイルを直接処理"""
    client_config = load_client_config(client_id)
    client_name = client_config.get("client_name", client_id)

    print(f"=== [{client_name}] ローカルファイルを処理 ===")

    valid_paths = []
    for fp in file_paths:
        if os.path.exists(fp):
            valid_paths.append(fp)
        else:
            print(f"警告: ファイルが見つかりません: {fp}")

    if not valid_paths:
        print("処理するファイルがありません。")
        return

    csv_path, journals, _ = run_processing(config, client_id, valid_paths)

    if csv_path and journals:
        # ローカルモードでも処理ログに記録
        source_names = [Path(fp).name for fp in valid_paths]
        append_processing_log(client_id, source_names, Path(csv_path).name, journals)

        print(f"\n完了！ CSVファイル: {csv_path}")
        print("このファイルをMFクラウド会計の「仕訳帳」→「インポート」から取り込んでください。")


def run_processing(config: dict, client_id: str,
                   file_paths: list[str],
                   drive_link_map: dict | None = None) -> tuple[str | None, list[dict] | None, list[dict] | None]:
    """ファイル処理の共通ロジック（顧客別）。(CSVパス, 仕訳リスト, 請求書データリスト)を返す"""
    history_path = get_client_history_path(client_id)
    output_dir = get_client_output_dir(client_id)

    # 顧客固有のルールとマッピングを取得
    client_rules = get_client_rules(client_id)
    history = load_journal_history(history_path)
    client_mappings = history.get("mappings", {})

    if client_rules:
        print(f"\n適用ルール: {len(client_rules)}件")
        for rule in client_rules:
            print(f"  - {rule}")

    # 1. Gemini APIで請求書データを抽出（顧客のコンテキスト付き）
    print(f"\n=== {len(file_paths)}件のファイルを解析 ===")
    invoice_data_list = process_files(
        config, file_paths,
        client_rules=client_rules,
        client_mappings=client_mappings,
    )

    # DriveリンクをGemini抽出結果に紐づける
    if drive_link_map:
        for data in invoice_data_list:
            source = data.get("source_file", "")
            if source in drive_link_map:
                data["drive_link"] = drive_link_map[source]

    # 2. 抽出データを仕訳にマッピング
    print("\n=== 仕訳マッピング ===")
    journals = []
    for invoice_data in invoice_data_list:
        journal = map_to_journal(invoice_data, history)
        journals.append(journal)

    # 3. 結果のプレビュー表示
    print("\n=== 仕訳プレビュー ===")
    print("-" * 80)
    for j in journals:
        print(f"日付: {j['date']}")
        print(f"  借方: {j['debit_account']}/{j['debit_sub_account']} ¥{j['amount']:,}")
        print(f"  貸方: {j['credit_account']}/{j['credit_sub_account']} ¥{j['amount']:,}")
        print(f"  摘要: {j['summary']}")
        print(f"  元ファイル: {j['source_file']}")
        print("-" * 80)

    # 4. CSV出力（顧客別ディレクトリ）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"mf_import_{timestamp}.csv")
    encoding = config["mf_export"].get("encoding", "utf-8")

    generate_mf_csv(journals, output_path, encoding)

    # 5. 仕訳履歴を更新（顧客別に学習）
    print("\n=== 仕訳履歴の更新 ===")
    update_journal_history(history_path, journals)

    return output_path, journals, invoice_data_list


def show_client_list():
    """顧客一覧を表示"""
    clients = list_clients()

    if not clients:
        print("登録済みの顧客はありません。")
        print("'python main.py --create-client ID --name 名前' で顧客を登録してください。")
        return

    print("=== 登録済み顧客一覧 ===")
    print(f"{'ID':<20} {'顧客名':<25} {'マッピング数':<10} {'メモ'}")
    print("-" * 75)
    for c in clients:
        print(f"{c['client_id']:<20} {c['client_name']:<25} {c['mapping_count']:<10} {c['notes']}")


def show_mappings(client_id: str):
    """顧客の仕訳マッピング一覧を表示"""
    client_config = load_client_config(client_id)
    history_path = get_client_history_path(client_id)
    history = load_journal_history(history_path)
    mappings = history.get("mappings", {})

    client_name = client_config.get("client_name", client_id)
    print(f"=== [{client_name}] 仕訳マッピング一覧 ===")

    if not mappings:
        print("登録済みのマッピングはありません。")
        return

    print(f"{'取引先名':<25} {'借方科目':<15} {'補助科目':<15} {'税区分':<15}")
    print("-" * 70)
    for vendor, m in sorted(mappings.items()):
        print(
            f"{vendor:<25} {m['debit_account']:<15} "
            f"{m.get('debit_sub_account', ''):<15} {m['tax_category']:<15}"
        )


def add_mapping(client_id: str, vendor: str, debit_account: str, debit_sub: str = "",
                credit_account: str = "普通預金", tax_category: str = "課税仕入 10%"):
    """顧客の仕訳マッピングを手動追加する"""
    history_path = get_client_history_path(client_id)
    history = load_journal_history(history_path)
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
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

    client_config = load_client_config(client_id)
    client_name = client_config.get("client_name", client_id)
    print(f"[{client_name}] マッピングを追加: {vendor} → {debit_account}")


def show_rules(client_id: str):
    """顧客のルール一覧を表示"""
    client_config = load_client_config(client_id)
    client_name = client_config.get("client_name", client_id)
    rules = get_client_rules(client_id)

    print(f"=== [{client_name}] 仕訳ルール（暗黙知）一覧 ===")

    if not rules:
        print("登録済みのルールはありません。")
        print(f"'python main.py --client {client_id} --add-rule \"ルール内容\"' で追加できます。")
        return

    for i, rule in enumerate(rules, 1):
        print(f"  {i}. {rule}")


def show_processing_log(client_id: str):
    """処理ログを表示"""
    client_config = load_client_config(client_id)
    client_name = client_config.get("client_name", client_id)
    log = load_processing_log(client_id)

    print(f"=== [{client_name}] 処理ログ ===")

    if not log:
        print("処理履歴はありません。")
        return

    for entry in log:
        ts = entry.get("timestamp", "不明")
        csv_file = entry.get("output_csv", "不明")
        count = entry.get("journal_count", 0)
        total = entry.get("total_amount", 0)
        sources = entry.get("source_files", [])

        print(f"\n日時: {ts}")
        print(f"  出力CSV: {csv_file}")
        print(f"  仕訳数: {count}件 / 合計: ¥{total:,}")
        print(f"  元ファイル:")
        for s in sources:
            print(f"    - {s}")


def main():
    parser = argparse.ArgumentParser(
        description="請求書・領収書 → MFクラウド会計インポートCSV変換（会計事務所向け）"
    )

    # 顧客管理
    parser.add_argument("--client", metavar="ID", help="処理対象の顧客ID")
    parser.add_argument("--list-clients", action="store_true", help="登録済み顧客一覧を表示")
    parser.add_argument("--create-client", metavar="ID", help="新規顧客を作成")
    parser.add_argument("--name", metavar="NAME", help="顧客名（--create-clientと併用）")
    parser.add_argument("--drive-folder", metavar="FOLDER_ID", help="DriveフォルダID（--create-clientと併用）")

    # 処理モード
    parser.add_argument("--local", nargs="+", metavar="FILE", help="ローカルファイルを直接指定して処理")

    # マッピング管理
    parser.add_argument("--list-mappings", action="store_true", help="仕訳マッピング一覧を表示")
    parser.add_argument("--add-mapping", nargs="+", metavar="ARG", help="マッピングを追加")

    # ルール管理（暗黙知の形式知化）
    parser.add_argument("--add-rule", metavar="RULE", help="顧客固有の仕訳ルールを追加")
    parser.add_argument("--list-rules", action="store_true", help="仕訳ルール一覧を表示")

    # 処理ログ
    parser.add_argument("--show-log", action="store_true", help="処理ログを表示")

    args = parser.parse_args()

    # --- 顧客一覧表示 ---
    if args.list_clients:
        show_client_list()
        return

    # --- 顧客作成 ---
    if args.create_client:
        name = args.name or args.create_client
        drive_folder = args.drive_folder or ""
        create_client(args.create_client, name, drive_folder)
        return

    # --- 以降は --client が必須 ---
    if not args.client:
        print("エラー: --client で顧客IDを指定してください。")
        print()
        show_client_list()
        print()
        print("使い方の例:")
        print("  python main.py --client company_a                    # Driveから処理")
        print("  python main.py --client company_a --local file.pdf   # ローカルファイル処理")
        print("  python main.py --client company_a --list-mappings    # マッピング確認")
        print("  python main.py --client company_a --add-rule \"ルール\" # 暗黙知を追加")
        print("  python main.py --client company_a --show-log         # 処理ログ確認")
        sys.exit(1)

    client_id = args.client

    # --- ルール一覧 ---
    if args.list_rules:
        show_rules(client_id)
        return

    # --- ルール追加 ---
    if args.add_rule:
        add_client_rule(client_id, args.add_rule)
        return

    # --- マッピング一覧 ---
    if args.list_mappings:
        show_mappings(client_id)
        return

    # --- マッピング追加 ---
    if args.add_mapping:
        if len(args.add_mapping) < 2:
            print("エラー: 取引先名と借方勘定科目は必須です。")
            sys.exit(1)
        add_mapping(client_id, *args.add_mapping[:5])
        return

    # --- 処理ログ ---
    if args.show_log:
        show_processing_log(client_id)
        return

    # --- メイン処理 ---
    config = load_config()

    if args.local:
        run_local_mode(config, client_id, args.local)
    else:
        run_drive_mode(config, client_id)


if __name__ == "__main__":
    main()
