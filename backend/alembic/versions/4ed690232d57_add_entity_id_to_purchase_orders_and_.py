"""add entity_id to purchase_orders and goods_receipts

Revision ID: 4ed690232d57
Revises: gap12_invoice_templates
Create Date: 2026-03-01 19:28:48.657584

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4ed690232d57'
down_revision: Union[str, None] = 'gap12_invoice_templates'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('purchase_orders', sa.Column(
        'entity_id', postgresql.UUID(as_uuid=True), nullable=True
    ))
    op.create_foreign_key(
        'fk_purchase_orders_entity_id', 'purchase_orders',
        'entities', ['entity_id'], ['id']
    )
    op.create_index('ix_purchase_orders_entity_id', 'purchase_orders', ['entity_id'])

    op.add_column('goods_receipts', sa.Column(
        'entity_id', postgresql.UUID(as_uuid=True), nullable=True
    ))
    op.create_foreign_key(
        'fk_goods_receipts_entity_id', 'goods_receipts',
        'entities', ['entity_id'], ['id']
    )
    op.create_index('ix_goods_receipts_entity_id', 'goods_receipts', ['entity_id'])


def downgrade() -> None:
    op.drop_index('ix_goods_receipts_entity_id', table_name='goods_receipts')
    op.drop_constraint('fk_goods_receipts_entity_id', 'goods_receipts', type_='foreignkey')
    op.drop_column('goods_receipts', 'entity_id')

    op.drop_index('ix_purchase_orders_entity_id', table_name='purchase_orders')
    op.drop_constraint('fk_purchase_orders_entity_id', 'purchase_orders', type_='foreignkey')
    op.drop_column('purchase_orders', 'entity_id')
