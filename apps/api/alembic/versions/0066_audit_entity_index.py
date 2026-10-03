"""AGN-015 -- audit_logs (entity_type, entity_id, created_at) for per-entity history reads.

Revision ID: 0066_audit_entity_index
Revises: 0065_agent_notifications

docs/superpowers/specs/2026-10-03-agn-015-student-journey-design.md §6 (DEC-SCOPE-060). One index; no row is read or written. 0001
builds a fresh database from the current models, which already carry it, so the add is guarded (0057's idiom). downgrade() drops
exactly what upgrade() added.
"""

import sqlalchemy as sa

from alembic import op

revision = "0066_audit_entity_index"
down_revision = "0065_agent_notifications"
branch_labels = None
depends_on = None

NAME = "ix_audit_logs_entity"


def upgrade() -> None:
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())
    if inspector is None or NAME not in {i["name"] for i in inspector.get_indexes("audit_logs")}:
        op.create_index(NAME, "audit_logs", ["entity_type", "entity_id", "created_at"])


def downgrade() -> None:
    op.drop_index(NAME, table_name="audit_logs")
