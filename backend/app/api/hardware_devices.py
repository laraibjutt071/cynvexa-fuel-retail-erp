import asyncio
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_station_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import STATION_UPDATE
from app.exceptions import NotFoundError, ValidationFailedError
from app.models.hardware_device import HardwareConnectionType, HardwareDevice, HardwareDeviceStatus
from app.models.user import User
from app.schemas.hardware_device import HardwareDeviceCreate, HardwareDeviceRead, HardwareDeviceTestResult

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/hardware-devices",
    tags=["hardware-devices"],
)

# A hard ceiling on the connect attempt below - this request must not hang
# the API waiting on a forecourt device that never answers.
CONNECT_TIMEOUT_SECONDS = 4.0


async def _get_device_or_404(db: AsyncSession, station_id: uuid.UUID, device_id: uuid.UUID) -> HardwareDevice:
    device = (
        await db.execute(
            select(HardwareDevice).where(HardwareDevice.id == device_id, HardwareDevice.station_id == station_id)
        )
    ).scalar_one_or_none()
    if device is None:
        raise NotFoundError("Hardware device not found.")
    return device


@router.post("", response_model=HardwareDeviceRead, status_code=201)
async def start_hardware_connection(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    payload: HardwareDeviceCreate,
    request: Request,
    current_user: User = Depends(require_permission(STATION_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> HardwareDevice:
    """Step 1 of the connection wizard: record what the device is and how
    it should be reached. Nothing is contacted yet - see test_connection."""
    await get_station_or_404(db, organization_id, station_id)

    device = HardwareDevice(
        station_id=station_id,
        created_by_user_id=current_user.id,
        status=HardwareDeviceStatus.DRAFT.value,
        **payload.model_dump(exclude={"device_type", "connection_type"}),
        device_type=payload.device_type.value,
        connection_type=payload.connection_type.value,
    )
    db.add(device)
    await db.flush()

    await write_audit_log(
        db,
        action="hardware_device.create",
        entity_type="HardwareDevice",
        entity_id=str(device.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"device_type": device.device_type, "label": device.label, "connection_type": device.connection_type},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return device


@router.get("", response_model=list[HardwareDeviceRead])
async def list_hardware_devices(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    current_user: User = Depends(require_permission(STATION_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> list[HardwareDevice]:
    result = await db.execute(select(HardwareDevice).where(HardwareDevice.station_id == station_id))
    return list(result.scalars().all())


@router.post("/{device_id}/test-connection", response_model=HardwareDeviceTestResult)
async def test_hardware_connection(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    device_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission(STATION_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> HardwareDeviceTestResult:
    """
    The one step in this wizard that actually does something to a network,
    rather than just recording intent: for a tcp_ip device, this opens a
    real TCP socket to the given host:port from this backend's own
    network. A success here means "this server can reach that address",
    not "the vendor's dispenser/ATG/biometric-device protocol handshake
    succeeded" - there is no protocol driver in this project for any real
    forecourt or biometric hardware.
    A serial (COM port) device can't be tested this way at all: the
    backend runs on a server, not on the till PC physically wired to the
    device, so that check is explicitly handed back to the on-site
    technician rather than faked as a pass.
    """
    device = await _get_device_or_404(db, station_id, device_id)

    if device.connection_type == HardwareConnectionType.SERIAL.value:
        device.status = HardwareDeviceStatus.FAILED.value
        device.last_test_message = (
            "Serial (COM port) devices are wired directly into the till PC at the station - this "
            "server cannot reach them over the network. Ask your on-site technician to confirm the "
            "cable is connected and the device responds using the vendor's own diagnostic tool."
        )
    else:
        if not device.ip_address or not device.port:
            raise ValidationFailedError("This device has no ip_address/port recorded to test.")
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(device.ip_address, device.port), timeout=CONNECT_TIMEOUT_SECONDS
            )
            writer.close()
            device.status = HardwareDeviceStatus.CONNECTED.value
            device.last_test_message = f"Reached {device.ip_address}:{device.port} successfully."
        except Exception as exc:
            device.status = HardwareDeviceStatus.FAILED.value
            device.last_test_message = (
                f"Could not reach {device.ip_address}:{device.port} ({type(exc).__name__}: {exc}). "
                "Check the device is powered on, the IP/port are correct, and this station's network "
                "allows the connection (firewall, VLAN, VPN)."
            )

    await db.flush()
    await write_audit_log(
        db,
        action="hardware_device.test_connection",
        entity_type="HardwareDevice",
        entity_id=str(device.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"status": device.status, "message": device.last_test_message},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return HardwareDeviceTestResult(status=device.status, message=device.last_test_message or "", device=device)
