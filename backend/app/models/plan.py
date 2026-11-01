from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class Plan(UUIDPKMixin, TimestampMixin, Base):
    """
    A platform-wide subscription package (Starter/Business/Enterprise are the
    master prompt's own example names, not fixed products) - one row per plan,
    shared across every customer organization, managed only by a platform
    administrator (see app/api/platform.py). Limits are nullable = unlimited,
    never a hardcoded number in business logic - enforcement reads this row.
    """

    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_monthly: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_annual: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # NULL = unlimited. Enforcing these limits against actual station/user
    # counts is not implemented yet - see docs/ASSUMPTIONS.md.
    max_stations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
