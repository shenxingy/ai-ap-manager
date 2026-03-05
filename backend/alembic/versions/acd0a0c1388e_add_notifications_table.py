"""add_notifications_table

Revision ID: acd0a0c1388e
Revises: 0d7b9b48c634
Create Date: 2026-03-01 20:42:52.558178

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'acd0a0c1388e'
down_revision: str | None = '0d7b9b48c634'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create notifications table
    op.create_table(
        'notifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('invoice_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('invoices.id'), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    op.create_index('ix_notifications_invoice_id', 'notifications', ['invoice_id'])


def downgrade() -> None:
    op.drop_index('ix_notifications_invoice_id', table_name='notifications')
    op.drop_index('ix_notifications_user_id', table_name='notifications')
    op.drop_table('notifications')
