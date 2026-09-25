"""Consolidate overlapping permissive RLS policies without changing authorization semantics.

Revision ID: 0033_rls_policy_consolidation
Revises: 0031_revision_helper_acl
Create Date: 2026-09-22

IMPORTANT: This migration is prepared for PERF-02 but must not be applied to
production until live four-role RBAC UAT has passed and the before/after
authorization matrix is captured.
"""

from alembic import op
import sqlalchemy as sa

revision = "0033_rls_policy_consolidation"
down_revision = "0032_dynamic_branch_scope"
branch_labels = None
depends_on = None


_POLICIES = (
    ("audit_engagement_assignments", "admin_manage_audit_engagement_assignments", "(( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role)", "(( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role)"),
    ("audit_finding_evidence", "auditor_manage_audit_finding_evidence", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_evidence.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_evidence.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("audit_finding_exceptions", "auditor_manage_audit_finding_exceptions", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_exceptions.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_exceptions.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("audit_finding_samples", "auditor_manage_audit_finding_samples", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_samples.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_samples.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("audit_finding_versions", "app_manage_audit_finding_versions", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_versions.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_versions.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("audit_finding_working_papers", "auditor_manage_audit_finding_working_papers", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_working_papers.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM audit_findings f\n  WHERE ((f.id = audit_finding_working_papers.finding_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM f.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("audit_findings", "auditor_reviewer_manage_audit_findings", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("audit_populations", "auditor_manage_audit_populations", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("audit_samples", "auditor_manage_audit_samples", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("audit_working_paper_evidence", "auditor_manage_audit_working_paper_evidence", "(EXISTS ( SELECT 1\n   FROM audit_working_papers wp\n  WHERE ((wp.id = audit_working_paper_evidence.working_paper_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM wp.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM audit_working_papers wp\n  WHERE ((wp.id = audit_working_paper_evidence.working_paper_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM wp.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("audit_working_paper_exceptions", "auditor_manage_audit_working_paper_exceptions", "(EXISTS ( SELECT 1\n   FROM audit_working_papers wp\n  WHERE ((wp.id = audit_working_paper_exceptions.working_paper_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM wp.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM audit_working_papers wp\n  WHERE ((wp.id = audit_working_paper_exceptions.working_paper_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM wp.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("audit_working_paper_versions", "app_manage_audit_working_paper_versions", "(EXISTS ( SELECT 1\n   FROM audit_working_papers wp\n  WHERE ((wp.id = audit_working_paper_versions.working_paper_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM wp.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM audit_working_papers wp\n  WHERE ((wp.id = audit_working_paper_versions.working_paper_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM wp.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("audit_working_papers", "auditor_manage_audit_working_papers", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("corrective_action_evidence", "app_manage_corrective_action_evidence", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("corrective_action_plan_history", "app_manage_corrective_action_plan_history", "(EXISTS ( SELECT 1\n   FROM corrective_action_plans p\n  WHERE ((p.id = corrective_action_plan_history.action_plan_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM p.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM corrective_action_plans p\n  WHERE ((p.id = corrective_action_plan_history.action_plan_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM p.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("corrective_action_plans", "app_manage_corrective_action_plans", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("corrective_action_progress_updates", "app_manage_corrective_action_progress_updates", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("corrective_action_verifications", "app_manage_corrective_action_verifications", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("evidence_resource_links", "auditor_manage_evidence_resource_links", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
    ("management_response_versions", "app_manage_management_response_versions", "(EXISTS ( SELECT 1\n   FROM management_responses p\n  WHERE ((p.id = management_response_versions.response_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM p.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))", "(EXISTS ( SELECT 1\n   FROM management_responses p\n  WHERE ((p.id = management_response_versions.response_id) AND (( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM p.branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))))"),
    ("management_responses", "app_manage_management_responses", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))", "((( SELECT current_app_role() AS current_app_role) = ANY (ARRAY['ADMIN'::app_role, 'AUDITOR'::app_role, 'REVIEWER'::app_role])) AND ((( SELECT current_app_role() AS current_app_role) = 'ADMIN'::app_role) OR (upper(TRIM(BOTH FROM branch)) = (( SELECT current_app_branch() AS current_app_branch))::text)))"),
)


def _supabase_rbac_available() -> bool:
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
                    from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                    where n.nspname='public' and p.proname='current_app_role'
                  )
                  and exists (
                    select 1
                    from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                    where n.nspname='public' and p.proname='current_app_branch'
                  )
                """
            )
        ).scalar()
    )


def _split_policy(table: str, policy: str, using_expr: str, check_expr: str) -> None:
    op.execute(f'drop policy if exists "{policy}" on public.{table}')

    op.execute(
        f"""
        create policy "{policy}_insert"
        on public.{table} for insert to authenticated
        with check ({check_expr})
        """
    )
    op.execute(
        f"""
        create policy "{policy}_update"
        on public.{table} for update to authenticated
        using ({using_expr})
        with check ({check_expr})
        """
    )
    op.execute(
        f"""
        create policy "{policy}_delete"
        on public.{table} for delete to authenticated
        using ({using_expr})
        """
    )


def _restore_policy(table: str, policy: str, using_expr: str, check_expr: str) -> None:
    for suffix in ("insert", "update", "delete"):
        op.execute(f'drop policy if exists "{policy}_{suffix}" on public.{table}')

    op.execute(
        f"""
        create policy "{policy}"
        on public.{table} for all to authenticated
        using ({using_expr})
        with check ({check_expr})
        """
    )


def upgrade() -> None:
    if not _supabase_rbac_available():
        return

    for table, policy, using_expr, check_expr in _POLICIES:
        _split_policy(table, policy, using_expr, check_expr)


def downgrade() -> None:
    if not _supabase_rbac_available():
        return

    for table, policy, using_expr, check_expr in reversed(_POLICIES):
        _restore_policy(table, policy, using_expr, check_expr)
