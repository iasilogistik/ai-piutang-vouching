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


def test_control_evidence_ui_has_search_and_status_filters():
    response = client.get("/ui/control-evidence")

    assert response.status_code == 200
    assert "Search" in response.text
    assert "searchText" in response.text
    assert "statusFilter" in response.text
    assert "signatureFilter" in response.text
    assert "stampFilter" in response.text
    assert "Rows Setelah Filter" in response.text



def test_control_evidence_ui_formats_spj_and_partial_payment_for_readability():
    response = client.get("/ui/control-evidence")

    assert response.status_code == 200
    assert "function formatMoneyId(value)" in response.text
    assert "new Intl.NumberFormat('id-ID'" in response.text
    assert "row.no_spj || '-'" in response.text
    assert "formatMoneyId(row.billing_partial_payment)" in response.text
    assert "formatMoneyId(row.spj_partial_payment)" in response.text
