"""Strengthen documents as audit evidence repository.

Revision ID: 0026_evidence_repository
Revises: 0025_audit_notifications
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0026_evidence_repository"
down_revision = "0025_audit_notifications"
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
    op.add_column("documents", sa.Column("engagement_id", sa.Integer(), sa.ForeignKey("audit_engagements.id", ondelete="SET NULL"), nullable=True))
    op.add_column("documents", sa.Column("evidence_classification", sa.String(length=50), nullable=True))
    op.add_column("documents", sa.Column("evidence_source", sa.String(length=100), nullable=True))
    op.add_column("documents", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("file_size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("documents", sa.Column("mime_type", sa.String(length=255), nullable=True))
    op.add_column("documents", sa.Column("evidence_version_number", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("documents", sa.Column("supersedes_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="RESTRICT"), nullable=True))
    op.add_column("documents", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("archived_by", sa.String(length=100), nullable=True))
    op.add_column("documents", sa.Column("archive_reason", sa.Text(), nullable=True))
    op.create_index("ix_documents_engagement", "documents", ["engagement_id"])
    op.create_index("ix_documents_supersedes", "documents", ["supersedes_document_id"])
    op.create_index("ix_documents_archived", "documents", ["archived_at"])

    op.create_table(
        "evidence_resource_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("engagement_id", sa.Integer(), sa.ForeignKey("audit_engagements.id", ondelete="SET NULL"), nullable=True),
        sa.Column("linked_by", sa.String(length=100), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("document_id", "resource_type", "resource_id", name="uq_evidence_resource_link"),
        sa.CheckConstraint(
            "resource_type in ('SAMPLE','WORKING_PAPER','FINDING','ACTION_PLAN','FOLLOW_UP','AUDIT_REPORT')",
            name="ck_evidence_resource_type",
        ),
    )
    op.create_index("ix_evidence_resource_links_document", "evidence_resource_links", ["document_id"])
    op.create_index("ix_evidence_resource_links_resource", "evidence_resource_links", ["resource_type", "resource_id"])
    op.create_index("ix_evidence_resource_links_branch", "evidence_resource_links", ["branch"])
    op.create_index("ix_evidence_resource_links_engagement", "evidence_resource_links", ["engagement_id"])
    op.execute("alter table public.evidence_resource_links enable row level security")

    if _supabase_rbac_available():
        op.execute("""
            create policy "app_read_evidence_resource_links"
            on public.evidence_resource_links for select to authenticated
            using (
              (select public.current_app_role())='ADMIN'::public.app_role
              or upper(trim(branch))=(select public.current_app_branch())
            )
        """)
        op.execute("""
            create policy "auditor_manage_evidence_resource_links"
            on public.evidence_resource_links for all to authenticated
            using (
              (select public.current_app_role())=any(array['ADMIN'::public.app_role,'AUDITOR'::public.app_role])
              and (
                (select public.current_app_role())='ADMIN'::public.app_role
                or upper(trim(branch))=(select public.current_app_branch())
              )
            )
            with check (
              (select public.current_app_role())=any(array['ADMIN'::public.app_role,'AUDITOR'::public.app_role])
              and (
                (select public.current_app_role())='ADMIN'::public.app_role
                or upper(trim(branch))=(select public.current_app_branch())
              )
            )
        """)


def downgrade() -> None:
    op.drop_table("evidence_resource_links")
    op.drop_index("ix_documents_archived", table_name="documents")
    op.drop_index("ix_documents_supersedes", table_name="documents")
    op.drop_index("ix_documents_engagement", table_name="documents")
    for column in (
        "archive_reason","archived_by","archived_at","supersedes_document_id",
        "evidence_version_number","mime_type","file_size_bytes","description",
        "evidence_source","evidence_classification","engagement_id",
    ):
        op.drop_column("documents", column)
