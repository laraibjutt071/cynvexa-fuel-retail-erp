import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import UUIDPKMixin, utcnow


class AuditLog(UUIDPKMixin, Base):
    """
    Append-only. Written in the same DB transaction as the mutation it records.
    Never updated or deleted by application code.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        # Every list/export query filters by organization_id and sorts by
        # created_at desc (see app/api/audit.py) - a composite index lets
        # Postgres satisfy both the filter and the ORDER BY from one index
        # scan instead of a sequential scan + sort as the table grows.
        Index("ix_audit_logs_org_created_at", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    # NULL means an org-level event (e.g. organization profile change, user
    # creation) that isn't tied to one station - everyone with AUDIT_READ in
    # the org sees those. A station-scoped viewer must NOT see another
    # station's events; see app/api/audit.py's filtering.
    station_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
