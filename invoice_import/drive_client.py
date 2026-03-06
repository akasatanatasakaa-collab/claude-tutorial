"""
Google Drive連携モジュール
ファイルの取得・アップロード・移動をすべてDrive上で完結させる。

フォルダ構成（顧客ごと）:
  請求書/        ← 新しいファイルを置く場所（監視対象）
  処理済み/      ← 処理が終わったファイルの移動先
  MFインポート/  ← 生成CSVのアップロード先
  インポート済み/ ← MFに取り込んだ後のCSVの移動先
"""

import io
import os
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Google Drive APIのスコープ（読み書き可能）
SCOPES = ["https://www.googleapis.com/auth/drive"]


def authenticate(credentials_path: str, token_path: str):
    """Google Drive APIの認証を行い、サービスオブジェクトを返す"""
    creds = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


def get_or_create_subfolder(service, parent_id: str, folder_name: str) -> str:
    """親フォルダ内にサブフォルダを取得（なければ作成）してIDを返す"""
    query = (
        f"'{parent_id}' in parents and "
        f"name='{folder_name}' and "
        f"mimeType='application/vnd.google-apps.folder' and "
        f"trashed=false"
    )
    response = service.files().list(q=query, spaces="drive", fields="files(id)").execute()
    files = response.get("files", [])

    if files:
        return files[0]["id"]

    # フォルダを新規作成
    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    print(f"  フォルダを作成: {folder_name}")
    return folder["id"]


def list_files(service, folder_id: str, extensions: list[str]) -> list[dict]:
    """指定フォルダ内の対象ファイル一覧を取得する"""
    mime_map = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }

    mime_queries = []
    for ext in extensions:
        mime = mime_map.get(ext.lower())
        if mime:
            mime_queries.append(f"mimeType='{mime}'")

    mime_filter = " or ".join(mime_queries)
    query = f"'{folder_id}' in parents and ({mime_filter}) and trashed=false"

    results = []
    page_token = None

    while True:
        response = service.files().list(
            q=query,
            spaces="drive",
            fields="nextPageToken, files(id, name, mimeType, createdTime, modifiedTime)",
            pageToken=page_token,
            orderBy="createdTime desc",
        ).execute()

        results.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return results


