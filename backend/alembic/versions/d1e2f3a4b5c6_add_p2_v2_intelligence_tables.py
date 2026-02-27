"""add p2 v2 intelligence tables: ai_feedback, rule_recommendations, analytics_reports, sla_alerts

Revision ID: d1e2f3a4b5c6
Revises: a62cfc478867
Create Date: 2026-02-27 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'a62cfc478867'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── ai_feedback ───
    op.create_table(
        'ai_feedback',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('feedback_type', sa.String(50), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('entity_id', UUID(as_uuid=True), nullable=False),
        sa.Column('field_name', sa.String(100), nullable=True),
        sa.Column('old_value', sa.Text, nullable=True),
        sa.Column('new_value', sa.Text, nullable=True),
        sa.Column('actor_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('actor_email', sa.String(255), nullable=True),
        sa.Column('invoice_id', UUID(as_uuid=True), sa.ForeignKey('invoices.id'), nullable=True),
        sa.Column('vendor_id', UUID(as_uuid=True), sa.ForeignKey('vendors.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_ai_feedback_feedback_type', 'ai_feedback', ['feedback_type'])
    op.create_index('ix_ai_feedback_entity_id', 'ai_feedback', ['entity_id'])
    op.create_index('ix_ai_feedback_invoice_id', 'ai_feedback', ['invoice_id'])
    op.create_index('ix_ai_feedback_vendor_id', 'ai_feedback', ['vendor_id'])

    # ─── rule_recommendations ───
    op.create_table(
        'rule_recommendations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('rule_type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('evidence_summary', sa.Text, nullable=True),
        sa.Column('suggested_config', sa.Text, nullable=True),
        sa.Column('confidence_score', sa.Float, nullable=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='pending'),
        sa.Column('reviewed_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_notes', sa.Text, nullable=True),
        sa.Column('analysis_period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('analysis_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('correction_count', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_rule_recommendations_status', 'rule_recommendations', ['status'])

    # ─── analytics_reports ───
    op.create_table(
        'analytics_reports',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('report_type', sa.String(50), nullable=False, server_default='root_cause'),
        sa.Column('status', sa.String(30), nullable=False, server_default='pending'),
        sa.Column('narrative', sa.Text, nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('requested_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('requester_email', sa.String(255), nullable=True),
        sa.Column('prompt_tokens', sa.Integer, nullable=True),
        sa.Column('completion_tokens', sa.Integer, nullable=True),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_analytics_reports_status', 'analytics_reports', ['status'])
    op.create_index('ix_analytics_reports_requester_email', 'analytics_reports', ['requester_email'])

    # ─── sla_alerts ───
    op.create_table(
        'sla_alerts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('invoice_id', UUID(as_uuid=True), sa.ForeignKey('invoices.id'), nullable=False),
        sa.Column('alert_type', sa.String(30), nullable=False),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('days_until_due', sa.Integer, nullable=True),
        sa.Column('invoice_status', sa.String(50), nullable=True),
        sa.Column('alert_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_sla_alerts_invoice_id', 'sla_alerts', ['invoice_id'])
    op.create_index('ix_sla_alerts_alert_type', 'sla_alerts', ['alert_type'])
    op.create_index('ix_sla_alerts_alert_date', 'sla_alerts', ['alert_date'])


def downgrade() -> None:
    op.drop_table('sla_alerts')
    op.drop_table('analytics_reports')
    op.drop_table('rule_recommendations')
    op.drop_table('ai_feedback')
