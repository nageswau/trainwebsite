"""nehn-026 -- keyword auto-scoring: `assessment_questions.keywords`, `assessment_answers.auto_score / score_source`.

Revision ID: 0218_assessment_keyword_scoring
Revises: 0217_course_agent_commission

docs/superpowers/specs/2026-10-29-nehn-026-keyword-auto-scoring-design.md (DEC-SCOPE-333). Additive: keywords default to `[]`, the answer
columns are nullable (NULL = not scored yet), no backfill. 0001 builds a fresh database from the current models, so every step is guarded.
downgrade() refuses while any question has keywords, so a rollback never silently drops an answer key.
"""

import sqlalchemy as sa

from alembic import op

revision = "0218_assessment_keyword_scoring"
down_revision = "0217_course_agent_commission"
branch_labels = None
depends_on = None

COLUMNS = (
    ("assessment_questions", sa.Column("keywords", sa.JSON(), nullable=False, server_default="[]")),
    ("assessment_answers", sa.Column("auto_score", sa.Numeric(10, 2), nullable=True)),
    ("assessment_answers", sa.Column("score_source", sa.String(10), nullable=True)),
)


def upgrade() -> None:
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())
    for table, column in COLUMNS:
        if inspector is None or column.name not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(table, column)


def downgrade() -> None:
    if not op.get_context().as_sql:
        found = op.get_bind().execute(sa.text("SELECT 1 FROM assessment_questions WHERE CAST(keywords AS TEXT) <> '[]' LIMIT 1")).first()
        if found:
            raise RuntimeError("Cannot downgrade 0218_assessment_keyword_scoring: questions have keywords. Remove them deliberately first.")
    for table, column in reversed(COLUMNS):
        op.drop_column(table, column.name)
