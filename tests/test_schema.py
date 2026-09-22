from sqlalchemy import inspect

from app.database import engine

EXPECTED_TABLES = {
    "documents",
    "import_batches",
    "sap_billing",
    "physical_billing",
    "billing_reconciliation",
    "spj",
    "vouching_result",
    "document_control_evidence",
    "control_evidence_detections",
    "audit_workflow_cases",
    "audit_engagements",
    "audit_engagement_assignments",
    "audit_populations",
    "audit_samples",
    "audit_working_papers",
    "audit_working_paper_versions",
    "audit_working_paper_evidence",
    "audit_working_paper_exceptions",
}


def test_core_schema_tables_exist() -> None:
    tables = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES.issubset(tables)


def test_schema_relationship_columns_exist() -> None:
    inspector = inspect(engine)
    assert {"import_batch_id", "billing_document", "doc_date", "nominal"}.issubset(
        {column["name"] for column in inspector.get_columns("sap_billing")}
    )
    assert {"document_id", "billing_document", "no_spj", "doc_date", "nominal"}.issubset(
        {column["name"] for column in inspector.get_columns("physical_billing")}
    )
    assert {
        "billing_id",
        "spj_id",
        "no_spj_billing",
        "no_spj_document",
        "status",
        "automated_status",
        "automated_rule_code",
        "automated_remarks",
        "manual_review_status",
        "review_reason_code",
        "reviewer_remarks",
        "expected_customer_name",
        "control_evidence_id",
    }.issubset({column["name"] for column in inspector.get_columns("vouching_result")})
    assert {
        "document_id",
        "receiver_signature_status",
        "driver_signature_status",
        "security_signature_status",
        "bm_signature_status",
        "checker_signature_status",
        "receiver_stamp_status",
        "stamp_text_raw",
        "stamp_customer_match_status",
        "review_required",
        "review_reasons",
    }.issubset({column["name"] for column in inspector.get_columns("document_control_evidence")})
    assert {
        "id",
        "engagement_id",
        "branch",
        "vouching_result_id",
        "control_evidence_id",
        "audit_exception_id",
        "review_workflow_id",
        "audit_report_id",
        "audit_closing_id",
        "stage",
        "created_by",
        "updated_by",
    }.issubset({column["name"] for column in inspector.get_columns("audit_workflow_cases")})
    assert "engagement_id" in {column["name"] for column in inspector.get_columns("audit_reports")}
    assert {
        "id", "code", "title", "branch", "period_start", "period_end", "scope", "status",
        "created_by", "updated_by", "created_at", "updated_at",
    }.issubset({column["name"] for column in inspector.get_columns("audit_engagements")})
    assert {
        "id", "engagement_id", "user_id", "assignment_role", "assigned_by", "assigned_at",
    }.issubset({column["name"] for column in inspector.get_columns("audit_engagement_assignments")})
    assert {
        "id", "engagement_id", "branch", "name", "population_type", "source_type",
        "source_reference", "total_records", "total_value", "snapshot_at", "created_by", "created_at",
    }.issubset({column["name"] for column in inspector.get_columns("audit_populations")})
    assert {
        "id", "engagement_id", "population_id", "branch", "source_record_ref", "selection_method",
        "selection_reason", "method_parameters", "monetary_value", "status", "selected_by", "selected_at",
        "vouching_result_id", "control_evidence_id",
    }.issubset({column["name"] for column in inspector.get_columns("audit_samples")})
    assert {
        "id", "engagement_id", "branch", "reference", "title", "audit_objective",
        "procedure_performed", "result_observation", "conclusion", "preparer_id", "prepared_at",
        "reviewer_id", "reviewed_at", "status", "version_number", "sample_id", "created_at", "updated_at",
    }.issubset({column["name"] for column in inspector.get_columns("audit_working_papers")})
    assert {
        "id", "working_paper_id", "version_number", "title", "audit_objective", "procedure_performed",
        "result_observation", "conclusion", "status", "changed_by", "change_reason", "created_at",
    }.issubset({column["name"] for column in inspector.get_columns("audit_working_paper_versions")})
    assert {
        "id", "working_paper_id", "document_id", "control_evidence_id", "linked_by", "linked_at",
    }.issubset({column["name"] for column in inspector.get_columns("audit_working_paper_evidence")})
    assert {
        "id", "working_paper_id", "audit_exception_id", "linked_by", "linked_at",
    }.issubset({column["name"] for column in inspector.get_columns("audit_working_paper_exceptions")})
    assert {
        "document_id",
        "branch",
        "detection_type",
        "status",
        "confidence",
        "page_number",
        "reference_json",
        "source_file_hash",
        "detector_name",
        "detector_version",
        "extraction_engine",
        "processing_status",
        "error_message",
        "processed_at",
    }.issubset({column["name"] for column in inspector.get_columns("control_evidence_detections")})


def test_one_to_one_constraints_are_declared() -> None:
    inspector = inspect(engine)

    billing_reconciliation_unique = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("billing_reconciliation")
    }
    assert ("sap_billing_id",) in billing_reconciliation_unique
    assert ("physical_billing_id",) in billing_reconciliation_unique

    physical_billing_unique = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("physical_billing")
    }
    assert ("document_id",) in physical_billing_unique

    spj_unique = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("spj")
    }
    assert ("document_id",) in spj_unique

    control_unique = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("document_control_evidence")
    }
    assert ("document_id",) in control_unique

    vouching_unique = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("vouching_result")
    }
    assert ("billing_id",) in vouching_unique


def test_detection_idempotency_constraint_is_declared() -> None:
    inspector = inspect(engine)
    constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("control_evidence_detections")
    }
    assert (
        "document_id",
        "detection_type",
        "source_file_hash",
        "detector_name",
        "detector_version",
    ) in constraints


def test_workflow_case_is_unique_per_vouching_result() -> None:
    inspector = inspect(engine)
    constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("audit_workflow_cases")
    }
    assert ("vouching_result_id",) in constraints


def test_engagement_constraints_are_declared() -> None:
    inspector = inspect(engine)
    engagement_unique = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("audit_engagements")
    }
    assignment_unique = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("audit_engagement_assignments")
    }
    assert ("code",) in engagement_unique
    assert ("engagement_id", "user_id", "assignment_role") in assignment_unique


def test_audit_sample_duplicate_constraint_is_declared() -> None:
    inspector = inspect(engine)
    constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("audit_samples")
    }
    assert ("population_id", "source_record_ref") in constraints


def test_working_paper_constraints_are_declared() -> None:
    inspector = inspect(engine)
    papers = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("audit_working_papers")
    }
    versions = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("audit_working_paper_versions")
    }
    exceptions = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("audit_working_paper_exceptions")
    }
    assert ("engagement_id", "reference") in papers
    assert ("working_paper_id", "version_number") in versions
    assert ("working_paper_id", "audit_exception_id") in exceptions
