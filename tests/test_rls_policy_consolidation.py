import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic" / "versions" / "0033_rls_policy_consolidation.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("rls_0033", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_rls_consolidation_is_single_release_head():
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    assert ScriptDirectory.from_config(config).get_heads() == ["0033_rls_policy_consolidation"]


def test_rls_consolidation_covers_exact_current_overlap_set():
    module = _load_migration()
    policies = list(module._POLICIES)

    assert len(policies) == 21
    assert {row[0] for row in policies} == set(["audit_engagement_assignments","audit_finding_evidence","audit_finding_exceptions","audit_finding_samples","audit_finding_versions","audit_finding_working_papers","audit_findings","audit_populations","audit_samples","audit_working_paper_evidence","audit_working_paper_exceptions","audit_working_paper_versions","audit_working_papers","corrective_action_evidence","corrective_action_plan_history","corrective_action_plans","corrective_action_progress_updates","corrective_action_verifications","evidence_resource_links","management_response_versions","management_responses"])
    assert {row[1] for row in policies} == set(["admin_manage_audit_engagement_assignments","auditor_manage_audit_finding_evidence","auditor_manage_audit_finding_exceptions","auditor_manage_audit_finding_samples","app_manage_audit_finding_versions","auditor_manage_audit_finding_working_papers","auditor_reviewer_manage_audit_findings","auditor_manage_audit_populations","auditor_manage_audit_samples","auditor_manage_audit_working_paper_evidence","auditor_manage_audit_working_paper_exceptions","app_manage_audit_working_paper_versions","auditor_manage_audit_working_papers","app_manage_corrective_action_evidence","app_manage_corrective_action_plan_history","app_manage_corrective_action_plans","app_manage_corrective_action_progress_updates","app_manage_corrective_action_verifications","auditor_manage_evidence_resource_links","app_manage_management_response_versions","app_manage_management_responses"])
    assert all(row[2] for row in policies)
    assert all(row[3] for row in policies)


def test_split_preserves_read_policy_and_creates_only_dml_manage_policies(monkeypatch):
    module = _load_migration()
    executed = []
    monkeypatch.setattr(module.op, "execute", executed.append)

    table, policy, using_expr, check_expr = module._POLICIES[0]
    module._split_policy(table, policy, using_expr, check_expr)

    sql = "\n".join(str(item).lower() for item in executed)
    assert f'drop policy if exists "{policy.lower()}"' in sql
    assert " for insert to authenticated" in sql
    assert " for update to authenticated" in sql
    assert " for delete to authenticated" in sql
    assert " for select " not in sql
    assert " for all " not in sql
    assert using_expr.lower() in sql
    assert check_expr.lower() in sql


def test_downgrade_restores_original_all_policy(monkeypatch):
    module = _load_migration()
    executed = []
    monkeypatch.setattr(module.op, "execute", executed.append)

    table, policy, using_expr, check_expr = module._POLICIES[0]
    module._restore_policy(table, policy, using_expr, check_expr)

    sql = "\n".join(str(item).lower() for item in executed)
    assert f'"{policy.lower()}_insert"' in sql
    assert f'"{policy.lower()}_update"' in sql
    assert f'"{policy.lower()}_delete"' in sql
    assert " for all to authenticated" in sql
    assert using_expr.lower() in sql
    assert check_expr.lower() in sql
