"""Backfill branch ownership for legacy root records.

Revision ID: 0010_branch_backfill
Revises: 0009_branch_access
Create Date: 2026-09-21
"""

from alembic import op

revision = "0010_branch_backfill"
down_revision = "0009_branch_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only infer a branch when the historical actor/uploader maps to exactly the
    # application user profile. Unresolved legacy rows stay NULL and therefore
    # remain ADMIN-only under the branch RLS/read rules.
    op.execute(
        """
        update public.documents d
        set branch = upper(trim(ur.branch))
        from public.user_roles ur
        where d.branch is null
          and d.uploaded_by is not null
          and ur.user_id::text = d.uploaded_by::text
          and ur.branch is not null
          and trim(ur.branch) <> ''
        """
    )
    op.execute(
        """
        update public.import_batches b
        set branch = upper(trim(ur.branch))
        from public.user_roles ur
        where b.branch is null
          and b.uploaded_by is not null
          and ur.user_id::text = b.uploaded_by::text
          and ur.branch is not null
          and trim(ur.branch) <> ''
        """
    )
    op.execute(
        """
        update public.audit_trail a
        set branch = upper(trim(ur.branch))
        from public.user_roles ur
        where a.branch is null
          and a.actor is not null
          and ur.user_id::text = a.actor::text
          and ur.branch is not null
          and trim(ur.branch) <> ''
        """
    )


def downgrade() -> None:
    # Ownership backfill is data repair and intentionally not erased on rollback.
    pass
