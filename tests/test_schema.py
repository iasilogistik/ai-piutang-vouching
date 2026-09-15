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

    vouching_unique = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("vouching_result")
    }
    assert ("billing_id",) in vouching_unique
