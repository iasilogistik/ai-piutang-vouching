"""Add branch-level access control.

Revision ID: 0009_branch_access
Revises: 0008_user_roles
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_branch_access"
down_revision = "0008_user_roles"
branch_labels = None
depends_on = None

_READ_TABLES = (
    "documents",
    "import_batches",
    "audit_trail",
    "sap_billing",
    "physical_billing",
    "billing_reconciliation",
    "spj",
    "vouching_result",
    "document_control_evidence",
)


def _supabase_rbac_available() -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                """
                select
                  exists (
                    select 1
                    from pg_proc p
                    join pg_namespace n on n.oid = p.pronamespace
                    where n.nspname = 'auth' and p.proname = 'uid'
                  )
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


def _drop_branch_policies() -> None:
    for table in _READ_TABLES:
        op.execute(f'drop policy if exists "app_read_{table}" on public.{table}')
    for table, policy in (
        ("documents", "auditor_insert_documents"),
        ("import_batches", "auditor_insert_import_batches"),
        ("sap_billing", "auditor_insert_sap_billing"),
        ("physical_billing", "auditor_insert_physical_billing"),
        ("spj", "auditor_insert_spj"),
        ("billing_reconciliation", "auditor_insert_reconciliation"),
        ("billing_reconciliation", "auditor_update_reconciliation"),
        ("vouching_result", "reviewer_insert_vouching"),
        ("vouching_result", "reviewer_update_vouching"),
        ("audit_trail", "app_insert_audit_trail"),
    ):
        op.execute(f'drop policy if exists "{policy}" on public.{table}')


