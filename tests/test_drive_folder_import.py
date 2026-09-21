from fastapi.testclient import TestClient

from app.main import app
from app.services.drive_folder import extract_google_drive_folder_id, is_supported_drive_folder_file, DriveFolderFile


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
    assert not is_supported_drive_folder_file(DriveFolderFile("3", "catatan.txt", "text/plain"))


def test_drive_import_ui_includes_folder_endpoint():
    response = client.get("/ui/drive-import")

    assert response.status_code == 200
    assert "Import Folder Link" in response.text
    assert "/documents/drive-folder-import" in response.text
    assert "GOOGLE_DRIVE_API_KEY" in response.text


def test_drive_folder_import_endpoint_order_not_caught_by_document_type_route():
    response = client.post("/documents/drive-folder-import", data={"url": "https://drive.google.com/drive/folders/abc"})

    assert response.status_code in {400, 401}
    assert "document_type must be BILLING or SPJ" not in response.text
