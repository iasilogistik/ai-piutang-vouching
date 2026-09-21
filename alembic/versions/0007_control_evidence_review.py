"""add manual review fields to document control evidence

Revision ID: 0007_control_evidence_review
Revises: 0006_document_control_evidence
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_control_evidence_review"
down_revision = "0006_document_control_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_control_evidence", sa.Column("review_status", sa.String(length=20), nullable=True))
    op.add_column("document_control_evidence", sa.Column("reviewer_id", sa.String(length=100), nullable=True))
    op.add_column("document_control_evidence", sa.Column("reviewer_remarks", sa.Text(), nullable=True))
    op.add_column("document_control_evidence", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_document_control_evidence_review_status", "document_control_evidence", ["review_status"])


def downgrade() -> None:
    op.drop_index("ix_document_control_evidence_review_status", table_name="document_control_evidence")
    op.drop_column("document_control_evidence", "reviewed_at")
    op.drop_column("document_control_evidence", "reviewer_remarks")
    op.drop_column("document_control_evidence", "reviewer_id")
    op.drop_column("document_control_evidence", "review_status")
