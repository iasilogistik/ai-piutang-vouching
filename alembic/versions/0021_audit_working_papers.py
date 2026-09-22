"""Add electronic audit working papers.

Revision ID: 0021_audit_working_papers
Revises: 0020_audit_sampling
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0021_audit_working_papers"
down_revision = "0020_audit_sampling"
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
        "audit_working_papers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("engagement_id", sa.Integer(), sa.ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("reference", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("audit_objective", sa.Text(), nullable=False),
        sa.Column("procedure_performed", sa.Text(), nullable=False),
        sa.Column("result_observation", sa.Text(), nullable=True),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("preparer_id", sa.String(length=100), nullable=False),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_id", sa.String(length=100), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sample_id", sa.Integer(), sa.ForeignKey("audit_samples.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("engagement_id", "reference", name="uq_audit_working_paper_reference"),
    )
    op.create_index("ix_audit_working_papers_engagement", "audit_working_papers", ["engagement_id"])
    op.create_index("ix_audit_working_papers_branch", "audit_working_papers", ["branch"])
    op.create_index("ix_audit_working_papers_status", "audit_working_papers", ["status"])
    op.create_index("ix_audit_working_papers_sample", "audit_working_papers", ["sample_id"])

    op.create_table(
        "audit_working_paper_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("working_paper_id", sa.Integer(), sa.ForeignKey("audit_working_papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("audit_objective", sa.Text(), nullable=False),
        sa.Column("procedure_performed", sa.Text(), nullable=False),
        sa.Column("result_observation", sa.Text(), nullable=True),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("changed_by", sa.String(length=100), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("working_paper_id", "version_number", name="uq_working_paper_version"),
    )
    op.create_index("ix_working_paper_versions_paper", "audit_working_paper_versions", ["working_paper_id"])

    op.create_table(
        "audit_working_paper_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("working_paper_id", sa.Integer(), sa.ForeignKey("audit_working_papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("control_evidence_id", sa.Integer(), sa.ForeignKey("document_control_evidence.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("linked_by", sa.String(length=100), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(document_id is not null and control_evidence_id is null) or "
            "(document_id is null and control_evidence_id is not null)",
            name="ck_working_paper_evidence_one_source",
        ),
        sa.UniqueConstraint("working_paper_id", "document_id", name="uq_working_paper_document"),
        sa.UniqueConstraint("working_paper_id", "control_evidence_id", name="uq_working_paper_control_evidence"),
    )
    op.create_index("ix_working_paper_evidence_paper", "audit_working_paper_evidence", ["working_paper_id"])

    op.create_table(
        "audit_working_paper_exceptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("working_paper_id", sa.Integer(), sa.ForeignKey("audit_working_papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("audit_exception_id", sa.Integer(), sa.ForeignKey("audit_exceptions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("linked_by", sa.String(length=100), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("working_paper_id", "audit_exception_id", name="uq_working_paper_exception"),
    )
    op.create_index("ix_working_paper_exceptions_paper", "audit_working_paper_exceptions", ["working_paper_id"])

    for table in (
        "audit_working_papers",
        "audit_working_paper_versions",
        "audit_working_paper_evidence",
        "audit_working_paper_exceptions",
    ):
        op.execute(f"alter table public.{table} enable row level security")

    if _supabase_rbac_available():
        op.execute("""
            create policy "app_read_audit_working_papers"
            on public.audit_working_papers for select to authenticated
            using (
              (select public.current_app_role()) = 'ADMIN'::public.app_role
              or upper(trim(branch)) = (select public.current_app_branch())
            )
        """)
        op.execute("""
            create policy "auditor_manage_audit_working_papers"
            on public.audit_working_papers for all to authenticated
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
        for table in ("audit_working_paper_versions", "audit_working_paper_evidence", "audit_working_paper_exceptions"):
            op.execute(
                f"""
                create policy "app_read_{table}"
                on public.{table} for select to authenticated
                using (
                  exists (
                    select 1 from public.audit_working_papers wp
                    where wp.id = working_paper_id
                      and (
                        (select public.current_app_role()) = 'ADMIN'::public.app_role
                        or upper(trim(wp.branch)) = (select public.current_app_branch())
                      )
                  )
                )
                """
            )

        op.execute(
            """
            create policy "app_manage_audit_working_paper_versions"
            on public.audit_working_paper_versions for all to authenticated
            using (
              exists (
                select 1 from public.audit_working_papers wp
                where wp.id = working_paper_id
                  and (select public.current_app_role()) = any (
                    array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role, 'REVIEWER'::public.app_role]
                  )
                  and (
                    (select public.current_app_role()) = 'ADMIN'::public.app_role
                    or upper(trim(wp.branch)) = (select public.current_app_branch())
                  )
              )
            )
            with check (
              exists (
                select 1 from public.audit_working_papers wp
                where wp.id = working_paper_id
                  and (select public.current_app_role()) = any (
                    array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role, 'REVIEWER'::public.app_role]
                  )
                  and (
                    (select public.current_app_role()) = 'ADMIN'::public.app_role
                    or upper(trim(wp.branch)) = (select public.current_app_branch())
                  )
              )
            )
            """
        )
        for table in ("audit_working_paper_evidence", "audit_working_paper_exceptions"):
            op.execute(
                f"""
                create policy "auditor_manage_{table}"
                on public.{table} for all to authenticated
                using (
                  exists (
                    select 1 from public.audit_working_papers wp
                    where wp.id = working_paper_id
                      and (select public.current_app_role()) = any (
                        array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]
                      )
                      and (
                        (select public.current_app_role()) = 'ADMIN'::public.app_role
                        or upper(trim(wp.branch)) = (select public.current_app_branch())
                      )
                  )
                )
                with check (
                  exists (
                    select 1 from public.audit_working_papers wp
                    where wp.id = working_paper_id
                      and (select public.current_app_role()) = any (
                        array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]
                      )
                      and (
                        (select public.current_app_role()) = 'ADMIN'::public.app_role
                        or upper(trim(wp.branch)) = (select public.current_app_branch())
                      )
                  )
                )
                """
            )


def downgrade() -> None:
    op.drop_table("audit_working_paper_exceptions")
    op.drop_table("audit_working_paper_evidence")
    op.drop_table("audit_working_paper_versions")
    op.drop_table("audit_working_papers")
