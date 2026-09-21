"""Add application user role table.

Revision ID: 0008_user_roles
Revises: 0007_control_evidence_review
Create Date: 2026-09-21
"""

from alembic import op

revision = "0008_user_roles"
down_revision = "0007_control_evidence_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        create table if not exists public.user_roles (
            user_id varchar(100) primary key,
            email varchar(255),
            display_name varchar(255),
            role varchar(30) not null default 'VIEWER',
            branch varchar(255),
            is_active boolean not null default true,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            constraint ck_user_roles_role check (role in ('ADMIN', 'AUDITOR', 'REVIEWER', 'VIEWER'))
        )
        """
    )
    op.execute("alter table public.user_roles add column if not exists email varchar(255)")
    op.execute("alter table public.user_roles add column if not exists display_name varchar(255)")
    op.execute("alter table public.user_roles add column if not exists branch varchar(255)")
    op.execute("alter table public.user_roles add column if not exists is_active boolean not null default true")
    op.execute("alter table public.user_roles add column if not exists created_at timestamptz not null default now()")
    op.execute("alter table public.user_roles add column if not exists updated_at timestamptz not null default now()")
    op.execute("create index if not exists ix_user_roles_role on public.user_roles(role)")
    op.execute("create index if not exists ix_user_roles_is_active on public.user_roles(is_active)")
    op.execute("create index if not exists ix_user_roles_branch on public.user_roles(branch)")


def downgrade() -> None:
    op.execute("drop table if exists public.user_roles")