def download_file(service, file_id: str, file_name: str, download_dir: str) -> str:
    """ファイルをダウンロードしてローカルパスを返す"""
    os.makedirs(download_dir, exist_ok=True)
    file_path = os.path.join(download_dir, file_name)

    request = service.files().get_media(fileId=file_id)
    with open(file_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

    return file_path


def move_file(service, file_id: str, dest_folder_id: str):
    """ファイルを別のフォルダに移動する"""
    # 現在の親フォルダを取得
    file_info = service.files().get(fileId=file_id, fields="parents").execute()
    current_parents = ",".join(file_info.get("parents", []))

    # 移動（親フォルダを付け替え）
    service.files().update(
        fileId=file_id,
        addParents=dest_folder_id,
        removeParents=current_parents,
        fields="id, parents",
    ).execute()


def upload_file(service, local_path: str, folder_id: str, file_name: str = None) -> str:
    """ローカルファイルをGoogle Driveにアップロードし、ファイルIDを返す"""
    if file_name is None:
        file_name = Path(local_path).name

    # MIMEタイプを判定
    suffix = Path(local_path).suffix.lower()
    mime_map = {
        ".csv": "text/csv",
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    mime_type = mime_map.get(suffix, "application/octet-stream")

    metadata = {
        "name": file_name,
        "parents": [folder_id],
    }
    media = MediaFileUpload(local_path, mimetype=mime_type)
    uploaded = service.files().create(
        body=metadata, media_body=media, fields="id"
    ).execute()

    return uploaded["id"]


def get_file_link(file_id: str) -> str:
    """DriveファイルのリンクURLを生成する"""
    return f"https://drive.google.com/file/d/{file_id}/view"


def rename_file(service, file_id: str, new_name: str):
    """Drive上のファイル名を変更する"""
    service.files().update(
        fileId=file_id,
        body={"name": new_name},
        fields="id, name",
    ).execute()


def fetch_invoices(config: dict, download_dir: str = "downloads") -> tuple[list[str], list[dict], object]:
    """ドライブからファイルを取得し、(ローカルパスのリスト, Driveファイル情報リスト, serviceオブジェクト)を返す"""
    drive_config = config["google_drive"]
    service = authenticate(
        drive_config["credentials_path"],
        drive_config["token_path"],
    )

    extensions = config.get("supported_extensions", [".pdf", ".png", ".jpg", ".jpeg"])
    watch_folder_id = drive_config["watch_folder_id"]
    files = list_files(service, watch_folder_id, extensions)

    if not files:
        print("新しいファイルが見つかりませんでした。")
        return [], [], service

    print(f"{len(files)}件のファイルが見つかりました:")
    downloaded = []
    for f in files:
        # DriveリンクをファイルIDから生成して付与
        f["webViewLink"] = get_file_link(f["id"])
        print(f"  - {f['name']} ({f['mimeType']})")
        path = download_file(service, f["id"], f["name"], download_dir)
        downloaded.append(path)

    return downloaded, files, service


def rename_for_denchoho(service, file_info: dict, invoice_data: dict):
    """電子帳簿保存法の検索要件に対応したファイル名にリネームする

    形式: YYYYMMDD_取引先名_金額円_元のファイル名.拡張子
    これにより日付・取引先・金額でファイル検索が可能になる
    """
    date_str = invoice_data.get("date", "").replace("/", "")
    vendor = invoice_data.get("vendor_name", "不明")
    amount = invoice_data.get("amount", 0)
    original_name = file_info["name"]
    suffix = Path(original_name).suffix

    # ファイル名に使えない文字を除去
    vendor_safe = vendor.replace("/", "／").replace("\\", "＼").replace(":", "：")

    new_name = f"{date_str}_{vendor_safe}_{amount}円_{original_name}"

    # Driveのファイル名が長すぎる場合は元ファイル名を省略
    if len(new_name) > 200:
        new_name = f"{date_str}_{vendor_safe}_{amount}円{suffix}"

    rename_file(service, file_info["id"], new_name)
    return new_name


def _get_year_month_folder(service, parent_folder_id: str, date_str: str) -> str:
    """日付文字列から年月フォルダを取得（なければ作成）する

    藤井氏・小澤氏の指摘: ファイル名だけでなく年月別フォルダで整理すべき。
    「処理済み/2026年03月/」のように年月でサブフォルダを切る。
    """
    # YYYY/MM/DD or YYYYMMDD から年月を抽出
    clean = date_str.replace("/", "")
    if len(clean) >= 6:
        year = clean[:4]
        month = clean[4:6]
        folder_name = f"{year}年{month}月"
    else:
        folder_name = "日付不明"

    return get_or_create_subfolder(service, parent_folder_id, folder_name)


def upload_csv_and_move_sources(service, config: dict, csv_path: str,
                                 source_files: list[dict],
                                 invoice_data_list: list[dict] | None = None):
    """CSVをDriveにアップロードし、処理済みファイルをリネーム＋年月フォルダに移動する"""
    watch_folder_id = config["google_drive"]["watch_folder_id"]

    # サブフォルダを取得または作成
    processed_folder_id = get_or_create_subfolder(service, watch_folder_id, "処理済み")
    import_folder_id = get_or_create_subfolder(service, watch_folder_id, "MFインポート")

    # CSVをアップロード
    csv_name = Path(csv_path).name
    csv_file_id = upload_file(service, csv_path, import_folder_id, csv_name)
    print(f"CSVをDriveにアップロード: {csv_name}")

    # 処理済みファイルを電帳法対応リネーム＋年月フォルダに移動
    for i, f in enumerate(source_files):
        date_str = ""
        if invoice_data_list and i < len(invoice_data_list):
            # 電帳法対応のファイル名にリネーム
            new_name = rename_for_denchoho(service, f, invoice_data_list[i])
            date_str = invoice_data_list[i].get("date", "")
            print(f"  リネーム: {f['name']} → {new_name}")

        # 年月サブフォルダに移動（例: 処理済み/2026年03月/）
        if date_str:
            dest_folder_id = _get_year_month_folder(service, processed_folder_id, date_str)
        else:
            dest_folder_id = processed_folder_id

        move_file(service, f["id"], dest_folder_id)
        print(f"  移動: → 処理済み/")

    return csv_file_id
