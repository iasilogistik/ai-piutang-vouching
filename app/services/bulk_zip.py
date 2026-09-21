from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import zipfile

from fastapi import UploadFile


ALLOWED_ARCHIVE_EXTENSIONS = {".zip"}
ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_BULK_FILES = 200


@dataclass(frozen=True)
class BulkZipEntry:
    source_path: str
    filename: str
    content: bytes
    content_type: str


class MemoryUpload:
    """Small UploadFile-compatible object for ZIP members."""

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
    return "application/octet-stream"


def iter_bulk_zip_entries(upload: UploadFile) -> list[BulkZipEntry]:
    filename = Path(upload.filename or "documents.zip").name
    if Path(filename).suffix.lower() not in ALLOWED_ARCHIVE_EXTENSIONS:
        raise ValueError("Bulk upload file must be a ZIP archive")
    content = upload.file.read()
    if not content:
        raise ValueError("Uploaded ZIP archive is empty")

    try:
        archive = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ValueError("Uploaded file is not a valid ZIP archive") from exc

    entries: list[BulkZipEntry] = []
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            source_path = info.filename
            clean_name = Path(source_path).name
            if not clean_name or source_path.startswith("__MACOSX/"):
                continue
            suffix = Path(clean_name).suffix.lower()
            if suffix not in ALLOWED_DOCUMENT_EXTENSIONS:
                continue
            if len(entries) >= MAX_BULK_FILES:
                raise ValueError(f"ZIP archive contains more than {MAX_BULK_FILES} supported document files")
            data = archive.read(info)
            if not data:
                continue
            entries.append(BulkZipEntry(source_path=source_path, filename=clean_name, content=data,
                                        content_type=content_type_for(clean_name)))
    if not entries:
        raise ValueError("ZIP archive does not contain supported PDF/JPG/PNG document files")
    return entries


def make_upload(entry: BulkZipEntry) -> MemoryUpload:
    return MemoryUpload(entry.filename, entry.content, entry.content_type)


def classify_entry(source_path: str, mode: str) -> list[str] | None:
    """Return document types for a ZIP entry.

    Modes:
    - BILLING: every supported file is imported as Billing.
    - SPJ: every supported file is imported as SPJ.
    - COMBINED: every supported file is imported once as Billing and once as SPJ.
    - AUTO: classify using folder/file name. Unknown files are skipped to avoid
      silently creating wrong audit evidence.
    """
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
