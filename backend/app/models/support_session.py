import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class SupportSession(UUIDPKMixin, TimestampMixin, Base):
    """
    Phase 5b: the only way a platform Super Admin may read a tenant's
    business data (stations, users, fuel, shifts, financial, inventory,
    attendance, audit log, reports) - see app/core/support_sessions.py and
    app/api/deps.py::require_permission. Strictly read-only: there is no
    write_permissions column at all, deliberately, per the owner's review
    of this phase's design. Organization profile read/update and
    suspend/reactivate are NOT gated by this - those stay direct
    superuser actions (app/api/deps.py's require_permission carve-out).

    At most one non-ended session may exist per superuser at a time,
    enforced by ix_support_sessions_one_active_per_admin (a partial unique
    index on superuser_id WHERE ended_at IS NULL) plus a row lock on
    creation (app/api/support_sessions.py) - closing the race where two
    concurrent requests could otherwise both create one.
    """

    __tablename__ = "support_sessions"
    __table_args__ = (
        Index("ix_support_sessions_superuser_org", "superuser_id", "organization_id"),
        # At most one non-ended session per superuser, enforced at the
        # database level (not just in application code) - see
        # app/api/support_sessions.py::create_support_session.
        Index(
            "ix_support_sessions_one_active_per_admin",
            "superuser_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
    )

    superuser_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    station_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stations.id", ondelete="CASCADE"), nullable=True
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
