from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.services import drive_folder
from app.services.drive_folder import (
    DriveFolderFile,
    download_drive_folder_file,
    extract_google_drive_folder_id,
    is_supported_drive_folder_file,
    list_google_drive_folder_files,
)


client = TestClient(app)


def test_extract_google_drive_folder_id_from_standard_link():
    url = "https://drive.google.com/drive/folders/1AbCDefGhIJklMNop?usp=sharing"
    assert extract_google_drive_folder_id(url) == "1AbCDefGhIJklMNop"


def test_extract_google_drive_folder_id_from_query_id():
    url = "https://drive.google.com/open?id=1FolderQueryId"
    assert extract_google_drive_folder_id(url) == "1FolderQueryId"


def test_supported_drive_folder_file_detection():
    assert is_supported_drive_folder_file(DriveFolderFile("1", "dokumen.pdf", "application/pdf"))
    assert is_supported_drive_folder_file(DriveFolderFile("2", "foto-stempel.jpg", "application/octet-stream"))
    assert is_supported_drive_folder_file(DriveFolderFile("4", "evidence.rar", "application/vnd.rar"))
    assert not is_supported_drive_folder_file(DriveFolderFile("3", "catatan.txt", "text/plain"))


def test_drive_import_ui_includes_folder_endpoint():
    response = client.get("/ui/drive-import")

    assert response.status_code == 200
    assert "Import Folder Link" in response.text
    assert "/documents/drive-folder-import" in response.text
    assert "Anyone with the link" in response.text
    assert "tanpa API key" in response.text


def test_drive_folder_import_endpoint_order_not_caught_by_document_type_route():
    response = client.post(
        "/documents/drive-folder-import",
        data={"url": "https://drive.google.com/drive/folders/abc"},
    )

    assert response.status_code in {400, 401}
    assert "document_type must be BILLING or SPJ" not in response.text


def test_public_folder_fallback_does_not_require_api_key(monkeypatch):
    monkeypatch.setattr(drive_folder.settings, "google_drive_api_key", None)
    monkeypatch.setattr(
        drive_folder.gdown,
        "download_folder",
        lambda **kwargs: [
            SimpleNamespace(id="file1", path="BILLING/invoice.pdf", local_path="/tmp/invoice.pdf"),
            SimpleNamespace(id="file2", path="SPJ/surat-jalan.jpg", local_path="/tmp/surat-jalan.jpg"),
        ],
    )

    rows = list_google_drive_folder_files(
        "https://drive.google.com/drive/folders/public123?usp=sharing"
    )

    assert [row.file_id for row in rows] == ["file1", "file2"]
    assert all(row.source == "PUBLIC" for row in rows)
    assert rows[0].name == "BILLING/invoice.pdf"


def test_public_folder_file_download_uses_gdown_without_api_key(monkeypatch):
    monkeypatch.setattr(drive_folder.settings, "google_drive_api_key", None)

    def fake_download(*, id, output, **kwargs):
        Path(output).write_bytes(b"%PDF-public-evidence")
        return output

    monkeypatch.setattr(drive_folder.gdown, "download", fake_download)
    item = DriveFolderFile(
        "file1",
        "BILLING/invoice.pdf",
        "application/octet-stream",
        source="PUBLIC",
    )

    upload = download_drive_folder_file(item)

    assert upload.filename == "invoice.pdf"
    assert upload.file.read() == b"%PDF-public-evidence"
