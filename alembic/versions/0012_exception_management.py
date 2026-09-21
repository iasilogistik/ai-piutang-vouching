"""Add structured audit exception management.

Revision ID: 0012_exception_management
Revises: 0011_branch_master
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_exception_management"
down_revision = "0011_branch_master"
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
                    where n.nspname = 'public'
                      and p.proname = 'current_app_role'
                  )
                  and exists (
                    select 1
                    from pg_proc p
                    join pg_namespace n on n.oid = p.pronamespace
                    where n.nspname = 'public'
                      and p.proname = 'current_app_branch'
                  )
                """
            )
        ).scalar()
    )


def upgrade() -> None:
    op.create_table(
        "audit_exceptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="OPEN"),
        sa.Column("owner", sa.String(length=100), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("auditor_note", sa.Text(), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "type in ('BILLING_MISSING','SPJ_MISSING','AMOUNT_MISMATCH','CUSTOMER_MISMATCH','DATE_MISMATCH','DUPLICATE_DOCUMENT','PHYSICAL_DOCUMENT_MISSING','SAP_DATA_MISSING','EVIDENCE_MISSING')",
            name="ck_audit_exceptions_type",
        ),
        sa.CheckConstraint(
            "severity in ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_audit_exceptions_severity",
        ),
        sa.CheckConstraint(
            "status in ('OPEN','IN_PROGRESS','RESOLVED','CLOSED')",
            name="ck_audit_exceptions_status",
        ),
        schema="public",
    )
    op.create_index("ix_audit_exceptions_branch", "audit_exceptions", ["branch"], schema="public")
    op.create_index("ix_audit_exceptions_status", "audit_exceptions", ["status"], schema="public")
    op.create_index("ix_audit_exceptions_type", "audit_exceptions", ["type"], schema="public")
    op.create_index("ix_audit_exceptions_due_date", "audit_exceptions", ["due_date"], schema="public")

    op.execute("alter table public.audit_exceptions enable row level security")
    if _supabase_authenticated_available():
        op.execute("revoke all on public.audit_exceptions from anon, authenticated")
        op.execute("revoke all on sequence public.audit_exceptions_id_seq from anon, authenticated")
        op.execute("grant select, insert, update on public.audit_exceptions to authenticated")
        op.execute("grant usage, select on sequence public.audit_exceptions_id_seq to authenticated")
        op.execute(
            """
            create policy "app_read_audit_exceptions" on public.audit_exceptions
            for select to authenticated
            using (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or branch = (select public.current_app_branch())
            )
            """
        )
        op.execute(
            """
            create policy "app_insert_audit_exceptions" on public.audit_exceptions
            for insert to authenticated
            with check (
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
            """
        )
        op.execute(
            """
            create policy "app_update_audit_exceptions" on public.audit_exceptions
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
    op.execute('drop policy if exists "app_update_audit_exceptions" on public.audit_exceptions')
    op.execute('drop policy if exists "app_insert_audit_exceptions" on public.audit_exceptions')
    op.execute('drop policy if exists "app_read_audit_exceptions" on public.audit_exceptions')
    op.drop_index("ix_audit_exceptions_due_date", table_name="audit_exceptions", schema="public")
    op.drop_index("ix_audit_exceptions_type", table_name="audit_exceptions", schema="public")
    op.drop_index("ix_audit_exceptions_status", table_name="audit_exceptions", schema="public")
    op.drop_index("ix_audit_exceptions_branch", table_name="audit_exceptions", schema="public")
    op.drop_table("audit_exceptions", schema="public")
