"""
顧客管理モジュール
会計事務所が複数の顧客を管理するための機能を提供する。
顧客ごとに仕訳履歴・設定・出力先を分離して管理する。
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
CLIENTS_DIR = BASE_DIR / "clients"

# 顧客初期設定のテンプレート
CLIENT_CONFIG_TEMPLATE = {
    "client_name": "",
    "google_drive": {
        "watch_folder_id": "",
        "processed_folder_id": "",
    },
    "mf_export": {
        "encoding": "utf-8",
    },
    "notes": "",
}

# 顧客別の仕訳履歴テンプレート
JOURNAL_HISTORY_TEMPLATE = {
    "description": "この顧客の仕訳マッピング履歴",
    "rules": [],
    "mappings": {},
    "default": {
        "debit_account": "雑費",
        "debit_sub_account": "",
        "credit_account": "普通預金",
        "credit_sub_account": "",
        "tax_category": "課税仕入 10%",
        "memo": "",
    },
}


def get_client_dir(client_id: str) -> Path:
    """顧客ディレクトリのパスを返す"""
    return CLIENTS_DIR / client_id


def list_clients() -> list[dict]:
    """登録済み顧客一覧を返す"""
    if not CLIENTS_DIR.exists():
        return []

    clients = []
    for d in sorted(CLIENTS_DIR.iterdir()):
        if not d.is_dir():
            continue
        config_path = d / "client_config.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            # マッピング数を取得
            history_path = d / "journal_history.json"
            mapping_count = 0
            if history_path.exists():
                with open(history_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
                mapping_count = len(history.get("mappings", {}))

            clients.append({
                "client_id": d.name,
                "client_name": config.get("client_name", d.name),
                "drive_folder": config.get("google_drive", {}).get("watch_folder_id", "未設定"),
                "mapping_count": mapping_count,
                "notes": config.get("notes", ""),
            })
    return clients


def create_client(client_id: str, client_name: str, drive_folder_id: str = "",
                  notes: str = "") -> Path:
    """新規顧客を作成する"""
    client_dir = get_client_dir(client_id)

    if client_dir.exists():
        raise ValueError(f"顧客ID '{client_id}' は既に存在します。")

    # ディレクトリ作成
    client_dir.mkdir(parents=True, exist_ok=True)
    (client_dir / "output").mkdir(exist_ok=True)

    # 顧客設定ファイル
    config = CLIENT_CONFIG_TEMPLATE.copy()
    config["client_name"] = client_name
    config["google_drive"] = {
        "watch_folder_id": drive_folder_id,
        "processed_folder_id": "",
    }
    config["notes"] = notes

    with open(client_dir / "client_config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

    # 仕訳履歴ファイル（空のテンプレート）
    history = JOURNAL_HISTORY_TEMPLATE.copy()
    history["description"] = f"{client_name}の仕訳マッピング履歴"

    with open(client_dir / "journal_history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

    print(f"顧客を作成しました: {client_name} (ID: {client_id})")
    print(f"  ディレクトリ: {client_dir}")
    return client_dir


def load_client_config(client_id: str) -> dict:
    """顧客設定を読み込む"""
    client_dir = get_client_dir(client_id)
    config_path = client_dir / "client_config.json"

    if not config_path.exists():
        raise FileNotFoundError(
            f"顧客 '{client_id}' が見つかりません。\n"
            f"'python main.py --list-clients' で一覧を確認してください。"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_client_history_path(client_id: str) -> str:
    """顧客の仕訳履歴ファイルのパスを返す"""
    return str(get_client_dir(client_id) / "journal_history.json")


def get_client_output_dir(client_id: str) -> str:
    """顧客のCSV出力先ディレクトリを返す"""
    output_dir = get_client_dir(client_id) / "output"
    output_dir.mkdir(exist_ok=True)
    return str(output_dir)


def build_client_drive_config(global_config: dict, client_config: dict) -> dict:
    """グローバル設定と顧客設定をマージしてDrive用設定を生成する"""
    merged = global_config.copy()

    # 顧客固有のDriveフォルダIDで上書き
    client_drive = client_config.get("google_drive", {})
    if client_drive.get("watch_folder_id"):
        merged["google_drive"]["watch_folder_id"] = client_drive["watch_folder_id"]
    if client_drive.get("processed_folder_id"):
        merged["google_drive"]["processed_folder_id"] = client_drive["processed_folder_id"]

    return merged


def add_client_rule(client_id: str, rule: str):
    """顧客固有の仕訳ルール（暗黙知）を追加する"""
    history_path = get_client_history_path(client_id)

    with open(history_path, "r", encoding="utf-8") as f:
        history = json.load(f)

    if "rules" not in history:
        history["rules"] = []

    history["rules"].append(rule)

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

    print(f"ルールを追加しました: {rule}")


def get_client_rules(client_id: str) -> list[str]:
    """顧客固有の仕訳ルール一覧を返す"""
    history_path = get_client_history_path(client_id)

    with open(history_path, "r", encoding="utf-8") as f:
        history = json.load(f)

    return history.get("rules", [])


def get_processing_log_path(client_id: str) -> str:
    """顧客の処理ログファイルのパスを返す"""
    return str(get_client_dir(client_id) / "processing_log.json")


def load_processing_log(client_id: str) -> list[dict]:
    """処理ログを読み込む"""
    log_path = get_processing_log_path(client_id)
    if not os.path.exists(log_path):
        return []
    with open(log_path, "r", encoding="utf-8") as f:
        return json.load(f)


def append_processing_log(client_id: str, source_files: list[str],
                          csv_file: str, journals: list[dict]):
    """処理ログに記録を追加する（重複処理の検知・監査証跡用）"""
    log_path = get_processing_log_path(client_id)
    log = load_processing_log(client_id)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "source_files": source_files,
        "output_csv": csv_file,
        "journal_count": len(journals),
        "total_amount": sum(j.get("amount", 0) for j in journals),
        "vendors": [j.get("vendor", "") for j in journals],
    }
    log.append(entry)

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=4)


def check_duplicate_files(client_id: str, file_names: list[str]) -> list[str]:
    """処理ログから重複ファイルを検出する"""
    log = load_processing_log(client_id)
    processed_files = set()
    for entry in log:
        for f in entry.get("source_files", []):
            processed_files.add(f)

    duplicates = [f for f in file_names if f in processed_files]
    return duplicates
