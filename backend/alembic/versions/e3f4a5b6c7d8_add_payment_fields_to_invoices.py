"""add payment fields to invoices

Revision ID: e3f4a5b6c7d8
Revises: e5f6a7b8c9d0
Create Date: 2026-02-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'e3f4a5b6c7d8'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('invoices', sa.Column('payment_status', sa.String(50), nullable=True))
    op.add_column('invoices', sa.Column('payment_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('invoices', sa.Column('payment_method', sa.String(50), nullable=True))
    op.add_column('invoices', sa.Column('payment_reference', sa.String(100), nullable=True))
    op.create_index('ix_invoices_payment_status', 'invoices', ['payment_status'])


def downgrade() -> None:
    op.drop_index('ix_invoices_payment_status', table_name='invoices')
    op.drop_column('invoices', 'payment_reference')
    op.drop_column('invoices', 'payment_method')
    op.drop_column('invoices', 'payment_date')
    op.drop_column('invoices', 'payment_status')
