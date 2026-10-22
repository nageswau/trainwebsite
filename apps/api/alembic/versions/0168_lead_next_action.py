"""ccrm-003 -- a lead's next action: enquiries.next_action, enquiries.next_action_due.

Revision ID: 0168_lead_next_action
Revises: 0167_lead_notes

docs/superpowers/specs/2026-10-22-ccrm-003-counselor-lead-actions-design.md (DEC-SCOPE-243). Additive: both columns are nullable, no
existing row changes (counselor leads are not back-filled, A2). 0001 builds a fresh database from the current models, which already carry
the columns, so each step is guarded (0166's idiom). MAX repeats app.models.LEAD_NEXT_ACTION_MAX (test_ccrm_003_migration).
"""

import sqlalchemy as sa

from alembic import op

revision = "0168_lead_next_action"
down_revision = "0167_lead_notes"
branch_labels = None
depends_on = None

TABLE = "enquiries"
MAX = 200  # app.models.LEAD_NEXT_ACTION_MAX
CHECK = "ck_enquiries_next_action_len"


def upgrade() -> None:
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything
    columns = set() if inspector is None else {c["name"] for c in inspector.get_columns(TABLE)}
    if "next_action" not in columns:
        op.add_column(TABLE, sa.Column("next_action", sa.String(MAX), nullable=True))
    if "next_action_due" not in columns:
        op.add_column(TABLE, sa.Column("next_action_due", sa.Date(), nullable=True))
    if inspector is None or CHECK not in {c["name"] for c in inspector.get_check_constraints(TABLE)}:
        op.create_check_constraint(CHECK, TABLE, f"next_action IS NULL OR length(next_action) BETWEEN 1 AND {MAX}")


def downgrade() -> None:
    op.drop_constraint(CHECK, TABLE, type_="check")
    op.drop_column(TABLE, "next_action_due")
    op.drop_column(TABLE, "next_action")