def _install_branch_policies() -> None:
    # Keep database-side authorization aligned with FastAPI: inactive users
    # must not retain access through an already-issued Supabase access token.
    op.execute(
        """
        create or replace function public.current_app_role()
        returns public.app_role
        language sql
        stable
        set search_path = ''
        as $
          select coalesce(
            (
              select ur.role
              from public.user_roles ur
              where ur.user_id::text = (select auth.uid())::text
                and coalesce(ur.is_active, true)
            ),
            'VIEWER'::public.app_role
          )
        $;
        """
    )
    op.execute(
        """
        create or replace function public.current_app_branch()
        returns varchar
        language sql
        stable
        set search_path = ''
        as $$
          select upper(trim(ur.branch))
          from public.user_roles ur
          where ur.user_id::text = (select auth.uid())::text
            and coalesce(ur.is_active, true)
        $;
        """
    )

    for table in _READ_TABLES:
        op.execute(f"alter table public.{table} enable row level security")

    _drop_branch_policies()

    # Root-table reads.
    op.execute(
        """
        create policy "app_read_documents" on public.documents for select to authenticated
        using (
          (select public.current_app_role()) = 'ADMIN'::public.app_role
          or upper(trim(branch)) = (select public.current_app_branch())
        )
        """
    )
    op.execute(
        """
        create policy "app_read_import_batches" on public.import_batches for select to authenticated
        using (
          (select public.current_app_role()) = 'ADMIN'::public.app_role
          or upper(trim(branch)) = (select public.current_app_branch())
        )
        """
    )
    op.execute(
        """
        create policy "app_read_audit_trail" on public.audit_trail for select to authenticated
        using (
          (select public.current_app_role()) = 'ADMIN'::public.app_role
          or upper(trim(branch)) = (select public.current_app_branch())
        )
        """
    )

    # Child-table reads inherit branch ownership from their root parent.
    op.execute(
        """
        create policy "app_read_sap_billing" on public.sap_billing for select to authenticated
        using (
          (select public.current_app_role()) = 'ADMIN'::public.app_role
          or exists (
            select 1 from public.import_batches b
            where b.id = sap_billing.import_batch_id
              and upper(trim(b.branch)) = (select public.current_app_branch())
          )
        )
        """
    )
    op.execute(
        """
        create policy "app_read_physical_billing" on public.physical_billing for select to authenticated
        using (
          (select public.current_app_role()) = 'ADMIN'::public.app_role
          or exists (
            select 1 from public.documents d
            where d.id = physical_billing.document_id
              and upper(trim(d.branch)) = (select public.current_app_branch())
          )
        )
        """
    )
    op.execute(
        """
        create policy "app_read_spj" on public.spj for select to authenticated
        using (
          (select public.current_app_role()) = 'ADMIN'::public.app_role
          or exists (
            select 1 from public.documents d
            where d.id = spj.document_id
              and upper(trim(d.branch)) = (select public.current_app_branch())
          )
        )
        """
    )
    op.execute(
        """
        create policy "app_read_billing_reconciliation" on public.billing_reconciliation for select to authenticated
        using (
          (select public.current_app_role()) = 'ADMIN'::public.app_role
          or exists (
            select 1
            from public.sap_billing s
            join public.import_batches b on b.id = s.import_batch_id
            where s.id = billing_reconciliation.sap_billing_id
              and upper(trim(b.branch)) = (select public.current_app_branch())
          )
        )
        """
    )
    op.execute(
        """
        create policy "app_read_vouching_result" on public.vouching_result for select to authenticated
        using (
          (select public.current_app_role()) = 'ADMIN'::public.app_role
          or exists (
            select 1
            from public.physical_billing pb
            join public.documents d on d.id = pb.document_id
            where pb.id = vouching_result.billing_id
              and upper(trim(d.branch)) = (select public.current_app_branch())
          )
        )
        """
    )
    op.execute(
        """
        create policy "app_read_document_control_evidence" on public.document_control_evidence for select to authenticated
        using (
          (select public.current_app_role()) = 'ADMIN'::public.app_role
          or exists (
            select 1 from public.documents d
            where d.id = document_control_evidence.document_id
              and upper(trim(d.branch)) = (select public.current_app_branch())
          )
        )
        """
    )

    # Root-table writes: role AND branch must both be authorized.
    op.execute(
        """
        create policy "auditor_insert_documents" on public.documents for insert to authenticated
        with check (
          (select public.current_app_role()) = any (
            array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]
          )
          and (
            (select public.current_app_role()) = 'ADMIN'::public.app_role
            or upper(trim(branch)) = (select public.current_app_branch())
          )
        )
        """
    )
    op.execute(
        """
        create policy "auditor_insert_import_batches" on public.import_batches for insert to authenticated
        with check (
          (select public.current_app_role()) = any (
            array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]
          )
          and (
            (select public.current_app_role()) = 'ADMIN'::public.app_role
            or upper(trim(branch)) = (select public.current_app_branch())
          )
        )
        """
    )
    op.execute(
        """
        create policy "app_insert_audit_trail" on public.audit_trail for insert to authenticated
        with check (
          (select public.current_app_role()) = any (
            array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role, 'REVIEWER'::public.app_role]
          )
          and (
            (select public.current_app_role()) = 'ADMIN'::public.app_role
            or upper(trim(branch)) = (select public.current_app_branch())
          )
        )
        """
    )

    # Child-table writes must point to a parent in the caller's branch.
    op.execute(
        """
        create policy "auditor_insert_sap_billing" on public.sap_billing for insert to authenticated
        with check (
          (select public.current_app_role()) = any (
            array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]
          )
          and exists (
            select 1 from public.import_batches b
            where b.id = sap_billing.import_batch_id
              and (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or upper(trim(b.branch)) = (select public.current_app_branch())
              )
          )
        )
        """
    )
    op.execute(
        """
        create policy "auditor_insert_physical_billing" on public.physical_billing for insert to authenticated
        with check (
          (select public.current_app_role()) = any (
            array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]
          )
          and exists (
            select 1 from public.documents d
            where d.id = physical_billing.document_id
              and (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or upper(trim(d.branch)) = (select public.current_app_branch())
              )
          )
        )
        """
    )
    op.execute(
        """
        create policy "auditor_insert_spj" on public.spj for insert to authenticated
        with check (
          (select public.current_app_role()) = any (
            array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]
          )
          and exists (
            select 1 from public.documents d
            where d.id = spj.document_id
              and (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or upper(trim(d.branch)) = (select public.current_app_branch())
              )
          )
        )
        """
    )
    op.execute(
        """
        create policy "auditor_insert_reconciliation" on public.billing_reconciliation for insert to authenticated
        with check (
          (select public.current_app_role()) = any (
            array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]
          )
          and exists (
            select 1
            from public.sap_billing s
            join public.import_batches b on b.id = s.import_batch_id
            where s.id = billing_reconciliation.sap_billing_id
              and (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or upper(trim(b.branch)) = (select public.current_app_branch())
              )
          )
        )
        """
    )
    op.execute(
        """
        create policy "auditor_update_reconciliation" on public.billing_reconciliation for update to authenticated
        using (
          (select public.current_app_role()) = any (
            array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]
          )
          and exists (
            select 1
            from public.sap_billing s
            join public.import_batches b on b.id = s.import_batch_id
            where s.id = billing_reconciliation.sap_billing_id
              and (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or upper(trim(b.branch)) = (select public.current_app_branch())
              )
          )
        )
        with check (
          (select public.current_app_role()) = any (
            array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]
          )
          and exists (
            select 1
            from public.sap_billing s
            join public.import_batches b on b.id = s.import_batch_id
            where s.id = billing_reconciliation.sap_billing_id
              and (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or upper(trim(b.branch)) = (select public.current_app_branch())
              )
          )
        )
        """
    )
    op.execute(
        """
        create policy "reviewer_insert_vouching" on public.vouching_result for insert to authenticated
        with check (
          (select public.current_app_role()) = any (
            array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role, 'REVIEWER'::public.app_role]
          )
          and exists (
            select 1
            from public.physical_billing pb
            join public.documents d on d.id = pb.document_id
            where pb.id = vouching_result.billing_id
              and (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or upper(trim(d.branch)) = (select public.current_app_branch())
              )
          )
        )
        """
    )
    op.execute(
        """
        create policy "reviewer_update_vouching" on public.vouching_result for update to authenticated
        using (
          (select public.current_app_role()) = any (
            array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role, 'REVIEWER'::public.app_role]
          )
          and exists (
            select 1
            from public.physical_billing pb
            join public.documents d on d.id = pb.document_id
            where pb.id = vouching_result.billing_id
              and (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or upper(trim(d.branch)) = (select public.current_app_branch())
              )
          )
        )
        with check (
          (select public.current_app_role()) = any (
            array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role, 'REVIEWER'::public.app_role]
          )
          and exists (
            select 1
            from public.physical_billing pb
            join public.documents d on d.id = pb.document_id
            where pb.id = vouching_result.billing_id
              and (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or upper(trim(d.branch)) = (select public.current_app_branch())
              )
          )
        )
        """
    )


