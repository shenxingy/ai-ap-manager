"""add performance indexes

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-02-28
"""
from alembic import op

revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index('ix_invoices_status', 'invoices', ['status'])
    op.create_index('ix_invoices_created_at', 'invoices', ['created_at'])
    op.create_index('ix_invoices_due_date', 'invoices', ['due_date'])
    op.create_index('ix_invoices_status_created_at', 'invoices', ['status', 'created_at'])
    op.create_index('ix_approval_tasks_due_at', 'approval_tasks', ['due_at'])
    op.create_index('ix_approval_tasks_status_due_at', 'approval_tasks', ['status', 'due_at'])
    op.create_index('ix_exceptions_status_severity', 'exception_records', ['status', 'severity'])
    op.create_index('ix_audit_logs_entity_id_created_at', 'audit_logs', ['entity_id', 'created_at'])
    op.create_index('ix_vendor_messages_invoice_direction', 'vendor_messages', ['invoice_id', 'direction'])


def downgrade() -> None:
    op.drop_index('ix_vendor_messages_invoice_direction', table_name='vendor_messages')
    op.drop_index('ix_audit_logs_entity_id_created_at', table_name='audit_logs')
    op.drop_index('ix_exceptions_status_severity', table_name='exception_records')
    op.drop_index('ix_approval_tasks_status_due_at', table_name='approval_tasks')
    op.drop_index('ix_approval_tasks_due_at', table_name='approval_tasks')
    op.drop_index('ix_invoices_status_created_at', table_name='invoices')
    op.drop_index('ix_invoices_due_date', table_name='invoices')
    op.drop_index('ix_invoices_created_at', table_name='invoices')
    op.drop_index('ix_invoices_status', table_name='invoices')
