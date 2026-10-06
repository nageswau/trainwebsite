"""bdm-025 (DEC-SCOPE-079) -- bdm_assignment_history.

docs/superpowers/specs/2026-10-06-bdm-025-deactivation-handover-design.md §4. Additive: one append-only table recording each
organization, appointment or task that changed owner (deactivation, later handover, bdm-002's single reassign). No existing row is
read or written. 0001 builds a fresh database from the current models, which already carry it, so creation is guarded (0071's
idiom). downgrade() refuses while rows exist: they are the only record of who owned what before.

Re-chained 2026-10-06 on merging `main` @ `230a043f`: drafted as `0078_bdm_assignment_history` after `0077_bdm_tasks_followups`
(DEC-SCOPE-076); tel-003 took `0078_enquiry_lead_record` (DEC-SCOPE-077) and bdm-005 `0079_bdm_mous` (DEC-SCOPE-078), and tel-017
took DEC-SCOPE-076, so this is `0080_bdm_assignment_history` after `0079_bdm_mous` and the decision is DEC-SCOPE-079. A database
stamped at `0078_bdm_assignment_history` is re-stamped with `alembic stamp --purge 0077_bdm_tasks_followups` then `upgrade head`.

Revision ID: 0080_bdm_assignment_history
Revises: 0079_bdm_mous
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0080_bdm_assignment_history"
down_revision = "0079_bdm_mous"
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
        raise RuntimeError("Cannot downgrade 0080_bdm_assignment_history: assignment history exists. Remove it deliberately first.")
    op.drop_table(TABLE)
