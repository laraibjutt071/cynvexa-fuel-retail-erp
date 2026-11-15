"""Day 2: reading corrections, FK safety, tank fields, credit customer fields

Revision ID: a1b2c3d4e5f6
Revises: 56260bf7064a
Create Date: 2026-11-14

Changes:
1. Create reading_corrections table (24-hour correction policy)
2. Change ondelete CASCADE → RESTRICT on shift_tank_readings.shift_id
   and shift_nozzle_readings.shift_id to prevent accidental data loss
3. Add tank.location and tank.calibration_reference columns
4. Add credit_customer fields: phone, contact_person, credit_limit,
   payment_terms_days, address, notes
5. Seed reading:correct and reading:correct_approve permissions
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '56260bf7064a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. reading_corrections table
    op.create_table(
        'reading_corrections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('station_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('stations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('shift_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('shifts.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('reading_type', sa.String(30), nullable=False),
        sa.Column('tank_reading_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('shift_tank_readings.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('nozzle_reading_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('shift_nozzle_readings.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('original_value', sa.Numeric(14, 3), nullable=False),
        sa.Column('corrected_value', sa.Numeric(14, 3), nullable=False),
        sa.Column('reason', sa.String(1000), nullable=False),
        sa.Column('original_submitted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_post_lock', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('status', sa.String(10), nullable=False, server_default='pending'),
        sa.Column('requested_by_user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column('decided_by_user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.String(500), nullable=True),
        sa.CheckConstraint('original_value >= 0', name='ck_reading_correction_original_nonneg'),
        sa.CheckConstraint('corrected_value >= 0', name='ck_reading_correction_corrected_nonneg'),
    )
    op.create_index('ix_reading_corrections_organization_id', 'reading_corrections', ['organization_id'])
    op.create_index('ix_reading_corrections_station_id', 'reading_corrections', ['station_id'])
    op.create_index('ix_reading_corrections_shift_id', 'reading_corrections', ['shift_id'])

    # 2. Change CASCADE → RESTRICT on shift_tank_readings.shift_id
    op.drop_constraint('shift_tank_readings_shift_id_fkey', 'shift_tank_readings', type_='foreignkey')
    op.create_foreign_key(
        'shift_tank_readings_shift_id_fkey', 'shift_tank_readings',
        'shifts', ['shift_id'], ['id'], ondelete='RESTRICT',
    )

    # Change CASCADE → RESTRICT on shift_nozzle_readings.shift_id
    op.drop_constraint('shift_nozzle_readings_shift_id_fkey', 'shift_nozzle_readings', type_='foreignkey')
    op.create_foreign_key(
        'shift_nozzle_readings_shift_id_fkey', 'shift_nozzle_readings',
        'shifts', ['shift_id'], ['id'], ondelete='RESTRICT',
    )

    # 3. Tank: add location and calibration_reference
    op.add_column('tanks', sa.Column('location', sa.String(200), nullable=True))
    op.add_column('tanks', sa.Column('calibration_reference', sa.String(500), nullable=True))

    # 4. Credit customer: add contact/financial fields
    op.add_column('credit_customers', sa.Column('phone', sa.String(50), nullable=True))
    op.add_column('credit_customers', sa.Column('contact_person', sa.String(200), nullable=True))
    op.add_column('credit_customers', sa.Column('credit_limit', sa.Numeric(14, 2), nullable=True))
    op.add_column('credit_customers', sa.Column('payment_terms_days', sa.Integer(), nullable=True))
    op.add_column('credit_customers', sa.Column('address', sa.String(500), nullable=True))
    op.add_column('credit_customers', sa.Column('notes', sa.String(1000), nullable=True))
    op.create_check_constraint(
        'ck_credit_customer_credit_limit_nonneg', 'credit_customers', 'credit_limit IS NULL OR credit_limit >= 0'
    )
    op.create_check_constraint(
        'ck_credit_customer_payment_terms_positive', 'credit_customers',
        'payment_terms_days IS NULL OR payment_terms_days > 0'
    )

    # 5. Seed new permissions
    permissions_table = sa.table(
        'permissions',
        sa.column('id', postgresql.UUID(as_uuid=True)),
        sa.column('code', sa.String),
        sa.column('description', sa.String),
        sa.column('created_at', sa.DateTime(timezone=True)),
        sa.column('updated_at', sa.DateTime(timezone=True)),
    )
    import uuid
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    op.bulk_insert(permissions_table, [
        {
            'id': str(uuid.uuid4()),
            'code': 'reading:correct',
            'description': 'Request a correction to a submitted reading within the 24-hour window or propose a post-lock amendment.',
            'created_at': now,
            'updated_at': now,
        },
        {
            'id': str(uuid.uuid4()),
            'code': 'reading:correct_approve',
            'description': 'Approve or reject a reading correction or post-lock amendment request.',
            'created_at': now,
            'updated_at': now,
        },
    ])


def downgrade() -> None:
    # Remove permissions
    op.execute("DELETE FROM permissions WHERE code IN ('reading:correct', 'reading:correct_approve')")

    # Remove credit customer constraints and columns
    op.drop_constraint('ck_credit_customer_payment_terms_positive', 'credit_customers', type_='check')
    op.drop_constraint('ck_credit_customer_credit_limit_nonneg', 'credit_customers', type_='check')
    op.drop_column('credit_customers', 'notes')
    op.drop_column('credit_customers', 'address')
    op.drop_column('credit_customers', 'payment_terms_days')
    op.drop_column('credit_customers', 'credit_limit')
    op.drop_column('credit_customers', 'contact_person')
    op.drop_column('credit_customers', 'phone')

    # Remove tank columns
    op.drop_column('tanks', 'calibration_reference')
    op.drop_column('tanks', 'location')

    # Restore CASCADE on nozzle readings
    op.drop_constraint('shift_nozzle_readings_shift_id_fkey', 'shift_nozzle_readings', type_='foreignkey')
    op.create_foreign_key(
        'shift_nozzle_readings_shift_id_fkey', 'shift_nozzle_readings',
        'shifts', ['shift_id'], ['id'], ondelete='CASCADE',
    )

    # Restore CASCADE on tank readings
    op.drop_constraint('shift_tank_readings_shift_id_fkey', 'shift_tank_readings', type_='foreignkey')
    op.create_foreign_key(
        'shift_tank_readings_shift_id_fkey', 'shift_tank_readings',
        'shifts', ['shift_id'], ['id'], ondelete='CASCADE',
    )

    # Drop reading_corrections
    op.drop_index('ix_reading_corrections_shift_id', 'reading_corrections')
    op.drop_index('ix_reading_corrections_station_id', 'reading_corrections')
    op.drop_index('ix_reading_corrections_organization_id', 'reading_corrections')
    op.drop_table('reading_corrections')
