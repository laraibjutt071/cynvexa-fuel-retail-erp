import uuid
from datetime import date, datetime, time
from decimal import Decimal

from pydantic import BaseModel, Field


class AttendanceRecordCreate(BaseModel):
    user_id: uuid.UUID
    attendance_date: date
    status: str = "present"
    check_in_time: time | None = None
    check_out_time: time | None = None
    notes: str | None = None


class AttendanceRecordUpdate(BaseModel):
    status: str | None = None
    check_in_time: time | None = None
    check_out_time: time | None = None
    notes: str | None = None


class AttendanceRecordRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    station_id: uuid.UUID
    user_id: uuid.UUID
    attendance_date: date
    status: str
    check_in_time: time | None
    check_out_time: time | None
    source: str
    notes: str | None
    recorded_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PayrollRuleCreate(BaseModel):
    rule_name: str = Field(max_length=100)
    shift_start_time: time
    late_threshold_minutes: int = Field(default=15, ge=0)
    half_day_threshold_minutes: int = Field(default=120, ge=0)
    late_deduction_amount: Decimal = Field(default=0, ge=0)
    absent_deduction_amount: Decimal = Field(default=0, ge=0)
    half_day_deduction_amount: Decimal = Field(default=0, ge=0)


class PayrollRuleUpdate(BaseModel):
    shift_start_time: time | None = None
    late_threshold_minutes: int | None = Field(default=None, ge=0)
    half_day_threshold_minutes: int | None = Field(default=None, ge=0)
    late_deduction_amount: Decimal | None = Field(default=None, ge=0)
    absent_deduction_amount: Decimal | None = Field(default=None, ge=0)
    half_day_deduction_amount: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None


class PayrollRuleRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    station_id: uuid.UUID
    rule_name: str
    shift_start_time: time
    late_threshold_minutes: int
    half_day_threshold_minutes: int
    late_deduction_amount: Decimal
    absent_deduction_amount: Decimal
    half_day_deduction_amount: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SalaryGenerateRequest(BaseModel):
    user_id: uuid.UUID
    period_start: date
    period_end: date
    base_salary: Decimal = Field(ge=0)
    notes: str | None = None


class SalaryRecordRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    station_id: uuid.UUID
    user_id: uuid.UUID
    period_start: date
    period_end: date
    base_salary: Decimal
    total_deductions: Decimal
    net_salary: Decimal
    days_present: int
    days_absent: int
    days_late: int
    days_half_day: int
    days_leave: int
    notes: str | None
    generated_by_user_id: uuid.UUID
    is_finalized: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
