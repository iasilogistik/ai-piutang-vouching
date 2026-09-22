"""Add in-app audit notifications and preferences.

Revision ID: 0025_audit_notifications
Revises: 0024_follow_up_monitoring
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0025_audit_notifications"
down_revision = "0024_follow_up_monitoring"
branch_labels = None
depends_on = None


def _supabase_auth_available() -> bool:
    bind = op.get_bind()
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


def upgrade() -> None:
    op.create_table(
        "audit_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("target_url", sa.String(length=1024), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_audit_notification_idempotency"),
    )
    op.create_index("ix_audit_notifications_user_read", "audit_notifications", ["user_id", "is_read", "created_at"])
    op.create_index("ix_audit_notifications_branch", "audit_notifications", ["branch"])
    op.create_index("ix_audit_notifications_event", "audit_notifications", ["event_type"])

    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.String(length=100), primary_key=True),
        sa.Column("in_app_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reminder_days_before", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("digest_frequency", sa.String(length=20), nullable=False, server_default="IMMEDIATE"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("reminder_days_before >= 0 and reminder_days_before <= 30", name="ck_notification_reminder_days"),
        sa.CheckConstraint("digest_frequency in ('IMMEDIATE','DAILY','WEEKLY')", name="ck_notification_digest_frequency"),
    )

    for table in ("audit_notifications", "notification_preferences"):
        op.execute(f"alter table public.{table} enable row level security")

    if _supabase_auth_available():
        op.execute("""
            create policy "notification_owner_read"
            on public.audit_notifications for select to authenticated
            using (user_id = auth.uid()::text)
        """)
        op.execute("""
            create policy "notification_owner_update"
            on public.audit_notifications for update to authenticated
            using (user_id = auth.uid()::text)
            with check (user_id = auth.uid()::text)
        """)
        op.execute("""
            create policy "notification_preferences_owner"
            on public.notification_preferences for all to authenticated
            using (user_id = auth.uid()::text)
            with check (user_id = auth.uid()::text)
        """)


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_table("audit_notifications")
