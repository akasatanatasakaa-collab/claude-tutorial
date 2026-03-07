"""
定期実行モジュール
全顧客のGoogle Driveフォルダを巡回し、新しい請求書を自動処理する。

使い方:
    # 全顧客を一括処理
    python scheduler.py

    # 特定の顧客のみ処理
    python scheduler.py --clients company_a company_b

    # cronで毎日9時に実行する例:
    # 0 9 * * * cd /path/to/invoice_import && python scheduler.py >> /var/log/invoice_import.log 2>&1

    # Google Cloud Schedulerから呼ぶ場合はCloud Functionsでラップする
"""

import argparse
import sys
import traceback
from datetime import datetime

from client_manager import list_clients, load_client_config


def run_all_clients(target_clients: list[str] | None = None):
    """全顧客（または指定顧客）のDriveフォルダを巡回処理する"""
    # mainモジュールから処理関数をインポート（循環インポート回避）
    from main import load_config, run_drive_mode

    config = load_config()
    clients = list_clients()

    if not clients:
        print("登録済みの顧客がありません。")
        return

    # 対象の絞り込み
    if target_clients:
        clients = [c for c in clients if c["client_id"] in target_clients]
        if not clients:
            print(f"指定された顧客が見つかりません: {target_clients}")
            return

    print(f"{'=' * 60}")
    print(f"定期実行開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"対象顧客: {len(clients)}件")
    print(f"{'=' * 60}")

    results = []
    for client_info in clients:
        client_id = client_info["client_id"]
        client_name = client_info["client_name"]

        print(f"\n{'─' * 40}")
        print(f"処理中: {client_name} ({client_id})")
        print(f"{'─' * 40}")

        try:
            client_config = load_client_config(client_id)
            drive_folder = client_config.get("google_drive", {}).get("watch_folder_id", "")

            if not drive_folder:
                print(f"  スキップ: DriveフォルダIDが未設定")
                results.append({
                    "client_id": client_id,
                    "client_name": client_name,
                    "status": "スキップ（フォルダ未設定）",
                })
                continue

            run_drive_mode(config, client_id)
            results.append({
                "client_id": client_id,
                "client_name": client_name,
                "status": "成功",
            })

        except Exception as e:
            print(f"  エラー: {e}")
            traceback.print_exc()
            results.append({
                "client_id": client_id,
                "client_name": client_name,
                "status": f"エラー: {e}",
            })

    # サマリー表示
    print(f"\n{'=' * 60}")
    print(f"定期実行完了: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")
    print(f"\n{'顧客名':<25} {'ステータス'}")
    print("-" * 50)
    for r in results:
        print(f"{r['client_name']:<25} {r['status']}")

    # エラーがあった場合は終了コード1を返す
    has_error = any("エラー" in r["status"] for r in results)
    return results, has_error


def main():
    parser = argparse.ArgumentParser(
        description="全顧客のDriveフォルダを巡回して請求書を自動処理する"
    )
    parser.add_argument(
        "--clients", nargs="+", metavar="ID",
        help="処理対象の顧客IDを指定（省略で全顧客）"
    )
    args = parser.parse_args()

    results, has_error = run_all_clients(args.clients)

    if has_error:
        sys.exit(1)


if __name__ == "__main__":
    main()
