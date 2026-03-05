"""create fx_rates table and add normalized_amount_usd to invoices

Revision ID: gap3_fx_rates
Revises: gap11_vendor_risk_scores
Create Date: 2026-03-01 00:00:00.000000
"""
import sqlalchemy as sa

from alembic import op

revision = 'gap3_fx_rates'
down_revision = 'gap11_vendor_risk_scores'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'fx_rates',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('base_currency', sa.String(3), nullable=False),
        sa.Column('quote_currency', sa.String(3), nullable=False),
        sa.Column('rate', sa.Float, nullable=False),
        sa.Column('valid_date', sa.Date, nullable=False),
        sa.Column('source', sa.String(20), nullable=False, server_default='ecb'),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('base_currency', 'quote_currency', 'valid_date', name='uq_fx_rate_pair_date'),
    )
    # normalized_amount_usd was added by a prior migration; add only if missing
    conn = op.get_bind()
    cols = [row[0] for row in conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='invoices' AND column_name='normalized_amount_usd'"
    ))]
    if not cols:
        op.add_column('invoices', sa.Column('normalized_amount_usd', sa.Numeric(18, 4), nullable=True))


def downgrade():
    op.drop_table('fx_rates')
    op.drop_column('invoices', 'normalized_amount_usd')
