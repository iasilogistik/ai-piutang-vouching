"""Add document control evidence table.

Revision ID: 0006_document_control_evidence
Revises: 0005_vouching_spj_index
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_document_control_evidence"
down_revision = "0005_vouching_spj_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_control_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("receiver_signature_status", sa.String(length=20), nullable=True),
        sa.Column("receiver_signature_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("receiver_signature_remarks", sa.Text(), nullable=True),
        sa.Column("driver_signature_status", sa.String(length=20), nullable=True),
        sa.Column("driver_signature_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("driver_signature_remarks", sa.Text(), nullable=True),
        sa.Column("security_signature_status", sa.String(length=20), nullable=True),
        sa.Column("security_signature_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("security_signature_remarks", sa.Text(), nullable=True),
        sa.Column("bm_signature_status", sa.String(length=20), nullable=True),
        sa.Column("bm_signature_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("bm_signature_remarks", sa.Text(), nullable=True),
        sa.Column("checker_signature_status", sa.String(length=20), nullable=True),
        sa.Column("checker_signature_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("checker_signature_remarks", sa.Text(), nullable=True),
        sa.Column("receiver_stamp_status", sa.String(length=20), nullable=True),
        sa.Column("receiver_stamp_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("receiver_stamp_remarks", sa.Text(), nullable=True),
        sa.Column("stamp_text_raw", sa.Text(), nullable=True),
        sa.Column("stamp_text_normalized", sa.String(length=255), nullable=True),
        sa.Column("stamp_customer_match_status", sa.String(length=20), nullable=True),
        sa.Column("stamp_customer_match_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("stamp_customer_match_remarks", sa.Text(), nullable=True),
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("review_reasons", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_document_control_evidence_review_required", "document_control_evidence", ["review_required"])


def downgrade() -> None:
    op.drop_index("ix_document_control_evidence_review_required", table_name="document_control_evidence")
    op.drop_table("document_control_evidence")
