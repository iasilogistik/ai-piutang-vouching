from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_combined_upload_ui_shell_loads():
    response = client.get("/ui/combined-upload")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Combined Billing + SPJ Upload" in response.text
    assert "/documents/combined" in response.text
    assert "Buka Control Evidence" in response.text


def test_combined_upload_endpoint_is_protected_before_document_type_route():
    response = client.post("/documents/combined")

    assert response.status_code == 401
    assert "document_type must be BILLING or SPJ" not in response.text
