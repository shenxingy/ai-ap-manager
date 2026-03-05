"""create inspection_reports table

Revision ID: gap6_inspection_reports
Revises: gap9_multi_entity
Create Date: 2026-03-01

"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision = "gap6_inspection_reports"
down_revision = "gap9_multi_entity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inspection_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("gr_id", UUID(as_uuid=True), sa.ForeignKey("goods_receipts.id"), nullable=False),
        sa.Column("invoice_id", UUID(as_uuid=True), sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("inspector_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("result", sa.String(10), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("inspected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_inspection_reports_gr_id", "inspection_reports", ["gr_id"])
    op.create_index("ix_inspection_reports_invoice_id", "inspection_reports", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_inspection_reports_invoice_id", table_name="inspection_reports")
    op.drop_index("ix_inspection_reports_gr_id", table_name="inspection_reports")
    op.drop_table("inspection_reports")
