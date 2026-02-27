"""add_exception_routing_rules

Revision ID: 9043f7a6e972
Revises: b60318e06768
Create Date: 2026-02-27 08:27:52.318964

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9043f7a6e972'
down_revision: Union[str, None] = 'b60318e06768'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'exception_routing_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('exception_code', sa.String(100), nullable=False),
        sa.Column('target_role', sa.String(50), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_exception_routing_rules_exception_code', 'exception_routing_rules', ['exception_code'])


def downgrade() -> None:
    op.drop_index('ix_exception_routing_rules_exception_code', table_name='exception_routing_rules')
    op.drop_table('exception_routing_rules')
