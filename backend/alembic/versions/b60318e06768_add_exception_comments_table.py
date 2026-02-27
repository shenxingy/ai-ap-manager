"""add exception_comments table

Revision ID: b60318e06768
Revises: 94b5a776a020
Create Date: 2026-02-27 08:13:05.954868

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b60318e06768'
down_revision: Union[str, None] = '94b5a776a020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'exception_comments',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('exception_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['users.id']),
        sa.ForeignKeyConstraint(['exception_id'], ['exception_records.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_exception_comments_exception_id', 'exception_comments', ['exception_id'])


def downgrade() -> None:
    op.drop_index('ix_exception_comments_exception_id', table_name='exception_comments')
    op.drop_table('exception_comments')
