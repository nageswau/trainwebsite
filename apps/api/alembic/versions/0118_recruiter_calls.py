"""rec-025 -- recruiter_calls: calls logged on a company contact or a candidate.

Revision ID: 0118_recruiter_calls
Revises: 0117_job_descriptions

docs/superpowers/specs/2026-10-08-rec-025-recruiter-calls-design.md §2 (DEC-SCOPE-133). A new table only; no existing row changes.
0001 builds a fresh database from the current models, which already carry this table, so it is created only when missing (0110's idiom).
CHECKS repeats app.models.RECRUITER_CALL_CHECKS (test_rec_025_migration). downgrade() refuses while any call exists: entered data is
never dropped silently.

Re-chained 2026-10-08 on merging `main` @ `e055ff91`: drafted as `0117_recruiter_calls` on `0116_recruiter_follow_ups`, but rec-008
(`0117_job_descriptions`, DEC-SCOPE-132, API §12AZ, RBAC §2.58) merged first, so this is `0118` (DEC-SCOPE-133, API §12BA, RBAC §2.59).
A database stamped at the draft is re-stamped with `alembic stamp --purge 0116_recruiter_follow_ups`, then `upgrade head` (both table
steps are guarded).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0118_recruiter_calls"
down_revision = "0117_job_descriptions"
branch_labels = None
depends_on = None

TABLE = "recruiter_calls"
UUID = postgresql.UUID(as_uuid=True)
OUTCOMES = ("connected", "call_back_requested", "busy", "no_answer", "switched_off", "wrong_number")
DIRECTIONS = ("outgoing", "incoming")
CHECKS = {  # must equal app.models.RECRUITER_CALL_CHECKS (test_rec_025_migration)
    "ck_recruiter_calls_outcome": f"outcome IN ({', '.join(repr(o) for o in OUTCOMES)})",
    "ck_recruiter_calls_direction": f"direction IN ({', '.join(repr(d) for d in DIRECTIONS)})",
    "ck_recruiter_calls_duration": "duration_seconds IS NULL OR duration_seconds BETWEEN 0 AND 14400",
    "ck_recruiter_calls_party": "(contact_id IS NULL) = (company_id IS NULL) AND (contact_id IS NULL) <> (candidate_id IS NULL)",
}
INDEXES = {
    "ix_recruiter_calls_company_occurred": ["company_id", "occurred_at"],
    "ix_recruiter_calls_contact_occurred": ["contact_id", "occurred_at"],
    "ix_recruiter_calls_candidate_occurred": ["candidate_id", "occurred_at"],
    "ix_recruiter_calls_caller_occurred": ["caller_user_id", "occurred_at"],
}


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    when = sa.DateTime(timezone=True)

    def fk(target: str):
        return sa.ForeignKey(target, ondelete="RESTRICT")

    op.create_table(
        TABLE,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, fk("companies.id"), nullable=True),
        sa.Column("contact_id", UUID, fk("company_contacts.id"), nullable=True),
        sa.Column("candidate_id", UUID, fk("candidates.id"), nullable=True),
        sa.Column("caller_user_id", UUID, fk("users.id"), nullable=False),
        sa.Column("occurred_at", when, nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", when, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", when, server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    for name, columns in INDEXES.items():
        op.create_index(name, TABLE, columns)


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0118_recruiter_calls: recruiter calls exist. Clear them deliberately first.")
    op.drop_table(TABLE)
