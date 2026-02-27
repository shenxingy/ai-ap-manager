"""add_fraud_incidents_and_recurring_patterns

Revision ID: 85d0d489d232
Revises: 38c1697a3bb1
Create Date: 2026-02-27 16:58:11.494687

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '85d0d489d232'
down_revision: Union[str, None] = '38c1697a3bb1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New tables: vendor_bank_histories, fraud_incidents
    op.create_table('vendor_bank_histories',
        sa.Column('vendor_id', sa.UUID(), nullable=False),
        sa.Column('bank_account_number', sa.String(length=64), nullable=False),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('changed_by', sa.UUID(), nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_vendor_bank_histories_bank_account_number'), 'vendor_bank_histories', ['bank_account_number'], unique=False)
    op.create_index(op.f('ix_vendor_bank_histories_vendor_id'), 'vendor_bank_histories', ['vendor_id'], unique=False)

    op.create_table('fraud_incidents',
        sa.Column('invoice_id', sa.UUID(), nullable=False),
        sa.Column('score_at_flag', sa.Integer(), nullable=False),
        sa.Column('triggered_signals', sa.JSON(), nullable=False),
        sa.Column('reviewed_by', sa.UUID(), nullable=True),
        sa.Column('outcome', sa.String(length=50), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_fraud_incidents_invoice_id'), 'fraud_incidents', ['invoice_id'], unique=False)

    # Evolve recurring_invoice_patterns: add new columns, remove legacy columns
    op.add_column('recurring_invoice_patterns', sa.Column('frequency_days', sa.Integer(), nullable=True))
    op.add_column('recurring_invoice_patterns', sa.Column('avg_amount', sa.Numeric(precision=18, scale=4), nullable=True))
    op.add_column('recurring_invoice_patterns', sa.Column('tolerance_pct', sa.Float(), nullable=True))
    op.add_column('recurring_invoice_patterns', sa.Column('auto_fast_track', sa.Boolean(), nullable=True))
    # Set defaults for existing rows (none expected in dev, but be safe)
    op.execute("UPDATE recurring_invoice_patterns SET frequency_days = 30, avg_amount = 0, tolerance_pct = 0.10, auto_fast_track = false WHERE frequency_days IS NULL")
    op.alter_column('recurring_invoice_patterns', 'frequency_days', nullable=False)
    op.alter_column('recurring_invoice_patterns', 'avg_amount', nullable=False)
    op.alter_column('recurring_invoice_patterns', 'tolerance_pct', nullable=False)
    op.alter_column('recurring_invoice_patterns', 'auto_fast_track', nullable=False)
    op.create_unique_constraint('uq_recurring_pattern_vendor', 'recurring_invoice_patterns', ['vendor_id'])
    op.drop_column('recurring_invoice_patterns', 'frequency')
    op.drop_column('recurring_invoice_patterns', 'description_pattern')
    op.drop_column('recurring_invoice_patterns', 'is_active')
    op.drop_column('recurring_invoice_patterns', 'expected_amount')
    op.drop_column('recurring_invoice_patterns', 'amount_tolerance_pct')


def downgrade() -> None:
    op.add_column('recurring_invoice_patterns', sa.Column('amount_tolerance_pct', sa.NUMERIC(precision=5, scale=4), nullable=False, server_default='0.05'))
    op.add_column('recurring_invoice_patterns', sa.Column('expected_amount', sa.NUMERIC(precision=18, scale=4), nullable=True))
    op.add_column('recurring_invoice_patterns', sa.Column('is_active', sa.BOOLEAN(), nullable=False, server_default='true'))
    op.add_column('recurring_invoice_patterns', sa.Column('description_pattern', sa.VARCHAR(length=500), nullable=True))
    op.add_column('recurring_invoice_patterns', sa.Column('frequency', sa.VARCHAR(length=50), nullable=False, server_default='monthly'))
    op.drop_constraint('uq_recurring_pattern_vendor', 'recurring_invoice_patterns', type_='unique')
    op.drop_column('recurring_invoice_patterns', 'auto_fast_track')
    op.drop_column('recurring_invoice_patterns', 'tolerance_pct')
    op.drop_column('recurring_invoice_patterns', 'avg_amount')
    op.drop_column('recurring_invoice_patterns', 'frequency_days')
    op.drop_index(op.f('ix_fraud_incidents_invoice_id'), table_name='fraud_incidents')
    op.drop_table('fraud_incidents')
    op.drop_index(op.f('ix_vendor_bank_histories_vendor_id'), table_name='vendor_bank_histories')
    op.drop_index(op.f('ix_vendor_bank_histories_bank_account_number'), table_name='vendor_bank_histories')
    op.drop_table('vendor_bank_histories')
