from __future__ import annotations

from pathlib import Path
import tempfile

import httpx

from app.config import settings


def _object_url(storage_path: str) -> str:
    if not settings.supabase_url:
        raise ValueError("SUPABASE_URL is not configured")
    return f"{settings.supabase_url.rstrip('/')}/storage/v1/object/{settings.supabase_storage_bucket}/{storage_path}"


def _headers(content_type: str | None = None) -> dict[str, str]:
    if not settings.supabase_secret_key:
        raise ValueError("SUPABASE_SECRET_KEY is not configured")
    headers = {
        "Authorization": f"Bearer {settings.supabase_secret_key}",
        "apikey": settings.supabase_secret_key,
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def upload_bytes(storage_path: str, content: bytes, content_type: str) -> None:
    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            _object_url(storage_path),
            headers={**_headers(content_type), "x-upsert": "true"},
            content=content,
        )
    if response.status_code not in {200, 201}:
        raise ValueError(f"Unable to store document in Supabase Storage ({response.status_code})")


def download_bytes(storage_path: str) -> bytes:
    with httpx.Client(timeout=60.0) as client:
        response = client.get(_object_url(storage_path), headers=_headers())
    if response.status_code != 200:
        raise ValueError("Stored document file not found")
    return response.content


def materialize(storage_path: str, suffix: str) -> str:
    content = download_bytes(storage_path)
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        handle.write(content)
        return handle.name
    finally:
        handle.close()
