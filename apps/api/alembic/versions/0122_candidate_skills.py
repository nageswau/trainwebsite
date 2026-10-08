"""rec-011 -- candidate_skills.

Revision ID: 0122_candidate_skills
Revises: 0121_job_application_tracking

docs/superpowers/specs/2026-10-08-rec-011-candidate-skills-design.md §2 (DEC-SCOPE-137). A new table only; no existing row changes. 0001
builds a fresh database from the current models, which already carry this table, so it is created only when missing (0119's idiom). CHECKS
repeats app.models.CANDIDATE_SKILL_CHECKS (test_rec_011_migration). downgrade() refuses while any row exists: entered data is never dropped
silently.

Re-chained on 2026-10-09: drafted as `0120_candidate_skills` (DEC-SCOPE-135, API §12BC, RBAC §2.61) on `0119_recruiter_meetings`;
rec-026 (`0120_recruiter_messages`) and rec-017 (`0121_job_application_tracking`) merged first, so this is `0122` (DEC-SCOPE-137,
§12BE, §2.63). A database stamped at the draft is re-stamped with `alembic stamp --purge 0119_recruiter_meetings`, then `upgrade head`
(the table step is guarded).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0122_candidate_skills"
down_revision = "0121_job_application_tracking"
branch_labels = None
depends_on = None

TABLE = "candidate_skills"
UUID = postgresql.UUID(as_uuid=True)
LEVELS = ("beginner", "intermediate", "advanced", "expert")
SOURCES = ("resume", "interview_verified", "assessment_verified", "course_completed", "certification", "employer_verified")
STATUSES = ("claimed", "verified", "assessed")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


CHECKS = {  # must equal app.models.CANDIDATE_SKILL_CHECKS (test_rec_011_migration)
    "ck_candidate_skills_level": _in("level", LEVELS),
    "ck_candidate_skills_source": _in("source", SOURCES),
    "ck_candidate_skills_status": _in("status", STATUSES),
    "ck_candidate_skills_verified": "(status = 'claimed') = (verified_at IS NULL) AND (verified_at IS NULL) = (verified_by_user_id IS NULL)",
    "ck_candidate_skills_experience": "experience_months IS NULL OR experience_months BETWEEN 0 AND 600",
    "ck_candidate_skills_last_used": "last_used_year IS NULL OR last_used_year >= 1950",
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
        sa.Column("candidate_id", UUID, fk("candidates.id"), nullable=False),
        sa.Column("skill_id", UUID, fk("skills.id"), nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("experience_months", sa.Integer(), nullable=True),
        sa.Column("last_used_year", sa.SmallInteger(), nullable=True),
        sa.Column("source", sa.String(24), nullable=False, server_default=sa.text("'resume'")),
        sa.Column("status", sa.String(12), nullable=False, server_default=sa.text("'claimed'")),
        sa.Column("verified_by_user_id", UUID, fk("users.id"), nullable=True),
        sa.Column("verified_at", when, nullable=True),
        sa.Column("added_by_user_id", UUID, fk("users.id"), nullable=False),
        sa.Column("updated_by_user_id", UUID, fk("users.id"), nullable=True),
        sa.Column("created_at", when, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", when, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("candidate_id", "skill_id", name="uq_candidate_skills_skill"),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    op.create_index("ix_candidate_skills_skill_candidate", TABLE, ["skill_id", "status", "candidate_id"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0122_candidate_skills: candidate skills exist. Clear them deliberately first.")
    op.drop_table(TABLE)
