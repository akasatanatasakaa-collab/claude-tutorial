"""
Google Drive連携モジュール
指定フォルダから請求書・領収書ファイルを取得し、ローカルにダウンロードする
"""

import io
import os
import json
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Google Drive APIのスコープ（読み取り専用）
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def authenticate(credentials_path: str, token_path: str):
    """Google Drive APIの認証を行い、サービスオブジェクトを返す"""
    creds = None

    # 既存のトークンがあれば読み込む
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # トークンが無効または期限切れの場合
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)

        # トークンを保存
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


def list_files(service, folder_id: str, extensions: list[str]) -> list[dict]:
    """指定フォルダ内の対象ファイル一覧を取得する"""
    # MIMEタイプでフィルタリング
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

    # クエリ構築: 指定フォルダ内 かつ 対象MIMEタイプ かつ ゴミ箱でない
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


def fetch_invoices(config: dict, download_dir: str = "downloads") -> list[str]:
    """設定に基づいてドライブからファイルを取得し、ダウンロードしたパスのリストを返す"""
    drive_config = config["google_drive"]
    service = authenticate(
        drive_config["credentials_path"],
        drive_config["token_path"],
    )

    extensions = config.get("supported_extensions", [".pdf", ".png", ".jpg", ".jpeg"])
    files = list_files(service, drive_config["watch_folder_id"], extensions)

    if not files:
        print("新しいファイルが見つかりませんでした。")
        return []

    print(f"{len(files)}件のファイルが見つかりました:")
    downloaded = []
    for f in files:
        print(f"  - {f['name']} ({f['mimeType']})")
        path = download_file(service, f["id"], f["name"], download_dir)
        downloaded.append(path)

    return downloaded
