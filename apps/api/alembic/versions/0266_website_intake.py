"""hrc-023 -- website registration -> candidate create/match: UTM, the application's candidate link and consent, nullable creators.

Revision ID: 0266_website_intake
Revises: 0265_skill_taxonomy

docs/superpowers/specs/2026-11-04-hrc-023-website-registration-intake-design.md (DEC-SCOPE-389). Adds `candidates.utm`,
`career_applications.candidate_id/utm/consent_version/consented_at`, and lets `candidates.created_by_user_id` and
`candidate_consents.user_id` be empty (a public form has no user). 0001 builds a fresh database from the current models, which already
carry the columns, so each step runs only when missing (0251's idiom). W8 / Q-25: existing career applications are LINKED to an
existing unmerged candidate with the same email; no candidate is created from history. The downgrade drops the new columns and
restores NOT NULL only where no empty value exists.
"""

import sqlalchemy as sa

from alembic import op

revision = "0266_website_intake"
down_revision = "0265_skill_taxonomy"
branch_labels = None
depends_on = None

APPLICATION_COLUMNS = ("candidate_id", "utm", "consent_version", "consented_at")
NULLABLE = (("candidates", "created_by_user_id"), ("candidate_consents", "user_id"))


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "utm" not in _columns("candidates"):
        op.add_column("candidates", sa.Column("utm", sa.JSON(), nullable=True))
    have = _columns("career_applications")
    if "candidate_id" not in have:
        op.add_column("career_applications", sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("candidates.id", ondelete="RESTRICT",
                                                                                                name="fk_career_applications_candidate_id"), nullable=True))  # fmt: skip
        op.create_index("ix_career_applications_candidate_id", "career_applications", ["candidate_id"])
    if "utm" not in have:
        op.add_column("career_applications", sa.Column("utm", sa.JSON(), nullable=True))
    if "consent_version" not in have:
        op.add_column("career_applications", sa.Column("consent_version", sa.String(20), nullable=True))
    if "consented_at" not in have:
        op.add_column("career_applications", sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True))
    for table, column in NULLABLE:
        op.alter_column(table, column, existing_type=sa.Uuid(), nullable=True)
    # W8: link history by exact (lower-cased) email to an unmerged candidate; the email is unique among candidates (uq_candidates_email)
    op.execute(
        "UPDATE career_applications AS a SET candidate_id = c.id FROM candidates AS c "
        "WHERE a.candidate_id IS NULL AND c.email IS NOT NULL AND lower(c.email) = lower(a.email) AND c.merged_into_id IS NULL"
    )


def downgrade() -> None:
    have = _columns("career_applications")
    if "candidate_id" in have:
        op.drop_index("ix_career_applications_candidate_id", table_name="career_applications")
    for column in APPLICATION_COLUMNS:
        if column in have:
            op.drop_column("career_applications", column)
    if "utm" in _columns("candidates"):
        op.drop_column("candidates", "utm")
    bind = op.get_bind()
    for table, column in NULLABLE:  # only when nothing is empty: a website-created row would otherwise block the downgrade
        if not bind.execute(sa.text(f"SELECT 1 FROM {table} WHERE {column} IS NULL LIMIT 1")).first():
            op.alter_column(table, column, existing_type=sa.Uuid(), nullable=False)
