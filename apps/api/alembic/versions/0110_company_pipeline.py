"""rec-005 -- the company B2B pipeline: `companies.stage` (+ when it changed, the Lost flag) and company_stage_history.

Revision ID: 0110_company_pipeline
Revises: 0109_university_duplicates

docs/superpowers/specs/2026-10-08-rec-005-company-pipeline-design.md §3 (DEC-SCOPE-125). Drafted as 0108 / DEC-SCOPE-123; upc-006 (0108) and upc-004 (0109) reached main first. Existing companies start at New Lead through the
column default, changed when they were created; every other insert path (EMP-001, /workflows/it/jobs) keeps working through the server
defaults. 0001 builds a fresh database from the current models, which already carry all of this, so every object is created only when
missing (0069's idiom). downgrade() refuses while pipeline data exists (a history row, a company past New Lead, or a Lost one).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0110_company_pipeline"
down_revision = "0109_university_duplicates"
branch_labels = None
depends_on = None

TABLE = "companies"
HISTORY = "company_stage_history"
UUID = postgresql.UUID(as_uuid=True)
# Frozen copy of app.recruiter_stages.ORDER (test_rec_005_migration checks parity).
STAGES = (
    "new_lead", "contacted", "interested", "meeting_scheduled", "requirement_discussion", "requirement_received", "jd_received",
    "candidates_sourcing", "profiles_shared", "interview", "selected", "joined", "requirement_closed",
)
CHECKS = {  # must equal app.models.COMPANY_PIPELINE_CHECKS
    "ck_companies_stage": "stage IN (" + ", ".join(f"'{s}'" for s in STAGES) + ")",
    "ck_companies_lost": "(lost_at IS NULL) = (lost_reason IS NULL)",
}
INDEX = "ix_companies_stage_recruiter"


def _inspect():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def upgrade() -> None:
    inspector = _inspect()
    columns = {c["name"] for c in inspector.get_columns(TABLE)} if inspector else set()
    checks = {c["name"] for c in inspector.get_check_constraints(TABLE)} if inspector else set()
    indexes = {i["name"] for i in inspector.get_indexes(TABLE)} if inspector else set()
    if "stage" not in columns:
        op.add_column(TABLE, sa.Column("stage", sa.String(30), nullable=False, server_default=STAGES[0]))
    if "stage_changed_at" not in columns:
        op.add_column(TABLE, sa.Column("stage_changed_at", sa.DateTime(timezone=True), nullable=True))
        op.execute(f"UPDATE {TABLE} SET stage_changed_at = created_at")
        op.alter_column(TABLE, "stage_changed_at", nullable=False, server_default=sa.func.now())
    if "lost_at" not in columns:
        op.add_column(TABLE, sa.Column("lost_at", sa.DateTime(timezone=True), nullable=True))
    if "lost_reason" not in columns:
        op.add_column(TABLE, sa.Column("lost_reason", sa.String(500), nullable=True))
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, TABLE, sql)
    if INDEX not in indexes:
        op.create_index(INDEX, TABLE, ["stage", "assigned_recruiter_user_id"])
    if inspector is None or HISTORY not in inspector.get_table_names():
        op.create_table(
            HISTORY,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("from_stage", sa.String(30), nullable=False),
            sa.Column("to_stage", sa.String(30), nullable=False),
            sa.Column("event", sa.String(30), nullable=False),
            sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("reason", sa.String(500), nullable=True),
            sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_company_stage_history_company", HISTORY, ["company_id", "position"])


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        used = f"SELECT 1 FROM {TABLE} WHERE stage <> '{STAGES[0]}' OR lost_at IS NOT NULL LIMIT 1"
        if bind.execute(sa.text(f"SELECT 1 FROM {HISTORY} LIMIT 1")).first() or bind.execute(sa.text(used)).first():
            raise RuntimeError("Cannot downgrade 0110_company_pipeline: company pipeline data exists. Clear it deliberately first.")
    op.drop_table(HISTORY)
    op.drop_index(INDEX, table_name=TABLE)
    for name in CHECKS:
        op.drop_constraint(name, TABLE, type_="check")
    for name in ("lost_reason", "lost_at", "stage_changed_at", "stage"):
        op.drop_column(TABLE, name)
