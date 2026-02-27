"""add fraud triggered signals column

Revision ID: 30c7aa8ecaf1
Revises: 9043f7a6e972
Create Date: 2026-02-27 08:43:10.908289

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '30c7aa8ecaf1'
down_revision: Union[str, None] = '9043f7a6e972'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'invoices',
        sa.Column(
            'fraud_triggered_signals',
            sa.JSON(),
            nullable=False,
            server_default='[]',
        ),
    )


def downgrade() -> None:
    op.drop_column('invoices', 'fraud_triggered_signals')
