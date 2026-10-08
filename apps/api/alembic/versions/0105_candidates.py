"""rec-009 -- the candidate master: candidates + candidate_resumes + candidate_code_seq.

Revision ID: 0105_candidates
Revises: 0103_partnership_profiles

docs/superpowers/specs/2026-10-08-rec-009-candidate-master-design.md §3 (DEC-SCOPE-120, provisional numbering: re-chained to the real head
at merge). Adds two tables and a sequence; no existing row is read or written. 0001 builds a fresh database from the current models, which
already carry these tables, so creation is guarded (0076's idiom). downgrade() refuses while any candidate exists.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0105_candidates"
down_revision = "0103_partnership_profiles"  # re-chained after upc-001 (merged to main first)
branch_labels = None
depends_on = None

SEQ = "candidate_code_seq"
STATUSES = ("available", "interviewing", "placed", "not_looking", "do_not_contact")  # Q-08
# Identical to app.models.CANDIDATE_CHECKS (asserted by test_rec_009_migration); repeated so the migration never imports the models.
CHECKS = {
    "ck_candidates_contact": "mobile IS NOT NULL OR email IS NOT NULL",
    "ck_candidates_status": "status IN (" + ", ".join(f"'{s}'" for s in STATUSES) + ")",
    "ck_candidates_passing_year": "passing_year IS NULL OR passing_year BETWEEN 1950 AND 2100",
    "ck_candidates_experience": "experience_months IS NULL OR experience_months BETWEEN 0 AND 600",
    "ck_candidates_notice": "notice_days IS NULL OR notice_days BETWEEN 0 AND 365",
    "ck_candidates_salary": "(current_salary IS NULL OR current_salary >= 0) AND (expected_salary IS NULL OR expected_salary >= 0)",
}


def _uuid(name: str, *args, nullable: bool = False, **kwargs) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, nullable=nullable, **kwargs)


def _text(name: str, length: int) -> sa.Column:
    return sa.Column(name, sa.String(length), nullable=True)


def upgrade() -> None:
    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQ}")
    if not op.get_context().as_sql and "candidates" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "candidates",
        _uuid("id", primary_key=True),
        sa.Column("candidate_code", sa.String(12), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        _text("mobile", 40),
        _text("mobile_normalized", 20),
        _text("email", 255),
        _text("location", 120),
        _text("qualification", 120),
        _text("college", 200),
        sa.Column("passing_year", sa.SmallInteger(), nullable=True),
        sa.Column("experience_months", sa.Integer(), nullable=True),
        _text("current_company", 200),
        sa.Column("current_salary", sa.Numeric(12, 2), nullable=True),
        sa.Column("expected_salary", sa.Numeric(12, 2), nullable=True),
        sa.Column("notice_days", sa.SmallInteger(), nullable=True),
        sa.Column("preferred_locations", sa.JSON(), nullable=False),
        _text("preferred_role", 120),
        _text("linkedin", 300),
        _uuid("source_id", sa.ForeignKey("rec_candidate_sources.id")),
        _text("source_detail", 200),
        sa.Column("status", sa.String(20), server_default=sa.text("'available'"), nullable=False),
        _uuid("user_id", sa.ForeignKey("users.id"), nullable=True, unique=True),
        sa.Column("opted_in", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _uuid("created_by_user_id", sa.ForeignKey("users.id")),
        _uuid("updated_by_user_id", sa.ForeignKey("users.id"), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        _uuid("archived_by_user_id", sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    op.create_index("uq_candidates_mobile", "candidates", ["mobile_normalized"], unique=True, postgresql_where=sa.text("mobile_normalized IS NOT NULL"))
    op.create_index("uq_candidates_email", "candidates", [sa.text("lower(email)")], unique=True, postgresql_where=sa.text("email IS NOT NULL"))
    op.create_index("ix_candidates_source_id", "candidates", ["source_id"])
    op.create_index("ix_candidates_status", "candidates", ["status"])
    op.create_index("ix_candidates_created_at", "candidates", ["created_at"])
    op.create_table(
        "candidate_resumes",
        _uuid("id", primary_key=True),
        _uuid("candidate_id", sa.ForeignKey("candidates.id")),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(300), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        _text("file_name", 255),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        _uuid("uploaded_by_user_id", sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("candidate_id", "version", name="uq_candidate_resumes_version"),
    )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM candidates LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0105_candidates: candidates exist. Remove them deliberately first.")
    op.drop_table("candidate_resumes")
    op.drop_table("candidates")
    op.execute(f"DROP SEQUENCE IF EXISTS {SEQ}")
