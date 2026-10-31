import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class Nozzle(UUIDPKMixin, TimestampMixin, Base):
    """
    A nozzle serves whatever fuel grade its tank holds (no separate
    fuel_grade_id here - it would just be able to disagree with the tank's).
    The API layer validates dispenser and tank belong to the same station.
    """

    __tablename__ = "nozzles"
    __table_args__ = (UniqueConstraint("dispenser_id", "code", name="uq_nozzle_dispenser_code"),)

    dispenser_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dispensers.id", ondelete="CASCADE"), nullable=False
    )
    tank_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tanks.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
