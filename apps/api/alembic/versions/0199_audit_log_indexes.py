"""nehn-042 -- audit_logs (created_at) for the paged, newest-first audit log search.

Revision ID: 0199_audit_log_indexes
Revises: 0198_live_session_cancel_reason

docs/superpowers/specs/2026-10-26-nehn-042-audit-log-search-design.md (DEC-SCOPE-289 A6). `ix_audit_logs_created_at` is new; the actor
index `ix_audit_logs_user_id` comes from the model (`index=True`) and is added only if a database lacks it. 0001 builds a fresh database
from the current models, which already carry both, so each add is guarded (0067's idiom). No row is read or written. The downgrade drops
only the created_at index (the user_id index predates this migration).
"""

import sqlalchemy as sa

from alembic import op

revision = "0199_audit_log_indexes"
down_revision = "0198_live_session_cancel_reason"
branch_labels = None
depends_on = None

INDEXES = {"ix_audit_logs_created_at": ["created_at"], "ix_audit_logs_user_id": ["user_id"]}


def upgrade() -> None:
    existing = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("audit_logs")}
    for name, columns in INDEXES.items():
        if name not in existing:
            op.create_index(name, "audit_logs", columns)


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
