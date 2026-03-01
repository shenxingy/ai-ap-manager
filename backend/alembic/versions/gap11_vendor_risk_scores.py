"""create vendor_risk_scores table

Revision ID: gap11_vendor_risk_scores
Revises: gap1_imap_email_fields
Create Date: 2026-03-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'gap11_vendor_risk_scores'
down_revision = 'gap1_imap_email_fields'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'vendor_risk_scores',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('vendor_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('vendors.id'), nullable=False),
        sa.Column('ocr_error_rate', sa.Float, nullable=True),
        sa.Column('exception_rate', sa.Float, nullable=True),
        sa.Column('avg_extraction_confidence', sa.Float, nullable=True),
        sa.Column('score', sa.Float, nullable=True),
        sa.Column('risk_level', sa.String(10), nullable=True),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('vendor_id', name='uq_vendor_risk_scores_vendor_id'),
    )
    op.create_index('ix_vendor_risk_scores_vendor_id', 'vendor_risk_scores', ['vendor_id'])


def downgrade():
    op.drop_index('ix_vendor_risk_scores_vendor_id', table_name='vendor_risk_scores')
    op.drop_table('vendor_risk_scores')
