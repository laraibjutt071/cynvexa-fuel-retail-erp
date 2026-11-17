"""Phase 3: add business-contact fields to organizations for Super Admin tenant management

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-11-18

Purely additive, all nullable - no existing row changes, no existing
column touched. Needed so the Super Admin "Create Petrol Pump" workflow
can capture the business's own contact/address information, which
Organization never had a place for before this phase.
"""

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6g7h8i9"
down_revision = "c3d4e5f6g7h8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("phone", sa.String(length=30), nullable=True))
    op.add_column("organizations", sa.Column("address", sa.String(length=300), nullable=True))
    op.add_column("organizations", sa.Column("city", sa.String(length=100), nullable=True))
    op.add_column("organizations", sa.Column("province", sa.String(length=100), nullable=True))
    op.add_column("organizations", sa.Column("country", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "country")
    op.drop_column("organizations", "province")
    op.drop_column("organizations", "city")
    op.drop_column("organizations", "address")
    op.drop_column("organizations", "phone")
