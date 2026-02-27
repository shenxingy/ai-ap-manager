"""add source_email to invoices

Revision ID: e5f6a7b8c9d0
Revises: 2ac83ef6dfcc
Create Date: 2026-02-27 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = '2ac83ef6dfcc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('invoices', sa.Column('source_email', sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column('invoices', 'source_email')
