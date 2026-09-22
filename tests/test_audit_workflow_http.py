from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_audit_workflow_ui_exposes_integrated_flow():
    response = client.get("/ui/audit-workflow")
    assert response.status_code == 200
    assert "End-to-End Audit Workflow" in response.text
    assert "VOUCHING" in response.text
    assert "CONTROL_EVIDENCE" in response.text
    assert "CLOSING" in response.text


def test_audit_workflow_api_requires_authentication():
    assert client.get("/audit-workflow-cases").status_code == 401
    assert client.get("/audit-workflow-cases/1").status_code == 401
    assert client.post(
        "/audit-workflow-cases",
        data={"vouching_result_id": "1"},
    ).status_code == 401
    assert client.post(
        "/audit-workflow-cases/1/transition",
        data={"stage": "CONTROL_EVIDENCE"},
    ).status_code == 401
