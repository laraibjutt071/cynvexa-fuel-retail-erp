import uuid

from sqlalchemy import Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin
from app.models.role import Role


class UserStationRole(UUIDPKMixin, TimestampMixin, Base):
    """
    Grants a user a role within an organization, optionally scoped to one station.
    station_id = NULL means the role applies across every station in the organization
    (e.g. an Owner). This row, filtered by organization_id (and station_id when set),
    is the sole access-isolation boundary enforced in app/core/permissions.py.
    """

    __tablename__ = "user_station_roles"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "organization_id", "station_id", "role_id", name="uq_user_org_station_role"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    station_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stations.id", ondelete="CASCADE"), nullable=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship(back_populates="station_roles")
    role: Mapped[Role] = relationship()
