"""rec-008 -- job_descriptions + jd_number_seq: a requirement's versioned JD.

Revision ID: 0117_job_descriptions
Revises: 0116_recruiter_follow_ups

docs/superpowers/specs/2026-10-08-rec-008-jd-management-design.md §2 (DEC-SCOPE-132). A new table and sequence only; no existing row
changes. 0001 builds a fresh database from the current models, which already carry both, so they are created only when missing (0107's
idiom). CHECKS repeats app.models.JOB_DESCRIPTION_CHECKS (test_rec_008_migration). downgrade() refuses while any JD exists: entered data
is never dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0117_job_descriptions"
down_revision = "0116_recruiter_follow_ups"
branch_labels = None
depends_on = None

TABLE = "job_descriptions"
SEQ = "jd_number_seq"
UUID = postgresql.UUID(as_uuid=True)
CHECKS = {  # must equal app.models.JOB_DESCRIPTION_CHECKS (test_rec_008_migration)
    "ck_job_descriptions_version": "version >= 1",
    "ck_job_descriptions_openings": "openings IS NULL OR openings BETWEEN 1 AND 10000",
    "ck_job_descriptions_file": "(storage_key IS NULL) = (content_type IS NULL) AND (storage_key IS NULL) = (size_bytes IS NULL)",
}


def upgrade() -> None:
    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQ} MAXVALUE 999999")
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return

    def fk(target: str):
        return sa.ForeignKey(target, ondelete="RESTRICT")

    op.create_table(
        TABLE,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("job_id", UUID, fk("jobs.id"), nullable=False),
        sa.Column("jd_number", sa.String(12), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("role", sa.String(180), nullable=False),
        sa.Column("experience", sa.String(120), nullable=True),
        sa.Column("qualification", sa.String(300), nullable=True),
        sa.Column("skills", sa.String(1000), nullable=True),
        sa.Column("salary", sa.String(120), nullable=True),
        sa.Column("location", sa.String(120), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("responsibilities", sa.Text(), nullable=True),
        sa.Column("requirements", sa.Text(), nullable=True),
        sa.Column("openings", sa.Integer(), nullable=True),
        sa.Column("contact_id", UUID, fk("company_contacts.id"), nullable=True),
        sa.Column("closing_date", sa.Date(), nullable=True),
        sa.Column("storage_key", sa.String(300), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("content_type", sa.String(120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", UUID, fk("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("job_id", "version", name="uq_job_descriptions_version"),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    op.create_index("uq_job_descriptions_current", TABLE, ["job_id"], unique=True, postgresql_where=sa.text("is_current"))
    op.create_index("ix_job_descriptions_number", TABLE, ["jd_number"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0117_job_descriptions: job descriptions exist. Remove them deliberately first.")
    op.drop_table(TABLE)
    op.execute(f"DROP SEQUENCE IF EXISTS {SEQ}")
