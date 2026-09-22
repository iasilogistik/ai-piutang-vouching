from fastapi.testclient import TestClient

from app.auth import CurrentUser, current_user
from app.main import app
from app.services.navigation import menu_for_role

client = TestClient(app)


def _labels(role: str):
    return [item["label"] for item in menu_for_role(role)]


def test_admin_navigation_contains_administration_links():
    labels = _labels("ADMIN")
    assert "Users" in labels
    assert "Branches" in labels
    assert "Upload" in labels
    assert "Audit Trail" in labels


def test_non_admin_navigation_hides_administration_links():
    for role in ("AUDITOR", "REVIEWER", "VIEWER"):
        labels = _labels(role)
        assert "Users" not in labels
        assert "Branches" not in labels


def test_viewer_navigation_is_read_focused():
    labels = _labels("VIEWER")
    assert labels == ["Dashboard", "Engagements", "Sampling", "Working Papers", "Findings", "Management Actions", "Workflow", "Reports", "Evidence"]
    assert "Upload" not in labels
    assert "Vouching" not in labels


def test_navigation_fragment_uses_authenticated_role_and_branch():
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        user_id="reviewer-nav", role="REVIEWER", branch="PASURUAN"
    )
    try:
        response = client.get("/ui/navigation")
        assert response.status_code == 200
        assert 'data-role="REVIEWER"' in response.text
        assert 'data-branch="PASURUAN"' in response.text
        assert "Review Queue" in response.text
        assert "User Management" not in response.text
        assert ">Users<" not in response.text
    finally:
        app.dependency_overrides.pop(current_user, None)


def _hrefs(role: str):
    return {item["label"]: item["href"] for item in menu_for_role(role)}


def test_wave2_navigation_uses_new_primary_routes():
    admin = _hrefs("ADMIN")
    auditor = _hrefs("AUDITOR")
    reviewer = _hrefs("REVIEWER")
    viewer = _hrefs("VIEWER")

    assert admin["Dashboard"] == "/ui/dashboard"
    assert admin["Engagements"] == "/ui/audit-engagements"
    assert admin["Sampling"] == "/ui/audit-sampling"
    assert admin["Working Papers"] == "/ui/audit-working-papers"
    assert admin["Findings"] == "/ui/audit-findings"
    assert admin["Management Actions"] == "/ui/management-actions"
    assert admin["Upload"] == "/ui/upload"
    assert admin["Exceptions"] == "/ui/exceptions"
    assert admin["Review Queue"] == "/ui/review-queue"
    assert admin["Workflow"] == "/ui/audit-workflow"

    assert auditor["Dashboard"] == "/ui/dashboard"
    assert auditor["Engagements"] == "/ui/audit-engagements"
    assert auditor["Sampling"] == "/ui/audit-sampling"
    assert auditor["Working Papers"] == "/ui/audit-working-papers"
    assert auditor["Findings"] == "/ui/audit-findings"
    assert auditor["Management Actions"] == "/ui/management-actions"
    assert auditor["Upload"] == "/ui/upload"
    assert auditor["Exceptions"] == "/ui/exceptions"
    assert auditor["Review Queue"] == "/ui/review-queue"
    assert auditor["Workflow"] == "/ui/audit-workflow"

    assert reviewer["Dashboard"] == "/ui/dashboard"
    assert reviewer["Engagements"] == "/ui/audit-engagements"
    assert reviewer["Sampling"] == "/ui/audit-sampling"
    assert reviewer["Working Papers"] == "/ui/audit-working-papers"
    assert reviewer["Findings"] == "/ui/audit-findings"
    assert reviewer["Management Actions"] == "/ui/management-actions"
    assert reviewer["Review Queue"] == "/ui/review-queue"
    assert reviewer["Exceptions"] == "/ui/exceptions"
    assert reviewer["Workflow"] == "/ui/audit-workflow"

    assert viewer["Dashboard"] == "/ui/dashboard"
    assert viewer["Engagements"] == "/ui/audit-engagements"
    assert viewer["Sampling"] == "/ui/audit-sampling"
    assert viewer["Working Papers"] == "/ui/audit-working-papers"
    assert viewer["Findings"] == "/ui/audit-findings"
    assert viewer["Management Actions"] == "/ui/management-actions"
    assert viewer["Workflow"] == "/ui/audit-workflow"
    assert "Upload" not in viewer
    assert "Exceptions" not in viewer
    assert "Review Queue" not in viewer
