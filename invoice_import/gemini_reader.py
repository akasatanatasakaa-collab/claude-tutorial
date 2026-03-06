"""
Gemini API 請求書・領収書読み取りモジュール
画像やPDFから請求書の情報を抽出する。
顧客固有のルール（暗黙知）をプロンプトに反映し、仕訳精度を高める。
"""

import json
import os
from pathlib import Path
import google.generativeai as genai


# Gemini APIに送る基本プロンプト
BASE_EXTRACTION_PROMPT = """
この画像/PDFは請求書または領収書です。以下の情報をJSON形式で抽出してください。

必ず以下の形式で返してください（JSONのみ、説明文は不要）:
{
    "vendor_name": "取引先名（会社名）",
    "date": "YYYY/MM/DD形式の日付",
    "amount": 税込合計金額（数値のみ）,
    "tax_amount": 消費税額（数値のみ、不明なら0）,
    "description": "品目・内容の要約",
    "invoice_number": "請求書番号（あれば）",
    "is_receipt": true/false（領収書ならtrue、請求書ならfalse）
}

注意:
- 金額はカンマなしの数値で返す
- 日付が和暦の場合は西暦に変換する
- 取引先名は正式名称を使う
- 複数品目がある場合はdescriptionにまとめる
"""


def build_prompt(client_rules: list[str] | None = None,
                 client_mappings: dict | None = None) -> str:
    """顧客固有のルールとマッピングを反映したプロンプトを構築する

    手島春樹氏（SoLabo）が指摘するように、仕訳は証憑だけでは決まらない。
    「なぜその勘定科目か」「なぜその税区分か」というコンテキストが必要。
    顧客ごとの暗黙知をプロンプトに注入することで、AIの判断精度を高める。
    """
    prompt = BASE_EXTRACTION_PROMPT

    # 顧客固有ルールがあればプロンプトに追加
    if client_rules:
        prompt += "\n\n## この顧客固有の注意事項（必ず従うこと）:\n"
        for i, rule in enumerate(client_rules, 1):
            prompt += f"{i}. {rule}\n"

    # 既知の取引先マッピングをコンテキストとして提供
    if client_mappings:
        prompt += "\n\n## この顧客で過去に使われた取引先と勘定科目の対応:\n"
        for vendor, mapping in list(client_mappings.items())[:20]:
            account = mapping.get("debit_account", "")
            sub = mapping.get("debit_sub_account", "")
            if sub:
                prompt += f"- {vendor} → {account}/{sub}\n"
            else:
                prompt += f"- {vendor} → {account}\n"
        prompt += "\n上記の取引先が含まれる場合、vendor_nameを正確に合わせてください。\n"

    return prompt


def configure_gemini(api_key: str, model_name: str = "gemini-2.0-flash"):
    """Gemini APIの設定を行う"""
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name)


def extract_invoice_data(model, file_path: str, prompt: str) -> dict:
    """ファイルから請求書データを抽出する"""
    path = Path(file_path)

    # ファイルをアップロード
    uploaded_file = genai.upload_file(file_path)

    # Geminiで解析
    response = model.generate_content([prompt, uploaded_file])
    response_text = response.text.strip()

    # JSONブロックの抽出（```json ... ``` で囲まれている場合の対応）
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        json_lines = [l for l in lines if not l.startswith("```")]
        response_text = "\n".join(json_lines)

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        print(f"警告: {path.name} のJSON解析に失敗しました。レスポンス:")
        print(response_text)
        data = {
            "vendor_name": "不明",
            "date": "",
            "amount": 0,
            "tax_amount": 0,
            "description": f"解析失敗: {path.name}",
            "invoice_number": "",
            "is_receipt": False,
        }

    # ソースファイル情報を追加
    data["source_file"] = path.name
    return data


def process_files(config: dict, file_paths: list[str],
                  client_rules: list[str] | None = None,
                  client_mappings: dict | None = None) -> list[dict]:
    """複数ファイルを処理して抽出データのリストを返す"""
    gemini_config = config["gemini"]
    api_key = os.environ.get(gemini_config["api_key_env"])

    if not api_key:
        raise ValueError(
            f"環境変数 {gemini_config['api_key_env']} が設定されていません。\n"
            f"export {gemini_config['api_key_env']}=your_api_key で設定してください。"
        )

    model = configure_gemini(api_key, gemini_config.get("model", "gemini-2.0-flash"))

    # 顧客のコンテキストを反映したプロンプトを構築
    prompt = build_prompt(client_rules, client_mappings)

    results = []
    for file_path in file_paths:
        print(f"解析中: {Path(file_path).name} ...")
        try:
            data = extract_invoice_data(model, file_path, prompt)
            results.append(data)
            print(f"  → {data['vendor_name']} / {data['date']} / ¥{data['amount']:,}")
        except Exception as e:
            print(f"  → エラー: {e}")
            results.append({
                "vendor_name": "不明",
                "date": "",
                "amount": 0,
                "tax_amount": 0,
                "description": f"処理エラー: {e}",
                "invoice_number": "",
                "is_receipt": False,
                "source_file": Path(file_path).name,
            })

    return results
