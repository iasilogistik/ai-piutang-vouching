from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_control_evidence_ui_shell_loads():
    response = client.get("/ui/control-evidence")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Dashboard Control Evidence SPJ" in response.text
    assert "/dashboard/control-evidence/export" in response.text
    assert "/reviews/control-evidence/" in response.text
    assert "Bearer Token" in response.text
