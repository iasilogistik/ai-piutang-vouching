"""Initial foundation migration.

Schema-specific tables are intentionally deferred to TASK-002.
"""

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
