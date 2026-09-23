from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic" / "versions" / "0028_performance_hardening.py"


def test_public_revision_helper_precedes_acl_hardening():
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision("0031_revision_helper_acl")
    assert revision.down_revision == "0030_public_revision_helper"


def test_performance_hardening_covers_reported_foreign_keys_and_rls_initplan():
    text = MIGRATION.read_text(encoding="utf-8")

    required_columns = {
        "audit_finding_evidence": {"control_evidence_id", "document_id"},
        "audit_finding_exceptions": {"audit_exception_id"},
        "audit_finding_samples": {"sample_id"},
        "audit_finding_working_papers": {"working_paper_id"},
        "audit_samples": {"control_evidence_id", "vouching_result_id"},
        "audit_workflow_cases": {
            "audit_closing_id",
            "audit_exception_id",
            "audit_report_id",
            "control_evidence_id",
            "review_workflow_id",
        },
        "audit_working_paper_evidence": {"control_evidence_id", "document_id"},
        "audit_working_paper_exceptions": {"audit_exception_id"},
        "corrective_action_evidence": {"control_evidence_id", "document_id"},
        "corrective_action_plans": {"response_id"},
    }

    for table, columns in required_columns.items():
        assert table in text
        for column in columns:
            assert column in text

    assert text.count('op.create_index(') == 1  # loop is intentionally data-driven
    assert "(select auth.uid())::text" in text
    assert "notification_owner_read" in text
    assert "notification_owner_update" in text
    assert "notification_preferences_owner" in text
