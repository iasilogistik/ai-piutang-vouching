from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.services import drive_folder
from app.services.drive_folder import (
    DriveFolderFile,
    _parse_public_folder_html,
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
        drive_folder,
        "_list_public_folder_page",
        lambda url: (_ for _ in ()).throw(ValueError("embedded view blocked")),
    )
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


def test_public_embedded_folder_page_parser_discovers_files_and_subfolders():
    html = """
    <html><body>
      <a href="https://drive.google.com/file/d/1AAAAAAAAAAAAAAAAAAAAAAAAA/view">invoice-01.pdf</a>
      <a href="https://drive.google.com/drive/folders/1BBBBBBBBBBBBBBBBBBBBBBBBB">SPJ</a>
    </body></html>
    """

    files, folders = _parse_public_folder_html(html, prefix="BILLING")

    assert len(files) == 1
    assert files[0].file_id == "1AAAAAAAAAAAAAAAAAAAAAAAAA"
    assert files[0].name == "BILLING/invoice-01.pdf"
    assert files[0].source == "PUBLIC"
    assert folders == [("1BBBBBBBBBBBBBBBBBBBBBBBBB", "SPJ")]


def test_public_folder_page_is_preferred_before_gdown(monkeypatch):
    monkeypatch.setattr(drive_folder.settings, "google_drive_api_key", None)
    expected = [
        DriveFolderFile(
            "file-page",
            "BILLING/from-page.pdf",
            "application/octet-stream",
            source="PUBLIC",
        )
    ]
    monkeypatch.setattr(drive_folder, "_list_public_folder_page", lambda url: expected)

    def fail_gdown(**kwargs):
        raise AssertionError("gdown must not run when embedded public page succeeds")

    monkeypatch.setattr(drive_folder.gdown, "download_folder", fail_gdown)

    rows = list_google_drive_folder_files(
        "https://drive.google.com/drive/folders/public123?usp=sharing"
    )

    assert rows == expected


def test_public_folder_failure_reports_fallback_detail(monkeypatch):
    monkeypatch.setattr(drive_folder.settings, "google_drive_api_key", None)
    monkeypatch.setattr(
        drive_folder,
        "_list_public_folder_page",
        lambda url: (_ for _ in ()).throw(ValueError("embedded blocked")),
    )
    monkeypatch.setattr(
        drive_folder,
        "_list_public_folder_with_gdown",
        lambda url: (_ for _ in ()).throw(ValueError("gdown blocked")),
    )

    try:
        list_google_drive_folder_files(
            "https://drive.google.com/drive/folders/public123?usp=sharing"
        )
    except ValueError as exc:
        message = str(exc)
        assert "Fallback detail" in message
        assert "embedded blocked" in message
        assert "gdown blocked" in message
    else:
        raise AssertionError("expected public folder import to fail")


def test_gdown_public_file_download_uses_only_supported_v52_arguments(monkeypatch):
    monkeypatch.setattr(drive_folder.settings, "google_drive_api_key", None)
    calls = []

    def compatible_download(
        *,
        id=None,
        output=None,
        quiet=False,
        use_cookies=True,
        user_agent=None,
    ):
        calls.append(
            {
                "id": id,
                "output": output,
                "quiet": quiet,
                "use_cookies": use_cookies,
                "user_agent": user_agent,
            }
        )
        Path(output).write_bytes(b"%PDF-compatible-download")
        return output

    monkeypatch.setattr(drive_folder.gdown, "download", compatible_download)
    item = DriveFolderFile(
        "file-compatible",
        "BILLING/evidence.pdf",
        "application/octet-stream",
        source="PUBLIC",
    )

    upload = download_drive_folder_file(item)

    assert upload.file.read() == b"%PDF-compatible-download"
    assert calls[0]["id"] == "file-compatible"
    assert "timeout" not in calls[0]
    assert "retries" not in calls[0]


def test_gdown_folder_discovery_uses_only_supported_v52_arguments(monkeypatch):
    monkeypatch.setattr(drive_folder.settings, "google_drive_api_key", None)
    monkeypatch.setattr(
        drive_folder,
        "_list_public_folder_page",
        lambda url: (_ for _ in ()).throw(ValueError("embedded view blocked")),
    )
    calls = []

    def compatible_download_folder(
        *,
        url=None,
        output=None,
        quiet=False,
        use_cookies=True,
        skip_download=False,
        user_agent=None,
    ):
        calls.append(
            {
                "url": url,
                "output": output,
                "quiet": quiet,
                "use_cookies": use_cookies,
                "skip_download": skip_download,
                "user_agent": user_agent,
            }
        )
        return [
            SimpleNamespace(
                id="file-compatible",
                path="BILLING/evidence.pdf",
                local_path="/tmp/evidence.pdf",
            )
        ]

    monkeypatch.setattr(drive_folder.gdown, "download_folder", compatible_download_folder)

    rows = list_google_drive_folder_files(
        "https://drive.google.com/drive/folders/public123?usp=sharing"
    )

    assert rows[0].file_id == "file-compatible"
    assert calls[0]["skip_download"] is True
    assert "timeout" not in calls[0]
    assert "retries" not in calls[0]
