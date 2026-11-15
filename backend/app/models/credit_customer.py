import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin

MONEY = Numeric(14, 2)


class CreditCustomer(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "credit_customers"
    __table_args__ = (
        CheckConstraint("credit_limit IS NULL OR credit_limit >= 0", name="ck_credit_customer_credit_limit_nonneg"),
        CheckConstraint(
            "payment_terms_days IS NULL OR payment_terms_days > 0",
            name="ck_credit_customer_payment_terms_positive",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact_person: Mapped[str | None] = mapped_column(String(200), nullable=True)
    credit_limit: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    payment_terms_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
