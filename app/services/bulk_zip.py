from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import zipfile

from fastapi import UploadFile
import rarfile


ALLOWED_ARCHIVE_EXTENSIONS = {".zip", ".rar"}
ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_BULK_FILES = 200
MAX_ARCHIVE_ENTRY_BYTES = 25 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 250 * 1024 * 1024


@dataclass(frozen=True)
class BulkZipEntry:
    source_path: str
    filename: str
    content: bytes
    content_type: str


class MemoryUpload:
    """Small UploadFile-compatible object for archive members."""

    def __init__(self, filename: str, content: bytes, content_type: str) -> None:
        self.filename = filename
        self.file = BytesIO(content)
        self.content_type = content_type


def content_type_for(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".zip":
        return "application/zip"
    if suffix == ".rar":
        return "application/vnd.rar"
    return "application/octet-stream"


def _append_entry(
    entries: list[BulkZipEntry],
    *,
    source_path: str,
    size: int,
    read_content,
    total_bytes: int,
) -> int:
    clean_name = Path(source_path).name
    if not clean_name or source_path.startswith("__MACOSX/"):
        return total_bytes
    if Path(clean_name).suffix.lower() not in ALLOWED_DOCUMENT_EXTENSIONS:
        return total_bytes
    if len(entries) >= MAX_BULK_FILES:
        raise ValueError(f"Archive contains more than {MAX_BULK_FILES} supported document files")
    if size > MAX_ARCHIVE_ENTRY_BYTES:
        raise ValueError(f"{clean_name} is larger than the allowed 25 MB extracted-file limit")
    if total_bytes + max(size, 0) > MAX_ARCHIVE_TOTAL_BYTES:
        raise ValueError("Archive expands beyond the allowed 250 MB safety limit")
    data = read_content()
    if not data:
        return total_bytes
    if len(data) > MAX_ARCHIVE_ENTRY_BYTES:
        raise ValueError(f"{clean_name} is larger than the allowed 25 MB extracted-file limit")
    total_bytes += len(data)
    if total_bytes > MAX_ARCHIVE_TOTAL_BYTES:
        raise ValueError("Archive expands beyond the allowed 250 MB safety limit")
    entries.append(
        BulkZipEntry(
            source_path=source_path,
            filename=clean_name,
            content=data,
            content_type=content_type_for(clean_name),
        )
    )
    return total_bytes


def _zip_entries(content: bytes) -> list[BulkZipEntry]:
    try:
        archive = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ValueError("Uploaded file is not a valid ZIP archive") from exc
    entries: list[BulkZipEntry] = []
    total_bytes = 0
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            total_bytes = _append_entry(
                entries,
                source_path=info.filename,
                size=int(info.file_size or 0),
                read_content=lambda info=info: archive.read(info),
                total_bytes=total_bytes,
            )
    return entries


def _rar_entries(content: bytes) -> list[BulkZipEntry]:
    try:
        archive = rarfile.RarFile(BytesIO(content))
    except rarfile.Error as exc:
        raise ValueError("Uploaded file is not a valid RAR archive") from exc
    entries: list[BulkZipEntry] = []
    total_bytes = 0
    try:
        with archive:
            for info in archive.infolist():
                if info.isdir():
                    continue
                total_bytes = _append_entry(
                    entries,
                    source_path=info.filename,
                    size=int(getattr(info, "file_size", 0) or 0),
                    read_content=lambda info=info: archive.read(info),
                    total_bytes=total_bytes,
                )
    except rarfile.RarCannotExec as exc:
        raise ValueError(
            "RAR archive was recognized, but the runtime RAR extractor is unavailable. "
            "Use ZIP or upload the individual files / Google Drive folder instead."
        ) from exc
    except rarfile.Error as exc:
        raise ValueError(f"Unable to extract RAR archive: {exc}") from exc
    return entries


def iter_bulk_archive_entries(upload: UploadFile) -> list[BulkZipEntry]:
    filename = Path(upload.filename or "documents.zip").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_ARCHIVE_EXTENSIONS:
        raise ValueError("Bulk upload file must be a ZIP or RAR archive")
    content = upload.file.read()
    if not content:
        raise ValueError("Uploaded archive is empty")
    entries = _zip_entries(content) if suffix == ".zip" else _rar_entries(content)
    if not entries:
        raise ValueError("Archive does not contain supported PDF/JPG/PNG document files")
    return entries


def iter_bulk_zip_entries(upload: UploadFile) -> list[BulkZipEntry]:
    """Backward-compatible name. Supports both ZIP and RAR."""
    return iter_bulk_archive_entries(upload)


def make_upload(entry: BulkZipEntry) -> MemoryUpload:
    return MemoryUpload(entry.filename, entry.content, entry.content_type)


def classify_entry(source_path: str, mode: str) -> list[str] | None:
    requested = mode.upper().strip()
    if requested not in {"AUTO", "BILLING", "SPJ", "COMBINED"}:
        raise ValueError("mode must be AUTO, BILLING, SPJ, or COMBINED")
    if requested == "BILLING":
        return ["BILLING"]
    if requested == "SPJ":
        return ["SPJ"]
    if requested == "COMBINED":
        return ["BILLING", "SPJ"]
    normalized = source_path.lower().replace("\\", "/")
    billing_markers = ("billing", "invoice", "faktur", "tagihan")
    spj_markers = ("spj", "surat jalan", "surat_jalan", "delivery", "do/")
    combined_markers = ("combined", "gabungan", "billing_spj", "billing+spj")
    if any(marker in normalized for marker in combined_markers):
        return ["BILLING", "SPJ"]
    billing = any(marker in normalized for marker in billing_markers)
    spj = any(marker in normalized for marker in spj_markers)
    if billing and spj:
        return ["BILLING", "SPJ"]
    if billing:
        return ["BILLING"]
    if spj:
        return ["SPJ"]
    return None
