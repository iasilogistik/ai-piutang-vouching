from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_main_home_layout_uses_left_sidebar_and_session_based_dashboard():
    response = client.get("/ui/main")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "AI Piutang Vouching" in response.text
    assert 'class="sidebar"' in response.text
    assert "Overview" in response.text
    assert "Data &amp; Vouching" in response.text
    assert "Monitoring" in response.text
    assert "Administration" in response.text
    assert "Ringkasan Operasional" in response.text
    assert "Alur Kerja Audit" in response.text
    assert "Akses Cepat" in response.text
    assert "/ui/dashboard" in response.text
    assert "/ui/upload" in response.text
    assert "/ui/users" in response.text
    assert "Filter cabang (opsional)" in response.text
    assert "Sesi login digunakan otomatis dari browser" in response.text
    assert "Bearer token" not in response.text
    assert "Bearer Token" not in response.text
    assert 'id="token"' not in response.text


def test_main_home_sidebar_is_role_aware_and_responsive():
    response = client.get("/")

    assert response.status_code == 200
    assert 'data-roles="ADMIN,AUDITOR"' in response.text
    assert 'data-roles="ADMIN"' in response.text
    assert "admin-only" in response.text
    assert "role !== 'ADMIN'" in response.text
    assert "mobile-nav-open" in response.text
    assert "sidebar-collapsed" in response.text
    assert "auditSidebarCollapsed" in response.text


def test_main_home_keeps_core_audit_navigation():
    response = client.get("/ui/main")

    assert response.status_code == 200
    for path in (
        "/ui/audit-management",
        "/ui/audit-engagements",
        "/ui/audit-sampling",
        "/ui/audit-working-papers",
        "/ui/audit-findings",
        "/ui/management-actions",
        "/ui/follow-up",
        "/ui/control-evidence",
        "/ui/evidence-repository",
        "/ui/audit-reports",
    ):
        assert path in response.text
