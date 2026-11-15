import enum
import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin, utcnow

MONEY = Numeric(14, 2)


class AttendanceStatus(str, enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    HALF_DAY = "half_day"
    LEAVE = "leave"


class AttendanceRecord(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("station_id", "user_id", "attendance_date", name="uq_attendance_station_user_date"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stations.id", ondelete="CASCADE"), nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=AttendanceStatus.PRESENT.value)
    check_in_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    check_out_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recorded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )


class PayrollRule(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "payroll_rules"
    __table_args__ = (
        UniqueConstraint("station_id", "rule_name", name="uq_payroll_rule_station_name"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stations.id", ondelete="CASCADE"), nullable=False,
    )
    rule_name: Mapped[str] = mapped_column(String(100), nullable=False)
    shift_start_time: Mapped[time] = mapped_column(Time, nullable=False)
    late_threshold_minutes: Mapped[int] = mapped_column(nullable=False, default=15)
    half_day_threshold_minutes: Mapped[int] = mapped_column(nullable=False, default=120)
    late_deduction_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    absent_deduction_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    half_day_deduction_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SalaryRecord(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "salary_records"
    __table_args__ = (
        UniqueConstraint("station_id", "user_id", "period_start", "period_end", name="uq_salary_station_user_period"),
        CheckConstraint("base_salary >= 0", name="ck_salary_base_nonnegative"),
        CheckConstraint("total_deductions >= 0", name="ck_salary_deductions_nonnegative"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stations.id", ondelete="CASCADE"), nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    base_salary: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    total_deductions: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    net_salary: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    days_present: Mapped[int] = mapped_column(nullable=False, default=0)
    days_absent: Mapped[int] = mapped_column(nullable=False, default=0)
    days_late: Mapped[int] = mapped_column(nullable=False, default=0)
    days_half_day: Mapped[int] = mapped_column(nullable=False, default=0)
    days_leave: Mapped[int] = mapped_column(nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    generated_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    is_finalized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
