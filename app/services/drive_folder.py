from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from pathlib import Path
import re
import tempfile
from urllib.parse import parse_qs, urlparse

import gdown
import httpx

from app.config import settings
from app.services.bulk_zip import MemoryUpload, content_type_for


SUPPORTED_DRIVE_MIME_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
    "application/vnd.rar": ".rar",
    "application/x-rar-compressed": ".rar",
}
SUPPORTED_DRIVE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".zip", ".rar"}
MAX_DRIVE_FOLDER_FILES = 200
MAX_DRIVE_FILE_BYTES = 75 * 1024 * 1024
MAX_PUBLIC_FOLDER_DEPTH = 8
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0 Safari/537.36"
)
_ANCHOR_RE = re.compile(
    r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_FILE_PATTERNS = (
    re.compile(r"https://drive\.google\.com/file/d/([-\w]{10,})/view", re.IGNORECASE),
    re.compile(
        r"https://docs\.google\.com/(?:document|spreadsheets|presentation|drawings)/d/([-\w]{10,})",
        re.IGNORECASE,
    ),
)
_FOLDER_PATTERN = re.compile(
    r"https://drive\.google\.com/drive/folders/([-\w]{10,})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DriveFolderFile:
    file_id: str
    name: str
    mime_type: str
    size: int | None = None
    source: str = "API"


def extract_google_drive_folder_id(url: str) -> str | None:
    parsed = urlparse((url or "").strip())
    query_id = parse_qs(parsed.query).get("id", [None])[0]
    if query_id:
        return query_id
    match = re.search(r"/folders/([^/?#]+)", parsed.path)
    if match:
        return match.group(1)
    return None


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


def _list_with_drive_api(folder_url: str, api_key: str) -> list[DriveFolderFile]:
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
                raise ValueError(f"Drive API listing returned HTTP {response.status_code}")
            payload = response.json()
            for raw in payload.get("files", []):
                if len(files) >= MAX_DRIVE_FOLDER_FILES:
                    raise ValueError(f"Google Drive folder contains more than {MAX_DRIVE_FOLDER_FILES} files")
                size_raw = raw.get("size")
                size = int(size_raw) if size_raw is not None else None
                files.append(
                    DriveFolderFile(
                        file_id=raw.get("id", ""),
                        name=raw.get("name", "untitled"),
                        mime_type=raw.get("mimeType", "application/octet-stream"),
                        size=size,
                        source="API",
                    )
                )
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
    return files


def _clean_anchor_name(value: str, fallback: str) -> str:
    text = _TAG_RE.sub(" ", value or "")
    text = re.sub(r"\s+", " ", unescape(text)).strip()
    return text or fallback


def _parse_public_folder_html(
    html_text: str,
    *,
    prefix: str = "",
) -> tuple[list[DriveFolderFile], list[tuple[str, str]]]:
    files: list[DriveFolderFile] = []
    folders: list[tuple[str, str]] = []
    seen_files: set[str] = set()
    seen_folders: set[str] = set()

    for raw_href, raw_label in _ANCHOR_RE.findall(html_text or ""):
        href = unescape(raw_href)
        file_id = None
        for pattern in _FILE_PATTERNS:
            match = pattern.search(href)
            if match:
                file_id = match.group(1)
                break
        if file_id and file_id not in seen_files:
            seen_files.add(file_id)
            name = _clean_anchor_name(raw_label, f"gdrive_{file_id}")
            relative_name = f"{prefix}/{name}" if prefix else name
            files.append(
                DriveFolderFile(
                    file_id=file_id,
                    name=relative_name,
                    mime_type="application/octet-stream",
                    size=None,
                    source="PUBLIC",
                )
            )
            continue

        folder_match = _FOLDER_PATTERN.search(href)
        if folder_match:
            folder_id = folder_match.group(1)
            if folder_id in seen_folders:
                continue
            seen_folders.add(folder_id)
            folder_name = _clean_anchor_name(raw_label, folder_id)
            folders.append((folder_id, folder_name))

    return files, folders


def _list_public_folder_page(folder_url: str) -> list[DriveFolderFile]:
    root_id = extract_google_drive_folder_id(folder_url)
    if not root_id:
        raise ValueError("Unable to read Google Drive folder ID from the shared folder link")

    files: list[DriveFolderFile] = []
    visited: set[str] = set()

    with httpx.Client(
        timeout=90.0,
        follow_redirects=True,
        headers={"user-agent": _BROWSER_USER_AGENT, "accept-language": "en-US,en;q=0.9"},
    ) as client:

        def visit(folder_id: str, prefix: str, depth: int) -> None:
            if folder_id in visited:
                return
            if depth > MAX_PUBLIC_FOLDER_DEPTH:
                raise ValueError("Public Google Drive folder nesting is too deep")
            visited.add(folder_id)

            response = client.get(
                "https://drive.google.com/embeddedfolderview",
                params={"id": folder_id},
            )
            if response.status_code != 200:
                raise ValueError(f"embedded folder view returned HTTP {response.status_code}")
            page_files, child_folders = _parse_public_folder_html(response.text, prefix=prefix)

            for item in page_files:
                if len(files) >= MAX_DRIVE_FOLDER_FILES:
                    raise ValueError(f"Google Drive folder contains more than {MAX_DRIVE_FOLDER_FILES} files")
                files.append(item)

            for child_id, child_name in child_folders:
                child_prefix = f"{prefix}/{child_name}" if prefix else child_name
                visit(child_id, child_prefix, depth + 1)

        visit(root_id, "", 0)

    if not files:
        raise ValueError("embedded folder view returned no downloadable files")
    return files


def _list_public_folder_with_gdown(folder_url: str) -> list[DriveFolderFile]:
    last_error: Exception | None = None
    for use_cookies in (False, True):
        try:
            discovered = gdown.download_folder(
                url=folder_url,
                output=None,
                quiet=True,
                use_cookies=use_cookies,
                skip_download=True,
                user_agent=_BROWSER_USER_AGENT,
            )
        except Exception as exc:
            last_error = exc
            continue

        files: list[DriveFolderFile] = []
        for raw in discovered or []:
            if len(files) >= MAX_DRIVE_FOLDER_FILES:
                raise ValueError(f"Google Drive folder contains more than {MAX_DRIVE_FOLDER_FILES} files")
            file_id = str(getattr(raw, "id", "") or "")
            relative_path = str(getattr(raw, "path", "") or getattr(raw, "local_path", "") or "")
            if not file_id or not relative_path:
                continue
            files.append(
                DriveFolderFile(
                    file_id=file_id,
                    name=relative_path,
                    mime_type="application/octet-stream",
                    size=None,
                    source="PUBLIC",
                )
            )
        if files:
            return files

    detail = str(last_error or "no visible files")
    if len(detail) > 180:
        detail = detail[:177] + "..."
    raise ValueError(f"gdown folder discovery failed: {detail}")


def list_google_drive_folder_files(folder_url: str) -> list[DriveFolderFile]:
    if not extract_google_drive_folder_id(folder_url):
        raise ValueError("Unable to read Google Drive folder ID from the shared folder link")

    errors: list[str] = []
    api_key = (settings.google_drive_api_key or "").strip()

    if api_key:
        try:
            files = _list_with_drive_api(folder_url, api_key)
            if files:
                return files
            errors.append("Drive API: no visible files")
        except ValueError as exc:
            errors.append(f"Drive API: {exc}")

    try:
        return _list_public_folder_page(folder_url)
    except ValueError as exc:
        errors.append(f"public page: {exc}")

    try:
        return _list_public_folder_with_gdown(folder_url)
    except ValueError as exc:
        errors.append(f"gdown: {exc}")

    detail = " | ".join(errors[-3:])
    raise ValueError(
        "Google Drive folder could not be read. "
        "Make sure General access is 'Anyone with the link' and the files are visible. "
        f"Fallback detail: {detail}"
    )


def _download_public_file(item: DriveFolderFile) -> bytes:
    last_error: Exception | None = None
    for use_cookies in (False, True):
        with tempfile.TemporaryDirectory(prefix="drive-public-") as temp_dir:
            filename = _safe_name(item.name, item.mime_type, f"gdrive_{item.file_id}")
            output_path = str(Path(temp_dir) / filename)
            try:
                downloaded = gdown.download(
                    id=item.file_id,
                    output=output_path,
                    quiet=True,
                    use_cookies=use_cookies,
                    user_agent=_BROWSER_USER_AGENT,
                )
            except Exception as exc:
                last_error = exc
                continue
            if downloaded and Path(downloaded).is_file():
                return Path(downloaded).read_bytes()

    detail = str(last_error or "download did not return a file")
    if len(detail) > 160:
        detail = detail[:157] + "..."
    raise ValueError(f"Unable to download {item.name} from public Google Drive: {detail}")


def download_drive_folder_file(item: DriveFolderFile) -> MemoryUpload:
    if item.size is not None and item.size > MAX_DRIVE_FILE_BYTES:
        raise ValueError(f"{item.name} is larger than the allowed 75 MB limit")
    if not is_supported_drive_folder_file(item):
        raise ValueError(f"{item.name} is not a supported PDF/JPG/PNG/ZIP/RAR document")

    filename = _safe_name(item.name, item.mime_type, f"gdrive_{item.file_id}")

    if item.source == "PUBLIC":
        content = _download_public_file(item)
        if len(content) > MAX_DRIVE_FILE_BYTES:
            raise ValueError(f"{item.name} is larger than the allowed 75 MB limit")
        return MemoryUpload(filename, content, content_type_for(filename))

    api_key = (settings.google_drive_api_key or "").strip()
    if not api_key:
        content = _download_public_file(
            DriveFolderFile(
                item.file_id,
                item.name,
                item.mime_type,
                item.size,
                source="PUBLIC",
            )
        )
        if len(content) > MAX_DRIVE_FILE_BYTES:
            raise ValueError(f"{item.name} is larger than the allowed 75 MB limit")
        return MemoryUpload(filename, content, content_type_for(filename))

    with httpx.Client(timeout=90.0, follow_redirects=True) as client:
        response = client.get(
            f"https://www.googleapis.com/drive/v3/files/{item.file_id}",
            params={"alt": "media", "key": api_key, "supportsAllDrives": "true"},
        )
    if response.status_code != 200:
        raise ValueError(f"Unable to download {item.name} from Google Drive ({response.status_code})")
    if len(response.content) > MAX_DRIVE_FILE_BYTES:
        raise ValueError(f"{item.name} is larger than the allowed 75 MB limit")
    return MemoryUpload(filename, response.content, content_type_for(filename))
