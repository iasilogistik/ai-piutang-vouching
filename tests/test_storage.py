from app.config import settings
from app.services import storage


def test_storage_disabled_without_supabase(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", None)
    monkeypatch.setattr(settings, "supabase_secret_key", None)
    assert settings.use_supabase_storage is False


def test_supabase_storage_upload(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_secret_key", "secret")
    monkeypatch.setattr(settings, "supabase_storage_bucket", "audit-documents")
    captured = {}

    class Response:
        status_code = 200

    class Client:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, headers, content):
            captured.update(url=url, headers=headers, content=content)
            return Response()

    monkeypatch.setattr(storage.httpx, "Client", Client)
    storage.upload_bytes("BILLING/a.pdf", b"pdf", "application/pdf")
    assert "/storage/v1/object/audit-documents/BILLING/a.pdf" in captured["url"]
    assert captured["content"] == b"pdf"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["headers"]["x-upsert"] == "true"
