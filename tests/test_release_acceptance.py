from pathlib import Path
import json

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.main import app


ROOT = Path(__file__).resolve().parents[1]


def _route_paths() -> set[str]:
    return set(app.openapi().get("paths", {}))


def test_release_has_single_alembic_head():
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1
    assert heads[0] == "0028_performance_hardening"


def test_release_identity_and_readiness_routes_registered():
    paths = _route_paths()
    assert {"/health", "/version", "/readiness"} <= paths


def test_current_audit_ui_routes_registered():
    required = {
        "/ui/users",
        "/ui/audit-engagements",
        "/ui/audit-sampling",
        "/ui/audit-working-papers",
        "/ui/audit-findings",
        "/ui/management-actions",
        "/ui/follow-up",
        "/ui/audit-management",
        "/ui/notifications",
        "/ui/evidence-repository",
        "/ui/search",
        "/ui/audit-reports",
        "/ui/audit-closing",
    }
    assert required <= _route_paths()


def test_current_protected_audit_api_routes_registered():
    required = {
        "/admin/users",
        "/audit-findings",
        "/management-responses",
        "/corrective-action-plans",
        "/follow-up",
        "/dashboard/audit-management",
        "/notifications",
        "/evidence-repository",
        "/search",
    }
    assert required <= _route_paths()


def test_vercel_feature_branches_do_not_auto_deploy():
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    enabled = config["git"]["deploymentEnabled"]
    for pattern in ("feature/*", "fix/*", "chore/*", "codex/*", "dev/*"):
        assert enabled[pattern] is False
    assert "main" not in enabled


def test_release_documentation_contains_required_operational_gates():
    text = (ROOT / "DEPLOYMENT.md").read_text(encoding="utf-8").lower()
    assert "schema-first" in text
    assert "production smoke" in text
    assert "vercel quota recovery" in text
    assert "rollback" in text


def test_core_release_control_test_modules_are_present():
    required = {
        "test_branch_access.py",
        "test_role_navigation.py",
        "test_audit_working_paper.py",
        "test_audit_finding.py",
        "test_management_actions.py",
        "test_follow_up.py",
        "test_audit_management_dashboard.py",
        "test_notifications.py",
        "test_evidence_repository.py",
        "test_global_search.py",
        "test_release_readiness.py",
    }
    present = {path.name for path in (ROOT / "tests").glob("test_*.py")}
    assert required <= present
