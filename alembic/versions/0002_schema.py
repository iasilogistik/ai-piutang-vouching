"""Create core vouching schema."""

from alembic import op
import sqlalchemy as sa

revision = "0002_schema"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("document_type", sa.String(20), nullable=False),
        sa.Column("file_hash", sa.String(128), nullable=False),
        sa.Column("storage_path", sa.String(1024), nullable=False),
        sa.Column("uploaded_by", sa.String(100)),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("period", sa.Date()),
        sa.Column("uploaded_by", sa.String(100)),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("total_records", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(30), server_default="UPLOADED", nullable=False),
    )
    op.create_table(
        "sap_billing",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("import_batch_id", sa.Integer(), sa.ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("customer", sa.String(255)),
        sa.Column("customer_account_name", sa.String(255)),
        sa.Column("billing_document", sa.String(100), nullable=False),
        sa.Column("doc_date", sa.Date(), nullable=False),
        sa.Column("nominal", sa.Numeric(20, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("import_batch_id", "billing_document", name="uq_sap_billing_batch_document"),
    )
    op.create_index("ix_sap_billing_billing_document", "sap_billing", ["billing_document"])
    op.create_table(
        "physical_billing",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("billing_document_raw", sa.Text()),
        sa.Column("billing_document", sa.String(100)),
        sa.Column("no_spj_raw", sa.Text()),
        sa.Column("no_spj", sa.String(100)),
        sa.Column("doc_date", sa.Date()),
        sa.Column("nominal", sa.Numeric(20, 2)),
        sa.Column("ocr_confidence", sa.Numeric(5, 4)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_physical_billing_billing_document", "physical_billing", ["billing_document"])
    op.create_table(
        "billing_reconciliation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sap_billing_id", sa.Integer(), sa.ForeignKey("sap_billing.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("physical_billing_id", sa.Integer(), sa.ForeignKey("physical_billing.id", ondelete="SET NULL"), unique=True),
        sa.Column("billing_match", sa.Boolean(), nullable=False),
        sa.Column("date_match", sa.Boolean(), nullable=False),
        sa.Column("nominal_match", sa.Boolean(), nullable=False),
        sa.Column("nominal_difference", sa.Numeric(20, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("exception_code", sa.String(50)),
        sa.Column("remarks", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_billing_reconciliation_status", "billing_reconciliation", ["status"])
    op.create_table(
        "spj",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("no_spj_raw", sa.Text()),
        sa.Column("no_spj", sa.String(100)),
        sa.Column("ocr_confidence", sa.Numeric(5, 4)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_spj_no_spj", "spj", ["no_spj"])
    op.create_table(
        "vouching_result",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("billing_id", sa.Integer(), sa.ForeignKey("physical_billing.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("spj_id", sa.Integer(), sa.ForeignKey("spj.id", ondelete="SET NULL")),
        sa.Column("no_spj_billing", sa.String(100)),
        sa.Column("no_spj_document", sa.String(100)),
        sa.Column("spj_match", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("rule_code", sa.String(50)),
        sa.Column("remarks", sa.Text()),
        sa.Column("reviewer_id", sa.String(100)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_vouching_result_status", "vouching_result", ["status"])


def downgrade() -> None:
    op.drop_index("ix_vouching_result_status", table_name="vouching_result")
    op.drop_table("vouching_result")
    op.drop_index("ix_spj_no_spj", table_name="spj")
    op.drop_table("spj")
    op.drop_index("ix_billing_reconciliation_status", table_name="billing_reconciliation")
    op.drop_table("billing_reconciliation")
    op.drop_index("ix_physical_billing_billing_document", table_name="physical_billing")
    op.drop_table("physical_billing")
    op.drop_index("ix_sap_billing_billing_document", table_name="sap_billing")
    op.drop_table("sap_billing")
    op.drop_table("import_batches")
    op.drop_table("documents")
