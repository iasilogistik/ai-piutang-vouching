"""Create canonical branch master.

Revision ID: 0011_branch_master
Revises: 0010_branch_backfill
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_branch_master"
down_revision = "0010_branch_backfill"
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
                """
            )
        ).scalar()
    )



def upgrade() -> None:
    op.create_table(
        "branches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_code", sa.String(length=50), nullable=False),
        sa.Column("branch_name", sa.String(length=255), nullable=False),
        sa.Column("region", sa.String(length=255), nullable=True),
        sa.Column("area", sa.String(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("branch_code", name="uq_branches_branch_code"),
        schema="public",
    )
    op.create_index("ix_branches_active", "branches", ["active"], schema="public")

    # Seed the master from branch values already in use so current production
    # ownership remains valid after this table is introduced.
    op.execute("""
        insert into public.branches (branch_code, branch_name)
        select branch_code, branch_code
        from (
            select distinct upper(trim(branch)) as branch_code from public.user_roles where branch is not null and trim(branch) <> ''
            union
            select distinct upper(trim(branch)) as branch_code from public.documents where branch is not null and trim(branch) <> ''
            union
            select distinct upper(trim(branch)) as branch_code from public.import_batches where branch is not null and trim(branch) <> ''
            union
            select distinct upper(trim(branch)) as branch_code from public.audit_trail where branch is not null and trim(branch) <> ''
        ) seeded
        where branch_code is not null and branch_code <> ''
        on conflict (branch_code) do nothing
    """)

    op.execute("alter table public.branches enable row level security")
    if _supabase_authenticated_available():
        op.execute("revoke all on public.branches from anon, authenticated")
        op.execute("revoke all on sequence public.branches_id_seq from anon, authenticated")
        op.execute("grant select, insert, update on public.branches to authenticated")
        op.execute("grant usage, select on sequence public.branches_id_seq to authenticated")
        op.execute("""
            create policy "app_read_branches" on public.branches
            for select to authenticated
            using (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or (
                    active = true
                    and branch_code = (select public.current_app_branch())
                )
            )
        """)
        op.execute("""
            create policy "admin_insert_branches" on public.branches
            for insert to authenticated
            with check ((select public.current_app_role()) = 'ADMIN'::public.app_role)
        """)
        op.execute("""
            create policy "admin_update_branches" on public.branches
            for update to authenticated
            using ((select public.current_app_role()) = 'ADMIN'::public.app_role)
            with check ((select public.current_app_role()) = 'ADMIN'::public.app_role)
        """)


def downgrade() -> None:
    op.execute('drop policy if exists "admin_update_branches" on public.branches')
    op.execute('drop policy if exists "admin_insert_branches" on public.branches')
    op.execute('drop policy if exists "app_read_branches" on public.branches')
    op.drop_index("ix_branches_active", table_name="branches", schema="public")
    op.drop_table("branches", schema="public")
