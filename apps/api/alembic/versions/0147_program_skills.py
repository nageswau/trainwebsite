"""rec-036 -- program_skills.

Revision ID: 0147_program_skills
Revises: 0146_interview_feedback

docs/superpowers/specs/2026-10-11-rec-036-it-training-integration-design.md §2 (DEC-SCOPE-176). A new table only; no existing row changes
and nothing is backfilled (no program has tags yet). 0001 builds a fresh database from the current models, which already carry this
table, so it is created only when missing (0122's idiom). downgrade() refuses while any row exists: entered data is never dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0147_program_skills"
down_revision = "0146_interview_feedback"
branch_labels = None
depends_on = None

TABLE = "program_skills"
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("program_id", UUID, sa.ForeignKey("programs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("skill_id", UUID, sa.ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("added_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_program_skills_skill", TABLE, ["skill_id"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0147_program_skills: program skill tags exist. Clear them deliberately first.")
    op.drop_index("ix_program_skills_skill", table_name=TABLE)
    op.drop_table(TABLE)
