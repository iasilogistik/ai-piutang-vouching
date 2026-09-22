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
    assert {"billing_id", "spj_id", "no_spj_billing", "no_spj_document", "status"}.issubset(
        {column["name"] for column in inspector.get_columns("vouching_result")}
    )
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
