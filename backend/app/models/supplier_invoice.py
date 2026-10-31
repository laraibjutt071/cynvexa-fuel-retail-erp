import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin

MONEY = Numeric(14, 2)


class SupplierInvoice(UUIDPKMixin, TimestampMixin, Base):
    """
    Money the organization owes a supplier - e.g. for a tanker delivery or
    any other supplier charge. Deliberately NOT derived from
    TankerReceipt.accepted_quantity * some price: this system has never
    captured a fuel purchase price anywhere (FuelPrice is the SELLING
    price), so the amount owed is recorded directly, the same way a
    receipt's payable_quantity_basis is a recorded decision, not a
    computed one. See docs/ASSUMPTIONS.md #26.
    """

    __tablename__ = "supplier_invoices"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_supplier_invoice_amount_positive"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    tanker_receipt_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tanker_receipts.id", ondelete="SET NULL"), nullable=True
    )
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
