from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class Organization(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Label only (e.g. ISO 4217 "PKR", "USD") - purely informational for
    # display. No currency conversion, multi-currency, or FX handling exists
    # anywhere in this system; every money field assumes a single implicit
    # currency per organization. See docs/ASSUMPTIONS.md #19.
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)

    stations: Mapped[list["Station"]] = relationship(back_populates="organization")
