"""Day 4: attendance tracking, payroll rules, salary records

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-15

Changes:
1. Create attendance_records table (manual check-in/out)
2. Create payroll_rules table (configurable deduction rules)
3. Create salary_records table (period-based salary generation)
4. Seed attendance:read, attendance:record, payroll:manage permissions
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b2c3d4e5f6g7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attendance_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("station_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("attendance_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="present"),
        sa.Column("check_in_time", sa.Time, nullable=True),
        sa.Column("check_out_time", sa.Time, nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("recorded_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("station_id", "user_id", "attendance_date", name="uq_attendance_station_user_date"),
    )

    op.create_table(
        "payroll_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("station_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_name", sa.String(100), nullable=False),
        sa.Column("shift_start_time", sa.Time, nullable=False),
        sa.Column("late_threshold_minutes", sa.Integer, nullable=False, server_default="15"),
        sa.Column("half_day_threshold_minutes", sa.Integer, nullable=False, server_default="120"),
        sa.Column("late_deduction_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("absent_deduction_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("half_day_deduction_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("station_id", "rule_name", name="uq_payroll_rule_station_name"),
    )

    op.create_table(
        "salary_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("station_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("base_salary", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_deductions", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("net_salary", sa.Numeric(14, 2), nullable=False),
        sa.Column("days_present", sa.Integer, nullable=False, server_default="0"),
        sa.Column("days_absent", sa.Integer, nullable=False, server_default="0"),
        sa.Column("days_late", sa.Integer, nullable=False, server_default="0"),
        sa.Column("days_half_day", sa.Integer, nullable=False, server_default="0"),
        sa.Column("days_leave", sa.Integer, nullable=False, server_default="0"),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("generated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_finalized", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("station_id", "user_id", "period_start", "period_end", name="uq_salary_station_user_period"),
        sa.CheckConstraint("base_salary >= 0", name="ck_salary_base_nonnegative"),
        sa.CheckConstraint("total_deductions >= 0", name="ck_salary_deductions_nonnegative"),
    )

    permissions_table = sa.table(
        "permissions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    import uuid
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    op.bulk_insert(permissions_table, [
        {
            "id": str(uuid.uuid4()),
            "code": "attendance:read",
            "description": "View attendance records.",
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": str(uuid.uuid4()),
            "code": "attendance:record",
            "description": "Record or edit attendance entries.",
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": str(uuid.uuid4()),
            "code": "payroll:manage",
            "description": "Manage payroll rules and generate salary records.",
            "created_at": now,
            "updated_at": now,
        },
    ])


def downgrade() -> None:
    op.drop_table("salary_records")
    op.drop_table("payroll_rules")
    op.drop_table("attendance_records")
    op.execute("DELETE FROM permissions WHERE code IN ('attendance:read', 'attendance:record', 'payroll:manage')")
