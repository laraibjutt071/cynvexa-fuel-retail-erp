import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import (
    get_credit_customer_or_404,
    get_ev_charger_port_in_station_or_404,
    get_ev_tariff_or_404,
    get_payment_method_or_404,
)
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import EV_SESSION_APPROVE, EV_SESSION_READ, EV_SESSION_RECORD
from app.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.models.ev_charger import EVCharger, EVChargerPort, PortStatus
from app.models.ev_charging_session import EVChargingSession, EVSessionStatus
from app.models.ev_tariff import EVPricingBasis
from app.models.user import User
from app.schemas.ev_charging_session import (
    EVChargingSessionClose,
    EVChargingSessionCreate,
    EVChargingSessionFail,
    EVChargingSessionRead,
    EVChargingSessionReverse,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/ev-charging-sessions",
    tags=["ev-charging-sessions"],
)

ENTITY_TYPE = "EVChargingSession"


def _decimal_fields(obj, fields: list[str]) -> dict:
    return {f: (str(v) if isinstance(v := getattr(obj, f), Decimal) else v) for f in fields}


async def _get_session_or_404(
    db: AsyncSession, station_id: uuid.UUID, session_id: uuid.UUID, *, for_update: bool = False
) -> EVChargingSession:
    """A session has no direct station_id column - it belongs to a station
    through its port's charger, so the check joins through both."""
    stmt = (
        select(EVChargingSession)
        .join(EVChargerPort, EVChargerPort.id == EVChargingSession.port_id)
        .join(EVCharger, EVCharger.id == EVChargerPort.charger_id)
        .where(EVChargingSession.id == session_id, EVCharger.station_id == station_id)
    )
    if for_update:
        stmt = stmt.with_for_update()
    session = (await db.execute(stmt)).scalar_one_or_none()
    if session is None:
        raise NotFoundError("EV charging session not found on this station.")
    return session


