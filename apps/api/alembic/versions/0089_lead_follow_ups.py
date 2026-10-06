"""tel-011 -- `lead_follow_ups`: follow-ups on a lead.

Revision ID: 0089_lead_follow_ups
Revises: 0087_lead_import_batches

docs/superpowers/specs/2026-10-06-tel-011-follow-ups-design.md §2 (DEC-SCOPE-093). The open tel-009 branch claims 0088; whichever merges
second re-chains onto the other. 0001 builds a fresh database from the current models, which already carry the table, so the upgrade is
guarded (0074's idiom). CHECKS repeats models.LEAD_FOLLOW_UP_CHECKS (test_tel_011_migration asserts they stay identical).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0089_lead_follow_ups"
down_revision = "0087_lead_import_batches"
branch_labels = None
depends_on = None

TABLE = "lead_follow_ups"
REASONS = ("discuss_with_parents", "course_details", "fee_details", "waiting_salary", "waiting_documents", "comparing_courses", "next_month",
           "next_intake", "university_information", "counselor_call")
CHECKS = {
    "ck_lead_follow_ups_reason": f"reason IN ({', '.join(repr(r) for r in REASONS)})",
    "ck_lead_follow_ups_status": "status IN ('open', 'done', 'cancelled')",
    "ck_lead_follow_ups_state": (
        "(status = 'done') = (completed_at IS NOT NULL) AND (completed_at IS NULL) = (completed_by_user_id IS NULL) "
        "AND (status = 'cancelled') = (cancelled_at IS NOT NULL) AND (cancelled_at IS NULL) = (cancel_reason IS NULL)"
    ),
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
        sa.Column("due_at", when, nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("next_action", sa.String(200), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'open'")),
        sa.Column("created_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("completed_at", when, nullable=True),
        sa.Column("completed_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("cancelled_at", when, nullable=True),
        sa.Column("cancel_reason", sa.String(500), nullable=True),
        sa.Column("created_at", when, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", when, server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    op.create_index("ix_lead_follow_ups_lead", TABLE, ["lead_id", "status", "due_at"])
    op.create_index("ix_lead_follow_ups_open_due", TABLE, ["due_at"], postgresql_where=sa.text("status = 'open'"))


def downgrade() -> None:
    op.drop_index("ix_lead_follow_ups_open_due", table_name=TABLE)
    op.drop_index("ix_lead_follow_ups_lead", table_name=TABLE)
    op.drop_table(TABLE)
