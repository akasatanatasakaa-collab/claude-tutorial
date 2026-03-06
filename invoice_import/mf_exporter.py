"""
MoneyForward クラウド会計 仕訳インポートCSV生成モジュール
抽出した請求書データを過去の仕訳履歴と照合し、MFインポート用CSVを出力する
"""

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from difflib import SequenceMatcher


def load_journal_history(history_path: str) -> dict:
    """過去の仕訳履歴を読み込む"""
    with open(history_path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_best_match(vendor_name: str, mappings: dict, threshold: float = 0.6) -> str | None:
    """取引先名のあいまい検索で最も近いマッピングキーを返す"""
    best_key = None
    best_score = 0.0

    for key in mappings:
        # 完全一致
        if vendor_name == key:
            return key
        # 部分一致（取引先名にキーが含まれる、またはその逆）
        if key in vendor_name or vendor_name in key:
            return key
        # あいまい一致
        score = SequenceMatcher(None, vendor_name.lower(), key.lower()).ratio()
        if score > best_score:
            best_score = score
            best_key = key

    if best_score >= threshold:
        return best_key
    return None


def map_to_journal(invoice_data: dict, history: dict) -> dict:
    """請求書データを過去の仕訳履歴に基づいて仕訳データにマッピングする"""
    vendor = invoice_data.get("vendor_name", "不明")
    mappings = history.get("mappings", {})
    default = history.get("default", {})

    # 取引先名で過去の仕訳を検索
    matched_key = find_best_match(vendor, mappings)

    if matched_key:
        mapping = mappings[matched_key]
        print(f"  マッチ: '{vendor}' → 既存マッピング '{matched_key}'")
    else:
        mapping = default
        print(f"  マッチなし: '{vendor}' → デフォルト勘定科目を使用")

    # 摘要の組み立て
    description = invoice_data.get("description", "")
    invoice_num = invoice_data.get("invoice_number", "")
    summary = f"{vendor} {description}"
    if invoice_num:
        summary += f" (No.{invoice_num})"

    return {
        "date": invoice_data.get("date", ""),
        "debit_account": mapping.get("debit_account", "雑費"),
        "debit_sub_account": mapping.get("debit_sub_account", ""),
        "credit_account": mapping.get("credit_account", "普通預金"),
        "credit_sub_account": mapping.get("credit_sub_account", ""),
        "amount": invoice_data.get("amount", 0),
        "tax_category": mapping.get("tax_category", "課税仕入 10%"),
        "summary": summary,
        "vendor": vendor,
        "source_file": invoice_data.get("source_file", ""),
        "drive_link": invoice_data.get("drive_link", ""),
    }


def _build_memo(journal: dict) -> str:
    """メモ列を構築する。Driveリンクがあれば含める"""
    parts = [f"元ファイル: {journal['source_file']}"]
    drive_link = journal.get("drive_link", "")
    if drive_link:
        parts.append(drive_link)
    return " | ".join(parts)


def generate_mf_csv(journals: list[dict], output_path: str, encoding: str = "utf-8") -> str:
    """MFクラウド会計インポート用CSVファイルを生成する"""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # MFクラウド会計の仕訳帳インポートCSVヘッダー
    # 参考: https://biz.moneyforward.com/support/account/guide/import-books/ib01.html
    headers = [
        "取引No",
        "取引日",
        "借方勘定科目",
        "借方補助科目",
        "借方部門",
        "借方取引先",
        "借方税区分",
        "借方インボイス",
        "借方金額(円)",
        "貸方勘定科目",
        "貸方補助科目",
        "貸方部門",
        "貸方取引先",
        "貸方税区分",
        "貸方インボイス",
        "貸方金額(円)",
        "摘要",
        "タグ",
        "MF仕訳タイプ",
        "メモ",
    ]

    with open(output_path, "w", newline="", encoding=encoding) as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for i, journal in enumerate(journals, start=1):
            row = [
                i,                                      # 取引No
                journal["date"],                        # 取引日
                journal["debit_account"],               # 借方勘定科目
                journal["debit_sub_account"],           # 借方補助科目
                "",                                     # 借方部門
                journal["vendor"],                      # 借方取引先
                journal["tax_category"],                # 借方税区分
                "",                                     # 借方インボイス
                journal["amount"],                      # 借方金額
                journal["credit_account"],              # 貸方勘定科目
                journal["credit_sub_account"],          # 貸方補助科目
                "",                                     # 貸方部門
                "",                                     # 貸方取引先
                journal["tax_category"],                # 貸方税区分
                "",                                     # 貸方インボイス
                journal["amount"],                      # 貸方金額
                journal["summary"],                     # 摘要
                "",                                     # タグ
                "",                                     # MF仕訳タイプ
                _build_memo(journal),                    # メモ
            ]
            writer.writerow(row)

    print(f"CSVファイルを出力しました: {output_path}")
    return output_path


def update_journal_history(history_path: str, journals: list[dict]):
    """新しい仕訳を履歴に追記する（学習機能）"""
    history = load_journal_history(history_path)
    mappings = history.get("mappings", {})

    updated = False
    for journal in journals:
        vendor = journal["vendor"]
        if vendor and vendor != "不明" and vendor not in mappings:
            mappings[vendor] = {
                "debit_account": journal["debit_account"],
                "debit_sub_account": journal["debit_sub_account"],
                "credit_account": journal["credit_account"],
                "credit_sub_account": journal["credit_sub_account"],
                "tax_category": journal["tax_category"],
                "memo": "",
            }
            print(f"  新規マッピング追加: '{vendor}'")
            updated = True

    if updated:
        history["mappings"] = mappings
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=4)
        print("仕訳履歴を更新しました。")
