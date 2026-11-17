"""Phase 4: add employee profile fields to users for Staff Management

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2026-11-18

Purely additive, all nullable - no existing row changes. employee_code
and job_title are per-person fields (global on User, matching how
full_name/email already work), not per-role-assignment - "joining date"
deliberately has no new column, since UserStationRole.created_at (when
an org/role was granted) already represents it accurately.
"""

from alembic import op
import sqlalchemy as sa

revision = "e5f6g7h8i9j0"
down_revision = "d4e5f6g7h8i9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("employee_code", sa.String(length=50), nullable=True))
    op.add_column("users", sa.Column("job_title", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "phone")
    op.drop_column("users", "job_title")
    op.drop_column("users", "employee_code")
