"""add_source_ai_extracted_shadow_mode_to_rule_versions

Revision ID: 2ac83ef6dfcc
Revises: d1e2f3a4b5c6
Create Date: 2026-02-27 19:46:22.812281

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2ac83ef6dfcc'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('rule_versions', sa.Column('source', sa.String(length=100), nullable=True))
    op.add_column('rule_versions', sa.Column('ai_extracted', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('rule_versions', sa.Column('is_shadow_mode', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('rule_versions', 'is_shadow_mode')
    op.drop_column('rule_versions', 'ai_extracted')
    op.drop_column('rule_versions', 'source')