@router.post("", response_model=EVChargingSessionRead, status_code=201)
async def open_ev_charging_session(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    payload: EVChargingSessionCreate,
    request: Request,
    current_user: User = Depends(require_permission(EV_SESSION_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> EVChargingSession:
    """
    Locks the port row before checking its status, so two concurrent opens
    against the same port can't both pass the "is it available" check
    before either commits - the same race this project's shift-opening
    endpoint was fixed against (two shifts could otherwise end up
    simultaneously open on one station; here it would be two sessions
    simultaneously charging on one port).
    """
    port = await get_ev_charger_port_in_station_or_404(db, station_id, payload.port_id, for_update=True)
    if port.status != PortStatus.AVAILABLE.value:
        raise ConflictError(f"Port is '{port.status}', not 'available' - cannot start a new session on it.")

    tariff = await get_ev_tariff_or_404(db, station_id, payload.tariff_id)
    if tariff.charger_id is not None and tariff.charger_id != port.charger_id:
        raise ValidationFailedError("This tariff is scoped to a different charger than the selected port.")

    if payload.credit_customer_id is not None:
        await get_credit_customer_or_404(db, organization_id, payload.credit_customer_id)

    session = EVChargingSession(
        port_id=payload.port_id,
        tariff_id=payload.tariff_id,
        session_reference=payload.session_reference,
        status=EVSessionStatus.CHARGING.value,
        start_time=payload.start_time or datetime.now(timezone.utc),
        start_meter_kwh=payload.start_meter_kwh,
        vehicle_reference=payload.vehicle_reference,
        credit_customer_id=payload.credit_customer_id,
        created_by_user_id=current_user.id,
    )
    db.add(session)
    port.status = PortStatus.CHARGING.value
    await db.flush()

    await write_audit_log(
        db,
        action="ev_charging_session.open",
        entity_type=ENTITY_TYPE,
        entity_id=str(session.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"port_id": str(payload.port_id), "tariff_id": str(payload.tariff_id), **_decimal_fields(session, ["start_meter_kwh"])},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return session


@router.get("", response_model=list[EVChargingSessionRead])
async def list_ev_charging_sessions(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    current_user: User = Depends(require_permission(EV_SESSION_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[EVChargingSession]:
    stmt = (
        select(EVChargingSession)
        .join(EVChargerPort, EVChargerPort.id == EVChargingSession.port_id)
        .join(EVCharger, EVCharger.id == EVChargerPort.charger_id)
        .where(EVCharger.station_id == station_id)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{session_id}", response_model=EVChargingSessionRead)
async def get_ev_charging_session(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    session_id: uuid.UUID,
    current_user: User = Depends(require_permission(EV_SESSION_READ)),
    db: AsyncSession = Depends(get_db),
) -> EVChargingSession:
    return await _get_session_or_404(db, station_id, session_id)


def _compute_gross_amount(pricing_basis: str, rate: Decimal, delivered_kwh: Decimal, duration_minutes: Decimal) -> Decimal:
    if pricing_basis == EVPricingBasis.PER_KWH.value:
        return (rate * delivered_kwh).quantize(Decimal("0.01"))
    if pricing_basis == EVPricingBasis.TIME_BASED.value:
        return (rate * duration_minutes).quantize(Decimal("0.01"))
    if pricing_basis == EVPricingBasis.SESSION_FEE.value:
        return rate.quantize(Decimal("0.01"))
    raise ValidationFailedError(f"Unknown EV tariff pricing basis '{pricing_basis}'.")


@router.patch("/{session_id}/close", response_model=EVChargingSessionRead)
async def close_ev_charging_session(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    session_id: uuid.UUID,
    payload: EVChargingSessionClose,
    request: Request,
    current_user: User = Depends(require_permission(EV_SESSION_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> EVChargingSession:
    session = await _get_session_or_404(db, station_id, session_id, for_update=True)
    if session.status not in (EVSessionStatus.INITIATED.value, EVSessionStatus.CHARGING.value):
        raise ConflictError(f"Session is '{session.status}' - only an initiated/charging session can be closed.")

    if payload.end_meter_kwh < session.start_meter_kwh:
        raise ValidationFailedError(
            "end_meter_kwh cannot be lower than start_meter_kwh - delivered energy cannot be negative."
        )
    end_time = payload.end_time or datetime.now(timezone.utc)
    if end_time < session.start_time:
        raise ValidationFailedError("end_time cannot be before start_time.")

    tariff = await get_ev_tariff_or_404(db, station_id, session.tariff_id)
    delivered_kwh = payload.end_meter_kwh - session.start_meter_kwh
    duration_minutes = Decimal((end_time - session.start_time).total_seconds()) / Decimal(60)
    gross_amount = _compute_gross_amount(tariff.pricing_basis, tariff.rate, delivered_kwh, duration_minutes)

    if payload.payment_method_id is not None:
        await get_payment_method_or_404(db, organization_id, payload.payment_method_id)

    session.end_meter_kwh = payload.end_meter_kwh
    session.end_time = end_time
    session.delivered_kwh = delivered_kwh
    session.gross_amount = gross_amount
    session.payment_method_id = payload.payment_method_id
    session.status = EVSessionStatus.COMPLETED.value

    port = await get_ev_charger_port_in_station_or_404(db, station_id, session.port_id, for_update=True)
    port.status = PortStatus.AVAILABLE.value
    await db.flush()

    await write_audit_log(
        db,
        action="ev_charging_session.close",
        entity_type=ENTITY_TYPE,
        entity_id=str(session.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={
            "status": session.status,
            **_decimal_fields(session, ["end_meter_kwh", "delivered_kwh", "gross_amount"]),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return session


@router.patch("/{session_id}/fail", response_model=EVChargingSessionRead)
async def fail_ev_charging_session(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    session_id: uuid.UUID,
    payload: EVChargingSessionFail,
    request: Request,
    current_user: User = Depends(require_permission(EV_SESSION_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> EVChargingSession:
    """No energy/amount is computed - a session that never delivered a
    trustworthy meter reading must not get an invented gross_amount."""
    session = await _get_session_or_404(db, station_id, session_id, for_update=True)
    if session.status not in (EVSessionStatus.INITIATED.value, EVSessionStatus.CHARGING.value):
        raise ConflictError(f"Session is '{session.status}' - only an initiated/charging session can be marked {payload.status}.")

    session.status = payload.status
    session.fault_reason = payload.fault_reason
    session.end_time = datetime.now(timezone.utc)

    port = await get_ev_charger_port_in_station_or_404(db, station_id, session.port_id, for_update=True)
    port.status = PortStatus.AVAILABLE.value if payload.status == "cancelled" else PortStatus.FAULTED.value
    await db.flush()

    await write_audit_log(
        db,
        action="ev_charging_session.fail",
        entity_type=ENTITY_TYPE,
        entity_id=str(session.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"status": session.status, "fault_reason": session.fault_reason},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return session


@router.patch("/{session_id}/reverse", response_model=EVChargingSessionRead)
async def reverse_ev_charging_session(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    session_id: uuid.UUID,
    payload: EVChargingSessionReverse,
    request: Request,
    current_user: User = Depends(require_permission(EV_SESSION_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> EVChargingSession:
    """
    Reversal (not deletion), same as ShiftTender.reverse - the original
    row, including who entered what, is never erased. Only a COMPLETED
    session can be reversed (there's a completed financial fact to
    correct); an already-reversed one can't be reversed twice.
    """
    session = await _get_session_or_404(db, station_id, session_id, for_update=True)
    if session.status != EVSessionStatus.COMPLETED.value:
        raise ConflictError(f"Session is '{session.status}' - only a completed session can be reversed.")
    if session.reversed_at is not None:
        raise ConflictError("This session has already been reversed.")

    session.reversed_by_user_id = current_user.id
    session.reversed_at = datetime.now(timezone.utc)
    session.reversal_reason = payload.reason
    session.status = EVSessionStatus.REFUNDED.value
    await db.flush()

    await write_audit_log(
        db,
        action="ev_charging_session.reverse",
        entity_type=ENTITY_TYPE,
        entity_id=str(session.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"reason": payload.reason},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return session
