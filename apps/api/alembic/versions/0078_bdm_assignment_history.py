"""bdm-025 (DEC-SCOPE-076) -- bdm_assignment_history.

docs/superpowers/specs/2026-10-06-bdm-025-deactivation-handover-design.md §4. Additive: one append-only table recording each
organization, appointment or task that changed owner (deactivation, later handover, bdm-002's single reassign). No existing row is
read or written. 0001 builds a fresh database from the current models, which already carry it, so creation is guarded (0071's
idiom). downgrade() refuses while rows exist: they are the only record of who owned what before.

Revision ID: 0078_bdm_assignment_history
Revises: 0077_bdm_tasks_followups
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0078_bdm_assignment_history"
down_revision = "0077_bdm_tasks_followups"
branch_labels = None
depends_on = None

TABLE = "bdm_assignment_history"


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    uuid = postgresql.UUID(as_uuid=True)
    users = lambda name: sa.Column(name, uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)  # noqa: E731
    op.create_table(
        TABLE,
        sa.Column("id", uuid, primary_key=True),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", uuid, nullable=False),
        users("from_user_id"),
        users("to_user_id"),
        users("actor_user_id"),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("entity_type IN ('organization', 'appointment', 'task')", name="ck_bdm_assignment_history_entity_type"),
        sa.CheckConstraint("reason IN ('bdm_deactivated', 'portfolio_handover', 'organization_reassigned')", name="ck_bdm_assignment_history_reason"),
    )
    op.create_index("ix_bdm_assignment_history_entity", TABLE, ["entity_type", "entity_id"])
    op.create_index("ix_bdm_assignment_history_from", TABLE, ["from_user_id"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0078_bdm_assignment_history: assignment history exists. Remove it deliberately first.")
    op.drop_table(TABLE)