def _restore_previous_policies() -> None:
    _drop_branch_policies()

    for table in (
        "documents",
        "import_batches",
        "audit_trail",
        "sap_billing",
        "physical_billing",
        "billing_reconciliation",
        "spj",
        "vouching_result",
    ):
        op.execute(
            f'''
            create policy "app_read_{table}" on public.{table} for select to authenticated
            using ((select auth.uid()) is not null)
            '''
        )

    op.execute(
        """
        create policy "auditor_insert_documents" on public.documents for insert to authenticated
        with check ((select public.current_app_role()) = any (array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]))
        """
    )
    op.execute(
        """
        create policy "auditor_insert_import_batches" on public.import_batches for insert to authenticated
        with check ((select public.current_app_role()) = any (array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]))
        """
    )
    op.execute(
        """
        create policy "auditor_insert_sap_billing" on public.sap_billing for insert to authenticated
        with check ((select public.current_app_role()) = any (array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]))
        """
    )
    op.execute(
        """
        create policy "auditor_insert_physical_billing" on public.physical_billing for insert to authenticated
        with check ((select public.current_app_role()) = any (array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]))
        """
    )
    op.execute(
        """
        create policy "auditor_insert_spj" on public.spj for insert to authenticated
        with check ((select public.current_app_role()) = any (array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]))
        """
    )
    op.execute(
        """
        create policy "auditor_insert_reconciliation" on public.billing_reconciliation for insert to authenticated
        with check ((select public.current_app_role()) = any (array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]))
        """
    )
    op.execute(
        """
        create policy "auditor_update_reconciliation" on public.billing_reconciliation for update to authenticated
        using ((select public.current_app_role()) = any (array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]))
        with check ((select public.current_app_role()) = any (array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]))
        """
    )
    op.execute(
        """
        create policy "reviewer_insert_vouching" on public.vouching_result for insert to authenticated
        with check ((select public.current_app_role()) = any (array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role, 'REVIEWER'::public.app_role]))
        """
    )
    op.execute(
        """
        create policy "reviewer_update_vouching" on public.vouching_result for update to authenticated
        using ((select public.current_app_role()) = any (array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role, 'REVIEWER'::public.app_role]))
        with check ((select public.current_app_role()) = any (array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role, 'REVIEWER'::public.app_role]))
        """
    )
    op.execute(
        """
        create policy "app_insert_audit_trail" on public.audit_trail for insert to authenticated
        with check ((select public.current_app_role()) = any (array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role, 'REVIEWER'::public.app_role]))
        """
    )


def upgrade() -> None:
    op.execute("alter table public.documents add column if not exists branch varchar(255)")
    op.execute("alter table public.import_batches add column if not exists branch varchar(255)")
    op.execute("alter table public.audit_trail add column if not exists branch varchar(255)")
    op.execute("create index if not exists ix_documents_branch on public.documents(branch)")
    op.execute("create index if not exists ix_import_batches_branch on public.import_batches(branch)")
    op.execute("create index if not exists ix_audit_trail_branch on public.audit_trail(branch)")

    # CI/local PostgreSQL does not include Supabase auth/RBAC functions.
    # Install Data API RLS only when the Supabase primitives are present.
    if _supabase_rbac_available():
        _install_branch_policies()


def downgrade() -> None:
    if _supabase_rbac_available():
        _restore_previous_policies()
        op.execute("drop function if exists public.current_app_branch()")

    op.execute("drop index if exists public.ix_audit_trail_branch")
    op.execute("drop index if exists public.ix_import_batches_branch")
    op.execute("drop index if exists public.ix_documents_branch")
    op.execute("alter table public.audit_trail drop column if exists branch")
    op.execute("alter table public.import_batches drop column if exists branch")
    op.execute("alter table public.documents drop column if exists branch")
