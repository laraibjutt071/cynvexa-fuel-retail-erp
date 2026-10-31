import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import UUIDPKMixin, utcnow


class Attachment(UUIDPKMixin, Base):
    """
    Evidence attached to an approvable record (a tanker receipt today;
    polymorphic by entity_type/entity_id so later phases can reuse it rather
    than growing a parallel attachments table per entity).

    storage_backend/storage_key: Phase B stores the file on local disk
    (storage_backend="local"), which is explicitly NOT how this should work
    in a real deployed environment with more than one backend instance or
    any expectation of durability - see docs/ASSUMPTIONS.md. Swapping to S3
    or equivalent only needs a different storage_backend value and a
    different reader/writer; the schema already supports it.
    """

    __tablename__ = "attachments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(20), nullable=False, default="local")
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
