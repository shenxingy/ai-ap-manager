"""add_vendor_messages_compliance_docs_normalized_amount

Revision ID: c4f57a15b205
Revises: 85d0d489d232
Create Date: 2026-02-27 17:41:10.131808

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c4f57a15b205'
down_revision: Union[str, None] = '85d0d489d232'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # invoices: add normalized_amount_usd for FX-normalized duplicate detection
    op.add_column('invoices', sa.Column('normalized_amount_usd', sa.Numeric(precision=18, scale=4), nullable=True))

    # vendor_compliance_docs: add file_key (MinIO object key) and uploaded_by FK
    op.add_column('vendor_compliance_docs', sa.Column('file_key', sa.String(length=500), nullable=True))
    op.add_column('vendor_compliance_docs', sa.Column('uploaded_by', sa.UUID(), nullable=True))
    op.create_foreign_key(None, 'vendor_compliance_docs', 'users', ['uploaded_by'], ['id'])

    # vendor_compliance_docs: change expiry_date from TIMESTAMP→DATE (USING cast)
    op.execute(
        "ALTER TABLE vendor_compliance_docs ALTER COLUMN expiry_date TYPE DATE "
        "USING expiry_date::DATE"
    )

    # vendor_messages: add attachments JSON column
    op.add_column('vendor_messages', sa.Column('attachments', sa.JSON(), server_default=sa.text("'[]'"), nullable=False))


def downgrade() -> None:
    op.drop_column('vendor_messages', 'attachments')
    op.drop_constraint(None, 'vendor_compliance_docs', type_='foreignkey')
    op.execute(
        "ALTER TABLE vendor_compliance_docs ALTER COLUMN expiry_date TYPE TIMESTAMP WITH TIME ZONE "
        "USING expiry_date::TIMESTAMP WITH TIME ZONE"
    )
    op.drop_column('vendor_compliance_docs', 'uploaded_by')
    op.drop_column('vendor_compliance_docs', 'file_key')
    op.drop_column('invoices', 'normalized_amount_usd')
