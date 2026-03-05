"""add email fields to invoices

Revision ID: gap1_imap_email_fields
Revises: f4a5b6c7d8e9
Create Date: 2026-03-01 00:00:00.000000
"""
import sqlalchemy as sa

from alembic import op

revision = 'gap1_imap_email_fields'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('invoices', sa.Column('email_from', sa.String(255), nullable=True))
    op.add_column('invoices', sa.Column('email_subject', sa.String(500), nullable=True))
    op.add_column('invoices', sa.Column('email_received_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('invoices', 'email_received_at')
    op.drop_column('invoices', 'email_subject')
    op.drop_column('invoices', 'email_from')
