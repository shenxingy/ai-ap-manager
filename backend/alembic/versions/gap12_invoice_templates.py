"""create invoice_templates table

Revision ID: gap12_invoice_templates
Revises: gap6_inspection_reports
Create Date: 2026-03-01

"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers
revision = "gap12_invoice_templates"
down_revision = "gap6_inspection_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoice_templates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "default_po_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("line_items", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"]),
        sa.ForeignKeyConstraint(["default_po_id"], ["purchase_orders.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )
    op.create_index("ix_invoice_templates_vendor_id", "invoice_templates", ["vendor_id"])


def downgrade() -> None:
    op.drop_index("ix_invoice_templates_vendor_id", table_name="invoice_templates")
    op.drop_table("invoice_templates")
