import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class SubscriptionPaymentStatus(str, enum.Enum):
    VERIFIED = "verified"
    FAILED = "failed"


class SubscriptionPayment(UUIDPKMixin, TimestampMixin, Base):
    """
    A manually-recorded, manually-verified subscription payment - there is no
    payment gateway integration yet (see docs/ASSUMPTIONS.md), so every row
    here is entered directly by a platform administrator who is personally
    attesting the payment was received, not a customer-submitted, pending
    claim. recorded_by_user_id is therefore also the verifier, and
    created_at (TimestampMixin) is effectively the verification timestamp -
    there is deliberately no separate "unverified/pending" state, to avoid
    pretending a two-step review process exists when it doesn't yet.
    """

    __tablename__ = "subscription_payments"

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[str] = mapped_column(String(50), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[SubscriptionPaymentStatus] = mapped_column(
        Enum(SubscriptionPaymentStatus, name="subscription_payment_status"), nullable=False
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
