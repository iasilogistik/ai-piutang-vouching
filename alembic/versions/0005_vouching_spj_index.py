"""Index vouching_result.spj_id for production query performance."""

from alembic import op

revision = "0005_vouching_spj_index"
down_revision = "0004_partial_payment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_vouching_result_spj_id", "vouching_result", ["spj_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_vouching_result_spj_id", table_name="vouching_result")
