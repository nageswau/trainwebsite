"""tel-010 -- `lead_calls`: calls logged on a lead.

Revision ID: 0092_lead_calls
Revises: 0091_lead_appointments

docs/superpowers/specs/2026-10-07-tel-010-call-logging-design.md §3 (DEC-SCOPE-096). Re-chained after tel-016's
0091_lead_appointments (DEC-SCOPE-095), which merged first. 0001 builds a fresh database from
the current models, which already carry the table, so the upgrade is guarded (0074's idiom). CHECKS repeats models.LEAD_CALL_CHECKS
(test_tel_010_migration asserts they stay identical).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0092_lead_calls"
down_revision = "0091_lead_appointments"
branch_labels = None
depends_on = None

TABLE = "lead_calls"
TYPES = ("outgoing", "incoming")
OUTCOMES = ("interested", "need_information", "follow_up_required", "appointment_fixed", "not_interested", "wrong_number", "busy", "no_answer",
            "switched_off", "call_back_requested", "already_joined", "duplicate_lead", "not_eligible")
CHECKS = {
    "ck_lead_calls_call_type": f"call_type IN ({', '.join(repr(t) for t in TYPES)})",
    "ck_lead_calls_outcome": f"outcome IN ({', '.join(repr(o) for o in OUTCOMES)})",
    "ck_lead_calls_duration": "duration_seconds BETWEEN 0 AND 14400",
}


def upgrade() -> None:
    if not op.get_context().as_sql and sa.inspect(op.get_bind()).has_table(TABLE):
        return
    uuid = postgresql.UUID(as_uuid=True)
    when = sa.DateTime(timezone=True)
    op.create_table(
        TABLE,
        sa.Column("id", uuid, primary_key=True),
        sa.Column("lead_id", uuid, sa.ForeignKey("enquiries.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("caller_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("occurred_at", when, nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("call_type", sa.String(16), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_at", when, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", when, server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    op.create_index("ix_lead_calls_caller_occurred", TABLE, ["caller_user_id", "occurred_at"])
    op.create_index("ix_lead_calls_lead_occurred", TABLE, ["lead_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_lead_calls_lead_occurred", table_name=TABLE)
    op.drop_index("ix_lead_calls_caller_occurred", table_name=TABLE)
    op.drop_table(TABLE)
