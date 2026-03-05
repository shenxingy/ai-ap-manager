"""add_approval_required_count

Revision ID: b8479ee361ad
Revises: 30c7aa8ecaf1
Create Date: 2026-02-27 10:03:04.881406

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8479ee361ad'
down_revision: str | None = '30c7aa8ecaf1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'approval_tasks',
        sa.Column('approval_required_count', sa.Integer(), nullable=False, server_default='1'),
    )


def downgrade() -> None:
    op.drop_column('approval_tasks', 'approval_required_count')
