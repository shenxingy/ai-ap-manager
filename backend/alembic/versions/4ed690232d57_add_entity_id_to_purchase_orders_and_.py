"""add entity_id to purchase_orders and goods_receipts

Revision ID: 4ed690232d57
Revises: gap12_invoice_templates
Create Date: 2026-03-01 19:28:48.657584

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '4ed690232d57'
down_revision: str | None = 'gap12_invoice_templates'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No-op: entity_id was already added to purchase_orders and goods_receipts
    # by gap9_multi_entity migration which runs earlier in the chain.
    pass


def downgrade() -> None:
    pass
