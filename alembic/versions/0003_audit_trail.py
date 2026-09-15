"""Add immutable audit trail."""

from alembic import op
import sqlalchemy as sa

revision = "0003_audit_trail"
down_revision = "0002_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_trail",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Integer()),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("status_from", sa.String(30)),
        sa.Column("status_to", sa.String(30)),
        sa.Column("actor", sa.String(100)),
        sa.Column("remarks", sa.Text()),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_trail_entity", "audit_trail", ["entity_type", "entity_id"])
    op.create_index("ix_audit_trail_created_at", "audit_trail", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_trail_created_at", table_name="audit_trail")
    op.drop_index("ix_audit_trail_entity", table_name="audit_trail")
    op.drop_table("audit_trail")
