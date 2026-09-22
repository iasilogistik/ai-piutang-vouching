"""Add structured audit finding management.

Revision ID: 0022_audit_findings
Revises: 0021_audit_working_papers
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0022_audit_findings"
down_revision = "0021_audit_working_papers"
branch_labels = None
depends_on = None


def _supabase_rbac_available() -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                """
                select
                  exists (
                    select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                    where n.nspname='public' and p.proname='current_app_role'
                  )
                  and exists (
                    select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                    where n.nspname='public' and p.proname='current_app_branch'
                  )
                """
            )
        ).scalar()
    )


def upgrade() -> None:
    op.create_table(
        "audit_findings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("engagement_id", sa.Integer(), sa.ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("reference", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("condition", sa.Text(), nullable=True),
        sa.Column("criteria", sa.Text(), nullable=True),
        sa.Column("cause", sa.Text(), nullable=True),
        sa.Column("effect_risk", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("preparer_id", sa.String(length=100), nullable=False),
        sa.Column("reviewer_id", sa.String(length=100), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("engagement_id", "reference", name="uq_audit_finding_reference"),
    )
    op.create_index("ix_audit_findings_engagement", "audit_findings", ["engagement_id"])
    op.create_index("ix_audit_findings_branch", "audit_findings", ["branch"])
    op.create_index("ix_audit_findings_status", "audit_findings", ["status"])
    op.create_index("ix_audit_findings_severity", "audit_findings", ["severity"])

    op.create_table(
        "audit_finding_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("finding_id", sa.Integer(), sa.ForeignKey("audit_findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("condition", sa.Text(), nullable=True),
        sa.Column("criteria", sa.Text(), nullable=True),
        sa.Column("cause", sa.Text(), nullable=True),
        sa.Column("effect_risk", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("changed_by", sa.String(length=100), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("finding_id", "version_number", name="uq_audit_finding_version"),
    )
    op.create_index("ix_audit_finding_versions_finding", "audit_finding_versions", ["finding_id"])

    op.create_table(
        "audit_finding_working_papers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("finding_id", sa.Integer(), sa.ForeignKey("audit_findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("working_paper_id", sa.Integer(), sa.ForeignKey("audit_working_papers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("linked_by", sa.String(length=100), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("finding_id", "working_paper_id", name="uq_audit_finding_working_paper"),
    )
    op.create_table(
        "audit_finding_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("finding_id", sa.Integer(), sa.ForeignKey("audit_findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("control_evidence_id", sa.Integer(), sa.ForeignKey("document_control_evidence.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("linked_by", sa.String(length=100), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(document_id is not null and control_evidence_id is null) or "
            "(document_id is null and control_evidence_id is not null)",
            name="ck_audit_finding_evidence_one_source",
        ),
        sa.UniqueConstraint("finding_id", "document_id", name="uq_audit_finding_document"),
        sa.UniqueConstraint("finding_id", "control_evidence_id", name="uq_audit_finding_control_evidence"),
    )
    op.create_table(
        "audit_finding_exceptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("finding_id", sa.Integer(), sa.ForeignKey("audit_findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("audit_exception_id", sa.Integer(), sa.ForeignKey("audit_exceptions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("linked_by", sa.String(length=100), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("finding_id", "audit_exception_id", name="uq_audit_finding_exception"),
    )
    op.create_table(
        "audit_finding_samples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("finding_id", sa.Integer(), sa.ForeignKey("audit_findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sample_id", sa.Integer(), sa.ForeignKey("audit_samples.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("linked_by", sa.String(length=100), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("finding_id", "sample_id", name="uq_audit_finding_sample"),
    )

    for table, column in (
        ("audit_finding_working_papers", "finding_id"),
        ("audit_finding_evidence", "finding_id"),
        ("audit_finding_exceptions", "finding_id"),
        ("audit_finding_samples", "finding_id"),
    ):
        op.create_index(f"ix_{table}_finding", table, [column])

    for table in (
        "audit_findings",
        "audit_finding_versions",
        "audit_finding_working_papers",
        "audit_finding_evidence",
        "audit_finding_exceptions",
        "audit_finding_samples",
    ):
        op.execute(f"alter table public.{table} enable row level security")

    if _supabase_rbac_available():
        op.execute("""
            create policy "app_read_audit_findings"
            on public.audit_findings for select to authenticated
            using (
              (select public.current_app_role()) = 'ADMIN'::public.app_role
              or upper(trim(branch)) = (select public.current_app_branch())
            )
        """)
        op.execute("""
            create policy "auditor_reviewer_manage_audit_findings"
            on public.audit_findings for all to authenticated
            using (
              (select public.current_app_role()) = any (
                array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role, 'REVIEWER'::public.app_role]
              )
              and (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or upper(trim(branch)) = (select public.current_app_branch())
              )
            )
            with check (
              (select public.current_app_role()) = any (
                array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role, 'REVIEWER'::public.app_role]
              )
              and (
                (select public.current_app_role()) = 'ADMIN'::public.app_role
                or upper(trim(branch)) = (select public.current_app_branch())
              )
            )
        """)
        for table in (
            "audit_finding_versions",
            "audit_finding_working_papers",
            "audit_finding_evidence",
            "audit_finding_exceptions",
            "audit_finding_samples",
        ):
            op.execute(
                f"""
                create policy "app_read_{table}"
                on public.{table} for select to authenticated
                using (
                  exists (
                    select 1 from public.audit_findings f
                    where f.id = finding_id
                      and (
                        (select public.current_app_role()) = 'ADMIN'::public.app_role
                        or upper(trim(f.branch)) = (select public.current_app_branch())
                      )
                  )
                )
                """
            )
        op.execute("""
            create policy "app_manage_audit_finding_versions"
            on public.audit_finding_versions for all to authenticated
            using (
              exists (
                select 1 from public.audit_findings f
                where f.id = finding_id
                  and (select public.current_app_role()) = any (
                    array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role, 'REVIEWER'::public.app_role]
                  )
                  and (
                    (select public.current_app_role()) = 'ADMIN'::public.app_role
                    or upper(trim(f.branch)) = (select public.current_app_branch())
                  )
              )
            )
            with check (
              exists (
                select 1 from public.audit_findings f
                where f.id = finding_id
                  and (select public.current_app_role()) = any (
                    array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role, 'REVIEWER'::public.app_role]
                  )
                  and (
                    (select public.current_app_role()) = 'ADMIN'::public.app_role
                    or upper(trim(f.branch)) = (select public.current_app_branch())
                  )
              )
            )
        """)
        for table in (
            "audit_finding_working_papers",
            "audit_finding_evidence",
            "audit_finding_exceptions",
            "audit_finding_samples",
        ):
            op.execute(
                f"""
                create policy "auditor_manage_{table}"
                on public.{table} for all to authenticated
                using (
                  exists (
                    select 1 from public.audit_findings f
                    where f.id = finding_id
                      and (select public.current_app_role()) = any (
                        array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]
                      )
                      and (
                        (select public.current_app_role()) = 'ADMIN'::public.app_role
                        or upper(trim(f.branch)) = (select public.current_app_branch())
                      )
                  )
                )
                with check (
                  exists (
                    select 1 from public.audit_findings f
                    where f.id = finding_id
                      and (select public.current_app_role()) = any (
                        array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]
                      )
                      and (
                        (select public.current_app_role()) = 'ADMIN'::public.app_role
                        or upper(trim(f.branch)) = (select public.current_app_branch())
                      )
                  )
                )
                """
            )


def downgrade() -> None:
    op.drop_table("audit_finding_samples")
    op.drop_table("audit_finding_exceptions")
    op.drop_table("audit_finding_evidence")
    op.drop_table("audit_finding_working_papers")
    op.drop_table("audit_finding_versions")
    op.drop_table("audit_findings")
