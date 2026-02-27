"""audit_log_immutability

Revision ID: c1f9a2d3e4b5
Revises: b8479ee361ad
Create Date: 2026-02-27 10:10:00.000000

Enforce append-only semantics on audit_logs at the DB level:
- Revoke UPDATE and DELETE from PUBLIC
- Grant SELECT and INSERT only

This prevents any application code (or direct psql sessions using the
app role) from modifying or removing historical audit records.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c1f9a2d3e4b5'
down_revision: Union[str, None] = 'b8479ee361ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("REVOKE UPDATE, DELETE ON audit_logs FROM PUBLIC;")
    op.execute("GRANT SELECT, INSERT ON audit_logs TO PUBLIC;")


def downgrade() -> None:
    # Restore full DML access (only for disaster-recovery; normally never run)
    op.execute("GRANT UPDATE, DELETE ON audit_logs TO PUBLIC;")
