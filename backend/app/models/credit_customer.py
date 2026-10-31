import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class CreditCustomer(UUIDPKMixin, TimestampMixin, Base):
    """
    Deliberately minimal - just enough identity for a ShiftTender to record
    WHO a credit sale's receivable belongs to. Credit limits, running
    balance, ageing and statements are Phase E's "Credit / Fleet Customers"
    scope, not duplicated here. See docs/ASSUMPTIONS.md #22.
    """

    __tablename__ = "credit_customers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
