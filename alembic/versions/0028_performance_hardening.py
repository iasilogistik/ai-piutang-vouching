"""Harden production query performance without changing access semantics.

Revision ID: 0028_performance_hardening
Revises: 0027_release_schema_revision
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0028_performance_hardening"
down_revision = "0027_release_schema_revision"
branch_labels = None
depends_on = None


_INDEXES = (
    ("ix_audit_finding_evidence_control", "audit_finding_evidence", ["control_evidence_id"]),
    ("ix_audit_finding_evidence_document", "audit_finding_evidence", ["document_id"]),
    ("ix_audit_finding_exceptions_exception", "audit_finding_exceptions", ["audit_exception_id"]),
    ("ix_audit_finding_samples_sample", "audit_finding_samples", ["sample_id"]),
    ("ix_audit_finding_wps_working_paper", "audit_finding_working_papers", ["working_paper_id"]),
    ("ix_audit_samples_control_evidence", "audit_samples", ["control_evidence_id"]),
    ("ix_audit_samples_vouching_result", "audit_samples", ["vouching_result_id"]),
    ("ix_workflow_cases_audit_closing", "audit_workflow_cases", ["audit_closing_id"]),
    ("ix_workflow_cases_audit_exception", "audit_workflow_cases", ["audit_exception_id"]),
    ("ix_workflow_cases_audit_report", "audit_workflow_cases", ["audit_report_id"]),
    ("ix_workflow_cases_control_evidence", "audit_workflow_cases", ["control_evidence_id"]),
    ("ix_workflow_cases_review_workflow", "audit_workflow_cases", ["review_workflow_id"]),
    ("ix_wp_evidence_control_evidence", "audit_working_paper_evidence", ["control_evidence_id"]),
    ("ix_wp_evidence_document", "audit_working_paper_evidence", ["document_id"]),
    ("ix_wp_exceptions_audit_exception", "audit_working_paper_exceptions", ["audit_exception_id"]),
    ("ix_ca_evidence_control_evidence", "corrective_action_evidence", ["control_evidence_id"]),
    ("ix_ca_evidence_document", "corrective_action_evidence", ["document_id"]),
    ("ix_corrective_action_plans_response", "corrective_action_plans", ["response_id"]),
)


def _supabase_auth_available() -> bool:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    return bool(
        bind.execute(
            sa.text(
                """
                select
                  exists (select 1 from pg_roles where rolname='authenticated')
                  and exists (
                    select 1
                    from pg_proc p
                    join pg_namespace n on n.oid=p.pronamespace
                    where n.nspname='auth' and p.proname='uid'
                  )
                """
            )
        ).scalar()
    )


def _replace_notification_policies(*, init_plan: bool) -> None:
    uid = "(select auth.uid())::text" if init_plan else "auth.uid()::text"

    op.execute('drop policy if exists "notification_owner_read" on public.audit_notifications')
    op.execute('drop policy if exists "notification_owner_update" on public.audit_notifications')
    op.execute('drop policy if exists "notification_preferences_owner" on public.notification_preferences')

    op.execute(
        f"""
        create policy "notification_owner_read"
        on public.audit_notifications for select to authenticated
        using (user_id = {uid})
        """
    )
    op.execute(
        f"""
        create policy "notification_owner_update"
        on public.audit_notifications for update to authenticated
        using (user_id = {uid})
        with check (user_id = {uid})
        """
    )
    op.execute(
        f"""
        create policy "notification_preferences_owner"
        on public.notification_preferences for all to authenticated
        using (user_id = {uid})
        with check (user_id = {uid})
        """
    )


def upgrade() -> None:
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)

    if _supabase_auth_available():
        _replace_notification_policies(init_plan=True)


def downgrade() -> None:
    if _supabase_auth_available():
        _replace_notification_policies(init_plan=False)

    for name, table, _columns in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
