"""add_approval_required_count

Revision ID: b8479ee361ad
Revises: 30c7aa8ecaf1
Create Date: 2026-02-27 10:03:04.881406

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8479ee361ad'
down_revision: Union[str, None] = '30c7aa8ecaf1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'approval_tasks',
        sa.Column('approval_required_count', sa.Integer(), nullable=False, server_default='1'),
    )


def downgrade() -> None:
    op.drop_column('approval_tasks', 'approval_required_count')
