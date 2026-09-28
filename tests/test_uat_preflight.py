import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "uat_preflight.py"


def _module():
    spec = importlib.util.spec_from_file_location("uat_preflight", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ready_state():
    return {
        "branches": [
            {"branch": "GRESIK", "records": 2},
            {"branch": "SIDOARJO", "records": 1},
        ],
        "roles": [
            {"role": "ADMIN", "scope": "GLOBAL", "branch": None, "users": 1},
            {"role": "AUDITOR", "scope": "GLOBAL", "branch": None, "users": 1},
            {"role": "REVIEWER", "scope": "GLOBAL", "branch": None, "users": 1},
            {"role": "VIEWER", "scope": "GLOBAL", "branch": None, "users": 1},
            {"role": "VIEWER", "scope": "SCOPED", "branch": "GRESIK", "users": 1},
        ],
        "branchless_business": {
            "documents": 0,
            "import_batches": 0,
            "audit_findings": 0,
            "corrective_action_plans": 0,
        },
        "operational_audit_trail_branchless": 0,
        "administrative_global_audit_events": 4,
    }


def test_preflight_ready_does_not_block_global_user_role_audit_events():
    module = _module()
    report = module.evaluate_state(_ready_state())

    assert report["ready"] is True
    assert report["issues"] == []
    assert report["administrative_global_audit_events"] == 4


def test_preflight_reports_missing_real_branches_global_auditor_and_scoped_viewer():
    module = _module()
    state = _ready_state()
    state["branches"] = []
    state["roles"] = [
        {"role": "ADMIN", "scope": "GLOBAL", "branch": None, "users": 1},
        {"role": "AUDITOR", "scope": "SCOPED", "branch": "PASURUAN", "users": 1},
        {"role": "REVIEWER", "scope": "GLOBAL", "branch": None, "users": 1},
        {"role": "VIEWER", "scope": "GLOBAL", "branch": None, "users": 1},
    ]

    report = module.evaluate_state(state)
    codes = {issue["code"] for issue in report["issues"]}

    assert report["ready"] is False
    assert "REAL_UPLOADED_BRANCHES" in codes
    assert "GLOBAL_AUDITOR" in codes
    assert "SCOPED_VIEWER" in codes


def test_preflight_blocks_branchless_business_and_operational_audit_rows():
    module = _module()
    state = _ready_state()
    state["branchless_business"]["documents"] = 1
    state["operational_audit_trail_branchless"] = 2

    report = module.evaluate_state(state)
    codes = {issue["code"] for issue in report["issues"]}

    assert report["ready"] is False
    assert "BRANCHLESS_DOCUMENTS" in codes
    assert "BRANCHLESS_OPERATIONAL_AUDIT" in codes
