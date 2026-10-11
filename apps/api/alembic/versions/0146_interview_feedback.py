"""rec-021 -- interview_feedback.

Revision ID: 0146_interview_feedback
Revises: 0145_university_onboarding

docs/superpowers/specs/2026-10-11-rec-021-interview-feedback-design.md §1 (DEC-SCOPE-175). A new table only; no existing row changes.
0001 builds a fresh database from the current models, which already carry this table, so it is created only when missing (0122's idiom).
CHECKS repeats app.models.FEEDBACK_CHECKS (test_rec_021_migration). downgrade() refuses while any row exists: entered data is never
dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0146_interview_feedback"
down_revision = "0145_university_onboarding"
branch_labels = None
depends_on = None

TABLE = "interview_feedback"
UUID = postgresql.UUID(as_uuid=True)
ROUNDS = ("hr_round", "technical_round", "manager_round", "final_round", "client_round")
DECISIONS = ("selected", "rejected", "on_hold")

CHECKS = {  # must equal app.models.FEEDBACK_CHECKS (test_rec_021_migration)
    "ck_interview_feedback_overall": "overall_rating BETWEEN 1 AND 5",
    "ck_interview_feedback_technical": "technical_rating IS NULL OR technical_rating BETWEEN 1 AND 5",
    "ck_interview_feedback_communication": "communication_rating IS NULL OR communication_rating BETWEEN 1 AND 5",
    "ck_interview_feedback_next_round": "next_round IS NULL OR next_round IN (" + ", ".join(f"'{s}'" for s in ROUNDS) + ")",
    "ck_interview_feedback_decision": "final_decision IS NULL OR final_decision IN (" + ", ".join(f"'{s}'" for s in DECISIONS) + ")",
    "ck_interview_feedback_rejected_no_next": "final_decision IS DISTINCT FROM 'rejected' OR next_round IS NULL",
}


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    when = sa.DateTime(timezone=True)

    def text(name: str) -> sa.Column:
        return sa.Column(name, sa.String(2000), nullable=True)

    op.create_table(
        TABLE,
        sa.Column("interview_id", UUID, sa.ForeignKey("interviews.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("technical_rating", sa.SmallInteger(), nullable=True),
        sa.Column("communication_rating", sa.SmallInteger(), nullable=True),
        sa.Column("overall_rating", sa.SmallInteger(), nullable=False),
        text("strengths"),
        text("weaknesses"),
        text("recruiter_comments"),
        text("company_feedback"),
        sa.Column("next_round", sa.String(20), nullable=True),
        sa.Column("final_decision", sa.String(16), nullable=True),
        sa.Column("recorded_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", when, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", when, server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0146_interview_feedback: interview feedback exists. Clear it deliberately first.")
    op.drop_table(TABLE)
