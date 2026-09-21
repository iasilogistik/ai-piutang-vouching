"""Add branch-level access control.

Revision ID: 0009_branch_access
Revises: 0008_user_roles
Create Date: 2026-09-21
"""

from alembic import op

revision = "0009_branch_access"
down_revision = "0008_user_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table public.documents add column if not exists branch varchar(255)")
    op.execute("alter table public.import_batches add column if not exists branch varchar(255)")
    op.execute("alter table public.audit_trail add column if not exists branch varchar(255)")
    op.execute("create index if not exists ix_documents_branch on public.documents(branch)")
    op.execute("create index if not exists ix_import_batches_branch on public.import_batches(branch)")
    op.execute("create index if not exists ix_audit_trail_branch on public.audit_trail(branch)")

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
          where ur.user_id = (select auth.uid())
        $$;
        """
    )

    # Replace broad authenticated policies with branch-aware policies.
    for table in ("documents", "import_batches", "audit_trail"):
        op.execute(f'drop policy if exists "app_read_{table}" on public.{table}')

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

    # Child table read policies inherit branch ownership from their parent.
    for table in ("sap_billing", "physical_billing", "billing_reconciliation", "spj", "vouching_result", "document_control_evidence"):
        op.execute(f'drop policy if exists "app_read_{table}" on public.{table}')

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


def downgrade() -> None:
    op.execute('drop policy if exists "app_read_document_control_evidence" on public.document_control_evidence')
    op.execute('drop function if exists public.current_app_branch()')
    op.execute("drop index if exists public.ix_audit_trail_branch")
    op.execute("drop index if exists public.ix_import_batches_branch")
    op.execute("drop index if exists public.ix_documents_branch")
    op.execute("alter table public.audit_trail drop column if exists branch")
    op.execute("alter table public.import_batches drop column if exists branch")
    op.execute("alter table public.documents drop column if exists branch")
