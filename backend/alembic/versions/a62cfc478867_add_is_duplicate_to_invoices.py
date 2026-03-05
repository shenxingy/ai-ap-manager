"""add is_duplicate to invoices

Revision ID: a62cfc478867
Revises: c4f57a15b205
Create Date: 2026-02-27 18:46:33.582915

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a62cfc478867'
down_revision: str | None = 'c4f57a15b205'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('invoices', sa.Column('is_duplicate', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('invoices', 'is_duplicate')
