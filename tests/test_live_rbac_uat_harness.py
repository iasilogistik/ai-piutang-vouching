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
    monkeypatch.setattr(module, "UAT_BRANCH", "PASURUAN")
    monkeypatch.setattr(module, "OTHER_BRANCH", "__OUTSIDE__")

    calls = []

    def fake_transport(token, path, method, form):
        role = token
        calls.append((role, path, method, form))

        if path == "/auth/me":
            branch = None if role == "ADMIN" else "PASURUAN"
            return 200, f'{{"role":"{role}","branch":{repr(branch).replace("None", "null")}}}'.replace("'", '"')

        if path == "/admin/users":
            return (200 if role == "ADMIN" else 403), "{}"

        if "branch=__OUTSIDE__" in path:
            return 403, "{}"

        if path == "/audit-findings" and method == "POST":
            return (404 if role in {"ADMIN", "AUDITOR"} else 403), "{}"

        if path.endswith(f"/audit-findings/{module.MISSING_ID}/reopen"):
            return (404 if role in {"ADMIN", "REVIEWER"} else 403), "{}"

        if path.endswith(f"/corrective-action-plans/{module.MISSING_ID}/verification"):
            return (404 if role in {"ADMIN", "REVIEWER"} else 403), "{}"

        return 200, "{}"

    tokens = {role: role for role in module.ROLES}
    results = module.run_matrix(tokens, transport=fake_transport)

    assert results
    assert all(result.passed for result in results)

    mutation_calls = [call for call in calls if call[2] == "POST"]
    assert mutation_calls
    assert all(str(module.MISSING_ID) in call[1] or call[1] == "/audit-findings" for call in mutation_calls)
    assert any(call[1] == "/audit-findings" and call[3]["engagement_id"] == module.MISSING_ID for call in mutation_calls)


def test_tokens_are_required_from_environment(monkeypatch):
    module = _module()
    for role in module.ROLES:
        monkeypatch.delenv(f"{role}_TOKEN", raising=False)

    try:
        module._tokens_from_env()
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected missing token precondition failure")

    for role in module.ROLES:
        assert f"{role}_TOKEN" in message
