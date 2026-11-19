"""Phase 5b: add support_sessions table for read-only Super Admin support access

Revision ID: g7h8i9j0k1l2
Revises: f6g7h8i9j0k1
Create Date: 2026-11-19

A new, standalone table - no existing table touched. The partial unique
index enforces at most one non-ended support session per superuser at a
time, at the database level (not just in application code), closing the
race between two concurrent session-creation requests.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "g7h8i9j0k1l2"
down_revision = "f6g7h8i9j0k1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superuser_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("station_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
    )
    op.create_index("ix_support_sessions_organization_id", "support_sessions", ["organization_id"])
    op.create_index("ix_support_sessions_superuser_org", "support_sessions", ["superuser_id", "organization_id"])
    op.create_index(
        "ix_support_sessions_one_active_per_admin",
        "support_sessions",
        ["superuser_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_support_sessions_one_active_per_admin", table_name="support_sessions")
    op.drop_index("ix_support_sessions_superuser_org", table_name="support_sessions")
    op.drop_index("ix_support_sessions_organization_id", table_name="support_sessions")
    op.drop_table("support_sessions")
