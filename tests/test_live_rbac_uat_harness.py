import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "live_rbac_uat.py"


def _module():
    spec = importlib.util.spec_from_file_location("live_rbac_uat", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_live_rbac_uat_matrix_is_non_mutating_and_role_aware(monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "UAT_BRANCH", "GRESIK")
    monkeypatch.setattr(module, "UAT_SECOND_BRANCH", "SIDOARJO")
    monkeypatch.setattr(module, "SCOPED_VIEWER_BRANCH", "GRESIK")

    calls = []

    def fake_transport(token, path, method, form):
        role = token
        calls.append((role, path, method, form))

        if path == "/auth/me":
            if role == "SCOPED_VIEWER":
                return 200, '{"role":"VIEWER","branch":"GRESIK"}'
            branch = None
            return 200, (
                f'{{"role":"{role}","branch":null}}'
                if branch is None
                else f'{{"role":"{role}","branch":"{branch}"}}'
            )

        if path == "/admin/users":
            return (200 if role == "ADMIN" else 403), "{}"

        if role == "SCOPED_VIEWER" and "branch=SIDOARJO" in path:
            return 403, "{}"

        if path == "/audit-findings" and method == "POST":
            return (404 if role in {"ADMIN", "AUDITOR"} else 403), "{}"

        if path.endswith(f"/audit-findings/{module.MISSING_ID}/reopen"):
            return (404 if role in {"ADMIN", "REVIEWER"} else 403), "{}"

        if path.endswith(f"/corrective-action-plans/{module.MISSING_ID}/verification"):
            return (404 if role in {"ADMIN", "REVIEWER"} else 403), "{}"

        return 200, "{}"

    tokens = {role: role for role in module.ROLES}
    tokens["SCOPED_VIEWER"] = "SCOPED_VIEWER"
    results = module.run_matrix(tokens, transport=fake_transport)

    assert results
    assert all(result.passed for result in results)

    global_branch_reads = [
        call for call in calls
        if call[0] in module.ROLES
        and call[2] == "GET"
        and ("branch=GRESIK" in call[1] or "branch=SIDOARJO" in call[1])
    ]
    assert global_branch_reads
    assert any(call[0] == "AUDITOR" and "branch=GRESIK" in call[1] for call in global_branch_reads)
    assert any(call[0] == "AUDITOR" and "branch=SIDOARJO" in call[1] for call in global_branch_reads)

    scoped_denials = [
        call for call in calls
        if call[0] == "SCOPED_VIEWER" and "branch=SIDOARJO" in call[1]
    ]
    assert len(scoped_denials) == 3

    mutation_calls = [call for call in calls if call[2] == "POST"]
    assert mutation_calls
    assert all(str(module.MISSING_ID) in call[1] or call[1] == "/audit-findings" for call in mutation_calls)
    assert any(call[1] == "/audit-findings" and call[3]["engagement_id"] == module.MISSING_ID for call in mutation_calls)


def test_tokens_are_required_from_environment(monkeypatch):
    module = _module()
    for role in module.ROLES:
        monkeypatch.delenv(f"{role}_TOKEN", raising=False)
    monkeypatch.delenv("SCOPED_VIEWER_TOKEN", raising=False)
    monkeypatch.setattr(module, "UAT_BRANCH", "")
    monkeypatch.setattr(module, "UAT_SECOND_BRANCH", "")
    monkeypatch.setattr(module, "SCOPED_VIEWER_BRANCH", "")

    try:
        module._tokens_from_env()
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected missing token precondition failure")

    for role in module.ROLES:
        assert f"{role}_TOKEN" in message
    assert "SCOPED_VIEWER_TOKEN" in message
    assert "UAT_BRANCH" in message
    assert "UAT_SECOND_BRANCH" in message
    assert "SCOPED_VIEWER_BRANCH" in message


def test_uat_requires_two_distinct_real_branches(monkeypatch):
    module = _module()
    for role in module.ROLES:
        monkeypatch.setenv(f"{role}_TOKEN", role)
    monkeypatch.setenv("SCOPED_VIEWER_TOKEN", "SCOPED")
    monkeypatch.setattr(module, "UAT_BRANCH", "GRESIK")
    monkeypatch.setattr(module, "UAT_SECOND_BRANCH", "GRESIK")
    monkeypatch.setattr(module, "SCOPED_VIEWER_BRANCH", "GRESIK")

    try:
        module._tokens_from_env()
    except RuntimeError as exc:
        assert "UAT_SECOND_BRANCH must differ" in str(exc)
    else:
        raise AssertionError("Expected duplicate branch precondition failure")
