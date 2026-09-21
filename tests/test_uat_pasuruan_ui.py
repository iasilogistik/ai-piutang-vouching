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
    assert "Export Excel" in response.text
