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
    response = client.get("/ui/main")

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


def test_main_home_sidebar_persists_workspace_pages_and_has_larger_ratio():
    response = client.get("/ui/main")

    assert response.status_code == 200
    assert "--sidebar-width:clamp(272px,19vw,292px)" in response.text
    assert "min-height:48px" in response.text
    assert "font-size:14px" in response.text
    assert "width:34px; height:34px" in response.text
    assert 'id="workspaceFrame"' in response.text
    assert 'id="homeView"' in response.text
    assert "openWorkspace" in response.text
    assert "showHome" in response.text
    assert "history.pushState" in response.text
    assert "/ui/main?view=" in response.text


def test_main_home_internal_menu_links_open_inside_persistent_shell():
    response = client.get("/ui/main")

    assert response.status_code == 200
    assert 'a[href^="/ui/"]' in response.text
    assert "event.preventDefault()" in response.text
    assert "workspaceFrame.src = path" in response.text
    assert "workspaceFrame.style.display = 'block'" in response.text
    assert "homeView.style.display = 'none'" in response.text


def test_main_home_workspace_uses_full_available_width_and_readable_override():
    response = client.get("/ui/main")

    assert response.status_code == 200
    assert "--sidebar-width:clamp(272px,19vw,292px)" in response.text
    assert "max-width:none; width:100%; margin:0" in response.text
    assert "body.workspace-open .workspace-frame" in response.text
    assert "persistent-shell-workspace-style" in response.text
    assert "main{max-width:none!important;width:100%!important" in response.text
    assert "font-size:14px!important;line-height:1.45" in response.text


def test_top_level_browser_ui_navigation_redirects_back_to_persistent_shell():
    response = client.get(
        "/ui/audit-findings",
        headers={"sec-fetch-dest": "document"},
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == "/ui/main?view=%2Fui%2Faudit-findings"


def test_iframe_ui_navigation_is_not_redirected_out_of_workspace():
    response = client.get(
        "/ui/dashboard",
        headers={"sec-fetch-dest": "iframe"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Dashboard Cabang" in response.text


def test_workspace_child_pages_receive_unified_modern_theme():
    response = client.get("/ui/main")

    assert response.status_code == 200
    assert "--shell-primary:#2563eb" in response.text
    assert "background:linear-gradient(135deg,#ffffff 0%,#f6f9ff 58%,#eef6ff 100%)" in response.text
    assert "border-radius:16px!important" in response.text
    assert "border-radius:14px!important" in response.text
    assert "input:focus,select:focus,textarea:focus" in response.text
    assert "tbody tr:hover" in response.text


def test_rendered_main_script_keeps_escaped_newline_and_does_not_break_javascript():
    response = client.get("/ui/main")

    assert response.status_code == 200
    assert r"data ? '\n' + JSON.stringify" in response.text
    assert "data ? '\n' + JSON.stringify" not in response.text


def test_sidebar_navigation_runtime_hooks_are_present_after_script_fix():
    response = client.get("/ui/main")

    assert response.status_code == 200
    assert "document.querySelectorAll('a[href^=\"/ui/\"]')" in response.text
    assert "event.preventDefault()" in response.text
    assert "openWorkspace(href)" in response.text
    assert "workspaceFrame.style.display = 'block'" in response.text
    assert "homeView.style.display = 'none'" in response.text


def test_top_right_account_menu_contains_logout_and_session_context():
    response = client.get("/ui/main")

    assert response.status_code == 200
    assert 'id="accountMenuBtn"' in response.text
    assert 'id="accountDropdown"' in response.text
    assert 'id="accountDropdownName"' in response.text
    assert 'id="accountDropdownMeta"' in response.text
    assert 'id="accountLogoutBtn"' in response.text
    assert ">Logout<" in response.text
    assert "aria-haspopup=\"true\"" in response.text
    assert "aria-expanded=\"false\"" in response.text


def test_account_menu_logout_reuses_secure_browser_session_cleanup():
    response = client.get("/ui/main")

    assert response.status_code == 200
    assert "function logout()" in response.text
    assert "localStorage.removeItem('auditToken')" in response.text
    assert "localStorage.removeItem('auditRefreshToken')" in response.text
    assert "localStorage.removeItem('auditExpiresAt')" in response.text
    assert "localStorage.removeItem('auditUser')" in response.text
    assert "document.getElementById('accountLogoutBtn').addEventListener('click', logout)" in response.text
    assert "window.location.href = '/login'" in response.text


def test_root_url_redirects_directly_to_login():
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/login"
