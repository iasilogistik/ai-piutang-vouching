"""Add partial payment fields for physical Billing and SPJ."""

from alembic import op
import sqlalchemy as sa

revision = "0004_partial_payment"
down_revision = "0003_audit_trail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("physical_billing", sa.Column("partial_payment_raw", sa.Text(), nullable=True))
    op.add_column("physical_billing", sa.Column("partial_payment", sa.Numeric(20, 2), nullable=True))
    op.add_column("spj", sa.Column("partial_payment_raw", sa.Text(), nullable=True))
    op.add_column("spj", sa.Column("partial_payment", sa.Numeric(20, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("spj", "partial_payment")
    op.drop_column("spj", "partial_payment_raw")
    op.drop_column("physical_billing", "partial_payment")
    op.drop_column("physical_billing", "partial_payment_raw")
