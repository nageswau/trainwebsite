"""hrc-029 -- the interview panel (`interview_interviewers`) and each panel member's own feedback (`interview_panel_feedback`).

Revision ID: 0280_interview_panel
Revises: 0278_commercial_grants

docs/superpowers/specs/2026-11-05-hrc-029-interviewer-access-feedback-design.md (DEC-SCOPE-405 V1, V7). Two new tables; 0001 builds a
fresh database from the current models, which already carry them, so each is created only when missing (0277's idiom). The checks are
frozen copies of the models at this revision (test_hrc_029_migration). No backfill: no interview has a panel yet. The downgrade drops both
tables (panel feedback first); interviews and rec-021 feedback are untouched.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0280_interview_panel"
down_revision = "0278_commercial_grants"
branch_labels = None
depends_on = None

ASSIGNMENT_CHECKS = {"ck_interview_interviewers_kind": "kind IN ('internal', 'employer')"}
FEEDBACK_CHECKS = {
    "ck_interview_panel_feedback_attendance": "attendance IN ('attended', 'no_show')",
    "ck_interview_panel_feedback_score": "score IS NULL OR score BETWEEN 1 AND 5",
    "ck_interview_panel_feedback_recommendation": "recommendation IS NULL OR recommendation IN ('strong_yes', 'yes', 'no', 'strong_no')",
    "ck_interview_panel_feedback_attended": "attendance = 'no_show' OR (score IS NOT NULL AND recommendation IS NOT NULL)",
}
UUID = postgresql.UUID(as_uuid=True)


def _fk(table: str):
    return sa.ForeignKey(f"{table}.id", ondelete="RESTRICT")


def upgrade() -> None:
    offline = op.get_context().as_sql
    tables = set() if offline else set(sa.inspect(op.get_bind()).get_table_names())
    if "interview_interviewers" not in tables:
        op.create_table(
            "interview_interviewers",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("interview_id", UUID, _fk("interviews"), nullable=False),
            sa.Column("user_id", UUID, _fk("users"), nullable=False),
            sa.Column("kind", sa.String(10), nullable=False),
            sa.Column("is_lead", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("resume_id", UUID, _fk("candidate_resumes"), nullable=True),
            sa.Column("assigned_by_user_id", UUID, _fk("users"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("interview_id", "user_id", name="uq_interview_interviewers_user"),
            *(sa.CheckConstraint(sql, name=name) for name, sql in ASSIGNMENT_CHECKS.items()),
        )
        op.create_index("uq_interview_interviewers_lead", "interview_interviewers", ["interview_id"], unique=True, postgresql_where=sa.text("is_lead"))
        op.create_index("ix_interview_interviewers_user", "interview_interviewers", ["user_id"])
    if "interview_panel_feedback" not in tables:
        op.create_table(
            "interview_panel_feedback",
            sa.Column("interview_id", UUID, _fk("interviews"), primary_key=True),
            sa.Column("interviewer_user_id", UUID, _fk("users"), primary_key=True),
            sa.Column("attendance", sa.String(10), nullable=False),
            sa.Column("score", sa.SmallInteger(), nullable=True),
            sa.Column("recommendation", sa.String(10), nullable=True),
            sa.Column("notes", sa.String(2000), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in FEEDBACK_CHECKS.items()),
        )


def downgrade() -> None:
    op.drop_table("interview_panel_feedback")
    op.drop_table("interview_interviewers")
