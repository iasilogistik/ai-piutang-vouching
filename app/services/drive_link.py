from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app.services.bulk_zip import MemoryUpload, content_type_for


ALLOWED_SHARE_LINK_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".zip"}
MAX_SHARE_LINK_BYTES = 75 * 1024 * 1024


def extract_google_drive_file_id(url: str) -> str | None:
    parsed = urlparse(url)
    query_id = parse_qs(parsed.query).get("id", [None])[0]
    if query_id:
        return query_id
    match = re.search(r"/file/d/([^/]+)", parsed.path)
    if match:
        return match.group(1)
    return None


def is_google_drive_folder_link(url: str) -> bool:
    parsed = urlparse(url)
    return "drive.google.com" in parsed.netloc.lower() and "/folders/" in parsed.path


def _filename_from_content_disposition(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"filename\*=UTF-8''([^;]+)", value, re.IGNORECASE)
    if match:
        return Path(unquote(match.group(1))).name
    match = re.search(r'filename="?([^";]+)"?', value, re.IGNORECASE)
    if match:
        return Path(match.group(1)).name
    return None


def _extension_from_content_type(content_type: str) -> str | None:
    value = content_type.split(";", 1)[0].strip().lower()
    return {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "application/zip": ".zip",
        "application/x-zip-compressed": ".zip",
    }.get(value)


def _safe_filename(name: str | None, fallback_stem: str, content_type: str) -> str:
    filename = Path(name or "").name.strip() or fallback_stem
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SHARE_LINK_EXTENSIONS:
        detected = _extension_from_content_type(content_type)
        if detected:
            filename = f"{Path(filename).stem or fallback_stem}{detected}"
    return filename


def _download(url: str) -> httpx.Response:
    with httpx.Client(timeout=90.0, follow_redirects=True) as client:
        response = client.get(url)
    if response.status_code != 200:
        raise ValueError(f"Unable to download shared document ({response.status_code})")
    if len(response.content) > MAX_SHARE_LINK_BYTES:
        raise ValueError("Shared document is larger than the allowed 75 MB limit")
    return response


def download_drive_link_file(url: str) -> MemoryUpload:
    """Download a public/shareable document link into an UploadFile-compatible object.

    Supports direct PDF/JPG/PNG/ZIP links and public Google Drive file links.
    Google Drive folder links require the Drive API/connector and are rejected
    instead of scraping folder HTML unreliably.
    """
    cleaned_url = (url or "").strip()
    if not cleaned_url:
        raise ValueError("Share link URL is required")
    parsed = urlparse(cleaned_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Share link must start with http or https")

    if is_google_drive_folder_link(cleaned_url):
        raise ValueError("Google Drive folder links require Google Drive API/connector. Zip the folder first or use a shared file link.")

    fallback_stem = "shared_document"
    download_url = cleaned_url
    if "drive.google.com" in parsed.netloc.lower():
        file_id = extract_google_drive_file_id(cleaned_url)
        if not file_id:
            raise ValueError("Unable to read Google Drive file ID from the shared link")
        fallback_stem = f"gdrive_{file_id}"
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    response = _download(download_url)
    content_type = response.headers.get("content-type", "application/octet-stream")
    if content_type.lower().startswith("text/html"):
        raise ValueError("Shared link did not return a downloadable document. Set permission to 'Anyone with the link' or upload a ZIP file.")

    filename = _safe_filename(
        _filename_from_content_disposition(response.headers.get("content-disposition")) or Path(parsed.path).name,
        fallback_stem,
        content_type,
    )
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SHARE_LINK_EXTENSIONS:
        raise ValueError("Shared document must be PDF, JPG, PNG, or ZIP")

    return MemoryUpload(filename, response.content, content_type_for(filename))
