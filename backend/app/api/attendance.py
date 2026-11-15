import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_station_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import ATTENDANCE_READ, ATTENDANCE_RECORD, PAYROLL_MANAGE
from app.core.revenue import round_money
from app.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.models.attendance import AttendanceRecord, AttendanceStatus, PayrollRule, SalaryRecord
from app.models.user import User
from app.schemas.attendance import (
    AttendanceRecordCreate,
    AttendanceRecordRead,
    AttendanceRecordUpdate,
    PayrollRuleCreate,
    PayrollRuleRead,
    PayrollRuleUpdate,
    SalaryGenerateRequest,
    SalaryRecordRead,
)

attendance_router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/attendance",
    tags=["attendance"],
)

payroll_router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/payroll",
    tags=["payroll"],
)


@attendance_router.post("", response_model=AttendanceRecordRead, status_code=201)
async def create_attendance_record(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    payload: AttendanceRecordCreate,
    request: Request,
    current_user: User = Depends(require_permission(ATTENDANCE_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> AttendanceRecord:
    await get_station_or_404(db, organization_id, station_id)

    valid_statuses = {s.value for s in AttendanceStatus}
    if payload.status not in valid_statuses:
        raise ValidationFailedError(f"Invalid status. Must be one of: {sorted(valid_statuses)}")

    record = AttendanceRecord(
        organization_id=organization_id,
        station_id=station_id,
        user_id=payload.user_id,
        attendance_date=payload.attendance_date,
        status=payload.status,
        check_in_time=payload.check_in_time,
        check_out_time=payload.check_out_time,
        notes=payload.notes,
        source="manual",
        recorded_by_user_id=current_user.id,
    )
    db.add(record)
    try:
        await db.flush()
    except Exception:
        await db.rollback()
        raise ConflictError("An attendance record already exists for this user on this date at this station.")

    await write_audit_log(
        db,
        action="attendance.create",
        entity_type="AttendanceRecord",
        entity_id=str(record.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"user_id": str(payload.user_id), "date": str(payload.attendance_date), "status": payload.status},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return record


@attendance_router.get("", response_model=list[AttendanceRecordRead])
async def list_attendance_records(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    user_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_permission(ATTENDANCE_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[AttendanceRecord]:
    await get_station_or_404(db, organization_id, station_id)
    stmt = select(AttendanceRecord).where(AttendanceRecord.station_id == station_id)
    if date_from:
        stmt = stmt.where(AttendanceRecord.attendance_date >= date_from)
    if date_to:
        stmt = stmt.where(AttendanceRecord.attendance_date <= date_to)
    if user_id:
        stmt = stmt.where(AttendanceRecord.user_id == user_id)
    stmt = stmt.order_by(AttendanceRecord.attendance_date.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@attendance_router.patch("/{record_id}", response_model=AttendanceRecordRead)
async def update_attendance_record(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    record_id: uuid.UUID,
    payload: AttendanceRecordUpdate,
    request: Request,
    current_user: User = Depends(require_permission(ATTENDANCE_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> AttendanceRecord:
    record = (
        await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.id == record_id,
                AttendanceRecord.station_id == station_id,
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise NotFoundError("Attendance record not found.")

    before = {"status": record.status}
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "status" and value is not None:
            valid_statuses = {s.value for s in AttendanceStatus}
            if value not in valid_statuses:
                raise ValidationFailedError(f"Invalid status. Must be one of: {sorted(valid_statuses)}")
        setattr(record, field, value)
    await db.flush()

    await write_audit_log(
        db,
        action="attendance.update",
        entity_type="AttendanceRecord",
        entity_id=str(record.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        before=before,
        after=payload.model_dump(exclude_unset=True, mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return record


@payroll_router.post("/rules", response_model=PayrollRuleRead, status_code=201)
async def create_payroll_rule(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    payload: PayrollRuleCreate,
    request: Request,
    current_user: User = Depends(require_permission(PAYROLL_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> PayrollRule:
    await get_station_or_404(db, organization_id, station_id)
    rule = PayrollRule(
        organization_id=organization_id,
        station_id=station_id,
        **payload.model_dump(),
    )
    db.add(rule)
    try:
        await db.flush()
    except Exception:
        await db.rollback()
        raise ConflictError("A payroll rule with this name already exists at this station.")

    await write_audit_log(
        db,
        action="payroll_rule.create",
        entity_type="PayrollRule",
        entity_id=str(rule.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"rule_name": rule.rule_name},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return rule


@payroll_router.get("/rules", response_model=list[PayrollRuleRead])
async def list_payroll_rules(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    current_user: User = Depends(require_permission(PAYROLL_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[PayrollRule]:
    await get_station_or_404(db, organization_id, station_id)
    result = await db.execute(
        select(PayrollRule).where(PayrollRule.station_id == station_id).order_by(PayrollRule.rule_name)
    )
    return list(result.scalars().all())


@payroll_router.patch("/rules/{rule_id}", response_model=PayrollRuleRead)
async def update_payroll_rule(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    rule_id: uuid.UUID,
    payload: PayrollRuleUpdate,
    request: Request,
    current_user: User = Depends(require_permission(PAYROLL_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> PayrollRule:
    rule = (
        await db.execute(
            select(PayrollRule).where(PayrollRule.id == rule_id, PayrollRule.station_id == station_id)
        )
    ).scalar_one_or_none()
    if rule is None:
        raise NotFoundError("Payroll rule not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    await db.flush()

    await write_audit_log(
        db,
        action="payroll_rule.update",
        entity_type="PayrollRule",
        entity_id=str(rule.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after=payload.model_dump(exclude_unset=True, mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return rule


@payroll_router.post("/salary/generate", response_model=SalaryRecordRead, status_code=201)
async def generate_salary(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    payload: SalaryGenerateRequest,
    request: Request,
    current_user: User = Depends(require_permission(PAYROLL_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> SalaryRecord:
    await get_station_or_404(db, organization_id, station_id)
    if payload.period_end < payload.period_start:
        raise ValidationFailedError("period_end must not be before period_start.")

    records = (
        await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.station_id == station_id,
                AttendanceRecord.user_id == payload.user_id,
                AttendanceRecord.attendance_date >= payload.period_start,
                AttendanceRecord.attendance_date <= payload.period_end,
            )
        )
    ).scalars().all()

    active_rule = (
        await db.execute(
            select(PayrollRule).where(
                PayrollRule.station_id == station_id,
                PayrollRule.is_active.is_(True),
            ).limit(1)
        )
    ).scalar_one_or_none()

    days_present = sum(1 for r in records if r.status == AttendanceStatus.PRESENT.value)
    days_absent = sum(1 for r in records if r.status == AttendanceStatus.ABSENT.value)
    days_late = sum(1 for r in records if r.status == AttendanceStatus.LATE.value)
    days_half_day = sum(1 for r in records if r.status == AttendanceStatus.HALF_DAY.value)
    days_leave = sum(1 for r in records if r.status == AttendanceStatus.LEAVE.value)

    total_deductions = Decimal(0)
    if active_rule:
        total_deductions += days_late * active_rule.late_deduction_amount
        total_deductions += days_absent * active_rule.absent_deduction_amount
        total_deductions += days_half_day * active_rule.half_day_deduction_amount
    total_deductions = round_money(total_deductions)
    net_salary = round_money(payload.base_salary - total_deductions)

    salary = SalaryRecord(
        organization_id=organization_id,
        station_id=station_id,
        user_id=payload.user_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
        base_salary=payload.base_salary,
        total_deductions=total_deductions,
        net_salary=net_salary,
        days_present=days_present,
        days_absent=days_absent,
        days_late=days_late,
        days_half_day=days_half_day,
        days_leave=days_leave,
        notes=payload.notes,
        generated_by_user_id=current_user.id,
    )
    db.add(salary)
    try:
        await db.flush()
    except Exception:
        await db.rollback()
        raise ConflictError("A salary record already exists for this user and period.")

    await write_audit_log(
        db,
        action="salary.generate",
        entity_type="SalaryRecord",
        entity_id=str(salary.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={
            "user_id": str(payload.user_id),
            "period": f"{payload.period_start} to {payload.period_end}",
            "net_salary": str(net_salary),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return salary


@payroll_router.get("/salary", response_model=list[SalaryRecordRead])
async def list_salary_records(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    user_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_permission(PAYROLL_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[SalaryRecord]:
    await get_station_or_404(db, organization_id, station_id)
    stmt = select(SalaryRecord).where(SalaryRecord.station_id == station_id)
    if user_id:
        stmt = stmt.where(SalaryRecord.user_id == user_id)
    stmt = stmt.order_by(SalaryRecord.period_start.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@payroll_router.patch("/salary/{salary_id}/finalize", response_model=SalaryRecordRead)
async def finalize_salary(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    salary_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission(PAYROLL_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> SalaryRecord:
    salary = (
        await db.execute(
            select(SalaryRecord).where(
                SalaryRecord.id == salary_id,
                SalaryRecord.station_id == station_id,
            )
        )
    ).scalar_one_or_none()
    if salary is None:
        raise NotFoundError("Salary record not found.")
    if salary.is_finalized:
        raise ConflictError("This salary record is already finalized.")

    salary.is_finalized = True
    await db.flush()

    await write_audit_log(
        db,
        action="salary.finalize",
        entity_type="SalaryRecord",
        entity_id=str(salary.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"is_finalized": True},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return salary
