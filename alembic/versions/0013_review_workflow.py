"""Add audit review workflow.

Revision ID: 0013_review_workflow
Revises: 0012_exception_management
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0013_review_workflow"
down_revision = "0012_exception_management"
branch_labels = None
depends_on = None


def _supabase_authenticated_available() -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                """
                select
                  exists (select 1 from pg_roles where rolname = 'authenticated')
                  and exists (
                    select 1
                    from pg_proc p
                    join pg_namespace n on n.oid = p.pronamespace
                    where n.nspname = 'public' and p.proname = 'current_app_role'
                  )
                  and exists (
                    select 1
                    from pg_proc p
                    join pg_namespace n on n.oid = p.pronamespace
                    where n.nspname = 'public' and p.proname = 'current_app_branch'
                  )
                """
            )
        ).scalar()
    )


def upgrade() -> None:
    op.create_table(
        "review_workflows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="NEW"),
        sa.Column("auditor_id", sa.String(length=100), nullable=True),
        sa.Column("reviewer_id", sa.String(length=100), nullable=True),
        sa.Column("auditor_remarks", sa.Text(), nullable=True),
        sa.Column("reviewer_remarks", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("entity_type", "entity_id", name="uq_review_workflows_entity"),
        sa.CheckConstraint(
            "status in ('NEW','PROCESSING','EXCEPTION','AUDITOR_REVIEWED','REVIEWER_APPROVED','REVIEWER_REJECTED','CLOSED')",
            name="ck_review_workflows_status",
        ),
        schema="public",
    )
    op.create_index("ix_review_workflows_branch", "review_workflows", ["branch"], schema="public")
    op.create_index("ix_review_workflows_status", "review_workflows", ["status"], schema="public")

    op.execute("alter table public.review_workflows enable row level security")
    if _supabase_authenticated_available():
        op.execute("revoke all on public.review_workflows from anon, authenticated")
        op.execute("revoke all on sequence public.review_workflows_id_seq from anon, authenticated")
        op.execute("grant select, insert, update on public.review_workflows to authenticated")
        op.execute("grant usage, select on sequence public.review_workflows_id_seq to authenticated")

        op.execute(
            """
            create policy "app_read_review_workflows" on public.review_workflows
            for select to authenticated
            using (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or branch = (select public.current_app_branch())
            )
            """
        )
        op.execute(
            """
            create policy "app_insert_review_workflows" on public.review_workflows
            for insert to authenticated
            with check (
                (select public.current_app_role()) in (
                    'ADMIN'::public.app_role,
                    'AUDITOR'::public.app_role
                )
                and (
                    (select public.current_app_role()) = 'ADMIN'::public.app_role
                    or branch = (select public.current_app_branch())
                )
            )
            """
        )
        op.execute(
            """
            create policy "app_update_review_workflows" on public.review_workflows
            for update to authenticated
            using (
                (select public.current_app_role()) in (
                    'ADMIN'::public.app_role,
                    'AUDITOR'::public.app_role,
                    'REVIEWER'::public.app_role
                )
                and (
                    (select public.current_app_role()) = 'ADMIN'::public.app_role
                    or branch = (select public.current_app_branch())
                )
            )
            with check (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or branch = (select public.current_app_branch())
            )
            """
        )


def downgrade() -> None:
    op.execute('drop policy if exists "app_update_review_workflows" on public.review_workflows')
    op.execute('drop policy if exists "app_insert_review_workflows" on public.review_workflows')
    op.execute('drop policy if exists "app_read_review_workflows" on public.review_workflows')
    op.drop_index("ix_review_workflows_status", table_name="review_workflows", schema="public")
    op.drop_index("ix_review_workflows_branch", table_name="review_workflows", schema="public")
    op.drop_table("review_workflows", schema="public")
