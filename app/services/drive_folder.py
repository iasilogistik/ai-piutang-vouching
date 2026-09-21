from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse

import httpx

from app.config import settings
from app.services.bulk_zip import MemoryUpload, content_type_for


SUPPORTED_DRIVE_MIME_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
}
SUPPORTED_DRIVE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".zip"}
MAX_DRIVE_FOLDER_FILES = 200
MAX_DRIVE_FILE_BYTES = 75 * 1024 * 1024


@dataclass(frozen=True)
class DriveFolderFile:
    file_id: str
    name: str
    mime_type: str
    size: int | None = None


def extract_google_drive_folder_id(url: str) -> str | None:
    parsed = urlparse((url or "").strip())
    query_id = parse_qs(parsed.query).get("id", [None])[0]
    if query_id:
        return query_id
    match = re.search(r"/folders/([^/?#]+)", parsed.path)
    if match:
        return match.group(1)
    return None


def _require_api_key() -> str:
    api_key = settings.google_drive_api_key
    if not api_key:
        raise ValueError("GOOGLE_DRIVE_API_KEY is not configured. Set it in Vercel environment variables before importing Google Drive folders.")
    return api_key


def _safe_name(name: str, mime_type: str, fallback: str) -> str:
    filename = Path(name or "").name.strip() or fallback
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_DRIVE_EXTENSIONS:
        detected = SUPPORTED_DRIVE_MIME_TYPES.get(mime_type.lower())
        if detected:
            filename = f"{Path(filename).stem or fallback}{detected}"
    return filename


def is_supported_drive_folder_file(item: DriveFolderFile) -> bool:
    suffix = Path(item.name).suffix.lower()
    return item.mime_type.lower() in SUPPORTED_DRIVE_MIME_TYPES or suffix in SUPPORTED_DRIVE_EXTENSIONS


def list_google_drive_folder_files(folder_url: str) -> list[DriveFolderFile]:
    api_key = _require_api_key()
    folder_id = extract_google_drive_folder_id(folder_url)
    if not folder_id:
        raise ValueError("Unable to read Google Drive folder ID from the shared folder link")

    files: list[DriveFolderFile] = []
    page_token: str | None = None
    query = f"'{folder_id}' in parents and trashed=false"
    fields = "nextPageToken,files(id,name,mimeType,size)"
    with httpx.Client(timeout=90.0, follow_redirects=True) as client:
        while True:
            response = client.get(
                "https://www.googleapis.com/drive/v3/files",
                params={
                    "key": api_key,
                    "q": query,
                    "fields": fields,
                    "pageSize": 100,
                    "pageToken": page_token,
                    "supportsAllDrives": "true",
                    "includeItemsFromAllDrives": "true",
                },
            )
            if response.status_code != 200:
                raise ValueError(f"Unable to list Google Drive folder files ({response.status_code})")
            payload = response.json()
            for raw in payload.get("files", []):
                if len(files) >= MAX_DRIVE_FOLDER_FILES:
                    raise ValueError(f"Google Drive folder contains more than {MAX_DRIVE_FOLDER_FILES} files")
                size_raw = raw.get("size")
                size = int(size_raw) if size_raw is not None else None
                files.append(DriveFolderFile(
                    file_id=raw.get("id", ""),
                    name=raw.get("name", "untitled"),
                    mime_type=raw.get("mimeType", "application/octet-stream"),
                    size=size,
                ))
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
    if not files:
        raise ValueError("Google Drive folder does not contain visible files or the folder is not shared publicly")
    return files


def download_drive_folder_file(item: DriveFolderFile) -> MemoryUpload:
    api_key = _require_api_key()
    if item.size is not None and item.size > MAX_DRIVE_FILE_BYTES:
        raise ValueError(f"{item.name} is larger than the allowed 75 MB limit")
    if not is_supported_drive_folder_file(item):
        raise ValueError(f"{item.name} is not a supported PDF/JPG/PNG/ZIP document")

    with httpx.Client(timeout=90.0, follow_redirects=True) as client:
        response = client.get(
            f"https://www.googleapis.com/drive/v3/files/{item.file_id}",
            params={"alt": "media", "key": api_key, "supportsAllDrives": "true"},
        )
    if response.status_code != 200:
        raise ValueError(f"Unable to download {item.name} from Google Drive ({response.status_code})")
    if len(response.content) > MAX_DRIVE_FILE_BYTES:
        raise ValueError(f"{item.name} is larger than the allowed 75 MB limit")

    filename = _safe_name(item.name, item.mime_type, f"gdrive_{item.file_id}")
    return MemoryUpload(filename, response.content, content_type_for(filename))
