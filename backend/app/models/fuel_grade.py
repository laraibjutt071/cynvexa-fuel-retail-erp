import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class FuelGrade(UUIDPKMixin, TimestampMixin, Base):
    """
    Organization-wide catalogue entry (e.g. "Petrol 92", "Diesel") - shared
    across every station in the org, not station-specific. A Tank holds one
    grade; a Nozzle serves whatever grade its tank holds.
    """

    __tablename__ = "fuel_grades"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_fuel_grade_org_code"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
