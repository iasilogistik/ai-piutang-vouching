from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_uat_pasuruan_ui_shell_loads():
    response = client.get("/ui/uat-pasuruan")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "UAT Pasuruan Final" in response.text
    assert "SANTOSO" in response.text
    assert "TTD checker" in response.text
    assert "/ui/control-evidence" in response.text
    assert "Export Evidence" in response.text


def test_uat_pasuruan_ui_contains_operational_upload_workbench():
    response = client.get("/ui/uat-pasuruan")

    assert "Operational Upload Workbench" in response.text
    assert "Bearer Token" in response.text
    assert "/sap/import" in response.text
    assert "/sap/validate/" in response.text
    assert "/documents/BILLING" in response.text
    assert "/documents/SPJ" in response.text
    assert "/reconciliation/" in response.text
    assert "/spj/vouch" in response.text
    assert "Log UAT" in response.text
