"""multi-entity support: create entities table, add entity_id FK

Revision ID: gap9_multi_entity
Revises: gap3_fx_rates
Create Date: 2026-03-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'gap9_multi_entity'
down_revision = 'gap3_fx_rates'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'entities',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('tax_id', sa.String(50), nullable=True),
        sa.Column('base_currency', sa.String(3), nullable=False, server_default='USD'),
        sa.Column('timezone', sa.String(50), nullable=False, server_default='UTC'),
        sa.Column('contact_info', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Add entity_id to invoices
    op.add_column('invoices', sa.Column('entity_id', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_invoices_entity_id', 'invoices', 'entities', ['entity_id'], ['id']
    )
    op.create_index('ix_invoices_entity_id', 'invoices', ['entity_id'])

    # Add entity_id to vendors
    op.add_column('vendors', sa.Column('entity_id', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_vendors_entity_id', 'vendors', 'entities', ['entity_id'], ['id']
    )
    op.create_index('ix_vendors_entity_id', 'vendors', ['entity_id'])

    # Add entity_id to purchase_orders (if table exists)
    conn = op.get_bind()
    tables = [row[0] for row in conn.execute(sa.text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='purchase_orders'"
    ))]
    if tables:
        op.add_column('purchase_orders', sa.Column('entity_id', UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            'fk_po_entity_id', 'purchase_orders', 'entities', ['entity_id'], ['id']
        )
        op.create_index('ix_purchase_orders_entity_id', 'purchase_orders', ['entity_id'])

    # Add entity_id to goods_receipts (if table exists)
    gr_tables = [row[0] for row in conn.execute(sa.text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='goods_receipts'"
    ))]
    if gr_tables:
        op.add_column('goods_receipts', sa.Column('entity_id', UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            'fk_gr_entity_id', 'goods_receipts', 'entities', ['entity_id'], ['id']
        )
        op.create_index('ix_goods_receipts_entity_id', 'goods_receipts', ['entity_id'])


def downgrade():
    conn = op.get_bind()

    gr_tables = [row[0] for row in conn.execute(sa.text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='goods_receipts'"
    ))]
    if gr_tables:
        op.drop_index('ix_goods_receipts_entity_id', table_name='goods_receipts')
        op.drop_constraint('fk_gr_entity_id', 'goods_receipts', type_='foreignkey')
        op.drop_column('goods_receipts', 'entity_id')

    po_tables = [row[0] for row in conn.execute(sa.text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='purchase_orders'"
    ))]
    if po_tables:
        op.drop_index('ix_purchase_orders_entity_id', table_name='purchase_orders')
        op.drop_constraint('fk_po_entity_id', 'purchase_orders', type_='foreignkey')
        op.drop_column('purchase_orders', 'entity_id')

    op.drop_index('ix_vendors_entity_id', table_name='vendors')
    op.drop_constraint('fk_vendors_entity_id', 'vendors', type_='foreignkey')
    op.drop_column('vendors', 'entity_id')

    op.drop_index('ix_invoices_entity_id', table_name='invoices')
    op.drop_constraint('fk_invoices_entity_id', 'invoices', type_='foreignkey')
    op.drop_column('invoices', 'entity_id')

    op.drop_table('entities')
