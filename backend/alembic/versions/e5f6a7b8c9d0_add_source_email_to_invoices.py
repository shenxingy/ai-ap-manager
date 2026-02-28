"""add source, source_email, due_date to invoices; create override_logs

Revision ID: e5f6a7b8c9d0
Revises: 2ac83ef6dfcc
Create Date: 2026-02-27 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = '2ac83ef6dfcc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── invoices: source tracking columns ───
    op.add_column('invoices', sa.Column('source', sa.String(50), nullable=False, server_default='upload'))
    op.add_column('invoices', sa.Column('source_email', sa.String(255), nullable=True))
    op.add_column('invoices', sa.Column('due_date', sa.DateTime(timezone=True), nullable=True))

    # ─── override_logs ───
    op.create_table(
        'override_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('invoice_id', UUID(as_uuid=True), sa.ForeignKey('invoices.id'), nullable=False, index=True),
        sa.Column('rule_id', UUID(as_uuid=True), sa.ForeignKey('rules.id'), nullable=True, index=True),
        sa.Column('field_name', sa.String(100), nullable=False, index=True),
        sa.Column('old_value', sa.JSON, nullable=True),
        sa.Column('new_value', sa.JSON, nullable=True),
        sa.Column('overridden_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('reason', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('override_logs')
    op.drop_column('invoices', 'due_date')
    op.drop_column('invoices', 'source_email')
    op.drop_column('invoices', 'source')
