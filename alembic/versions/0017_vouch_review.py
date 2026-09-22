"""Separate automated and manual vouching review.

Revision ID: 0017_vouch_review
Revises: 0016_control_evidence_detect
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_vouch_review"
down_revision = "0016_control_evidence_detect"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vouching_result", sa.Column("automated_status", sa.String(length=20), nullable=True))
    op.add_column("vouching_result", sa.Column("automated_rule_code", sa.String(length=50), nullable=True))
    op.add_column("vouching_result", sa.Column("automated_remarks", sa.Text(), nullable=True))
    op.add_column("vouching_result", sa.Column("manual_review_status", sa.String(length=20), nullable=True))
    op.add_column("vouching_result", sa.Column("review_reason_code", sa.String(length=50), nullable=True))
    op.add_column("vouching_result", sa.Column("reviewer_remarks", sa.Text(), nullable=True))
    op.add_column("vouching_result", sa.Column("expected_customer_name", sa.String(length=255), nullable=True))
    op.add_column("vouching_result", sa.Column("control_evidence_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_vouching_result_control_evidence",
        "vouching_result",
        "document_control_evidence",
        ["control_evidence_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_vouching_result_manual_review_status", "vouching_result", ["manual_review_status"])
    op.create_index("ix_vouching_result_review_reason_code", "vouching_result", ["review_reason_code"])
    op.create_index("ix_vouching_result_control_evidence_id", "vouching_result", ["control_evidence_id"])

    op.execute(
        """
        update vouching_result
        set automated_status = status,
            automated_rule_code = rule_code,
            automated_remarks = case when reviewer_id is null then remarks else null end,
            manual_review_status = case when reviewer_id is not null then status else null end,
            reviewer_remarks = case when reviewer_id is not null then remarks else null end
        """
    )


def downgrade() -> None:
    op.drop_index("ix_vouching_result_control_evidence_id", table_name="vouching_result")
    op.drop_index("ix_vouching_result_review_reason_code", table_name="vouching_result")
    op.drop_index("ix_vouching_result_manual_review_status", table_name="vouching_result")
    op.drop_constraint("fk_vouching_result_control_evidence", "vouching_result", type_="foreignkey")
    op.drop_column("vouching_result", "control_evidence_id")
    op.drop_column("vouching_result", "expected_customer_name")
    op.drop_column("vouching_result", "reviewer_remarks")
    op.drop_column("vouching_result", "review_reason_code")
    op.drop_column("vouching_result", "manual_review_status")
    op.drop_column("vouching_result", "automated_remarks")
    op.drop_column("vouching_result", "automated_rule_code")
    op.drop_column("vouching_result", "automated_status")
