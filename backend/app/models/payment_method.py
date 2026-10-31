import enum
import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class PaymentMethodCategory(str, enum.Enum):
    """
    The category drives reconciliation math (which methods count toward
    physical cash vs. a receivable), the specific PaymentMethod rows within
    a category are the station's own configurable list - e.g. "Visa",
    "Easypaisa" and "JazzCash" might all be separate DIGITAL methods.
    """

    CASH = "cash"
    CARD = "card"
    DIGITAL = "digital"
    CREDIT = "credit"


class PaymentMethod(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "payment_methods"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_payment_method_org_code"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(10), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
