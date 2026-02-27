"""add_approval_matrix_and_delegations

Revision ID: 38c1697a3bb1
Revises: c1f9a2d3e4b5
Create Date: 2026-02-27 16:45:04.570067

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '38c1697a3bb1'
down_revision: Union[str, None] = 'c1f9a2d3e4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'approval_matrix_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('amount_min', sa.Numeric(18, 2), nullable=True),
        sa.Column('amount_max', sa.Numeric(18, 2), nullable=True),
        sa.Column('department', sa.String(100), nullable=True),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('approver_role', sa.String(50), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'user_delegations',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('delegator_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('delegate_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('valid_from', sa.Date(), nullable=False),
        sa.Column('valid_until', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['delegate_id'], ['users.id']),
        sa.ForeignKeyConstraint(['delegator_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_user_delegations_delegator_id', 'user_delegations', ['delegator_id'])
    op.create_index('ix_user_delegations_delegate_id', 'user_delegations', ['delegate_id'])


def downgrade() -> None:
    op.drop_index('ix_user_delegations_delegate_id', table_name='user_delegations')
    op.drop_index('ix_user_delegations_delegator_id', table_name='user_delegations')
    op.drop_table('user_delegations')
    op.drop_table('approval_matrix_rules')
