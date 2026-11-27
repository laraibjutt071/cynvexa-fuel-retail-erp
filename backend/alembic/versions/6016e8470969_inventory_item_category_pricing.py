"""inventory_item_category_pricing

Revision ID: 6016e8470969
Revises: 74859ec42df9
Create Date: 2026-11-27 23:19:57.420558

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6016e8470969'
down_revision: Union[str, None] = '74859ec42df9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default backfills any existing row (NOT NULL with no default
    # otherwise fails against real data) - matches the model's own Python
    # defaults, so new rows via the ORM and this migration's backfill agree.
    op.add_column(
        'inventory_items', sa.Column('category', sa.String(length=50), nullable=False, server_default='other')
    )
    op.add_column(
        'inventory_items', sa.Column('unit_cost', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0')
    )
    op.add_column(
        'inventory_items', sa.Column('selling_price', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0')
    )
    op.create_check_constraint('ck_inventory_item_unit_cost_nonnegative', 'inventory_items', 'unit_cost >= 0')
    op.create_check_constraint('ck_inventory_item_selling_price_nonnegative', 'inventory_items', 'selling_price >= 0')


def downgrade() -> None:
    op.drop_constraint('ck_inventory_item_selling_price_nonnegative', 'inventory_items', type_='check')
    op.drop_constraint('ck_inventory_item_unit_cost_nonnegative', 'inventory_items', type_='check')
    op.drop_column('inventory_items', 'selling_price')
    op.drop_column('inventory_items', 'unit_cost')
    op.drop_column('inventory_items', 'category')
