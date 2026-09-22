"""Persist control-evidence detection history.

Revision ID: 0016_control_evidence_detect
Revises: 0015_audit_closing_signoff
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_control_evidence_detect"
down_revision = "0015_audit_closing_signoff"
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


def upgrade() -> None:
    op.create_table(
        "control_evidence_detections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=True),
        sa.Column("detection_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("reference_json", sa.JSON(), nullable=True),
        sa.Column("source_file_hash", sa.String(length=128), nullable=False),
        sa.Column("detector_name", sa.String(length=100), nullable=False),
        sa.Column("detector_version", sa.String(length=50), nullable=False),
        sa.Column("extraction_engine", sa.String(length=100), nullable=True),
        sa.Column("processing_status", sa.String(length=20), nullable=False, server_default="SUCCESS"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "document_id",
            "detection_type",
            "source_file_hash",
            "detector_name",
            "detector_version",
            name="uq_control_evidence_detection_idempotency",
        ),
    )
    op.create_index("ix_control_evidence_detections_branch", "control_evidence_detections", ["branch"])
    op.create_index("ix_control_evidence_detections_type", "control_evidence_detections", ["detection_type"])
    op.create_index("ix_control_evidence_detections_processed_at", "control_evidence_detections", ["processed_at"])
    op.execute("alter table public.control_evidence_detections enable row level security")

    if _supabase_rbac_available():
        op.execute(
            """
            create policy "app_read_control_evidence_detections"
            on public.control_evidence_detections for select to authenticated
            using (
              (select public.current_app_role()) = 'ADMIN'::public.app_role
              or exists (
                select 1 from public.documents d
                where d.id = control_evidence_detections.document_id
                  and upper(trim(d.branch)) = (select public.current_app_branch())
              )
            )
            """
        )
        op.execute(
            """
            create policy "auditor_insert_control_evidence_detections"
            on public.control_evidence_detections for insert to authenticated
            with check (
              (select public.current_app_role()) = any (
                array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]
              )
              and exists (
                select 1 from public.documents d
                where d.id = control_evidence_detections.document_id
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
            create policy "auditor_update_control_evidence_detections"
            on public.control_evidence_detections for update to authenticated
            using (
              (select public.current_app_role()) = any (
                array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]
              )
              and exists (
                select 1 from public.documents d
                where d.id = control_evidence_detections.document_id
                  and (
                    (select public.current_app_role()) = 'ADMIN'::public.app_role
                    or upper(trim(d.branch)) = (select public.current_app_branch())
                  )
              )
            )
            with check (
              (select public.current_app_role()) = any (
                array['ADMIN'::public.app_role, 'AUDITOR'::public.app_role]
              )
              and exists (
                select 1 from public.documents d
                where d.id = control_evidence_detections.document_id
                  and (
                    (select public.current_app_role()) = 'ADMIN'::public.app_role
                    or upper(trim(d.branch)) = (select public.current_app_branch())
                  )
              )
            )
            """
        )


def downgrade() -> None:
    op.drop_table("control_evidence_detections")
