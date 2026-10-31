from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(300), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Platform-level administrator (CYNVEXA operator), not a station role. Only this flag
    # may create a new Organization — see app/core/permissions.py::require_superuser.
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    station_roles: Mapped[list["UserStationRole"]] = relationship(back_populates="user")
