"""pob-002 -- requirement revisions (job_revisions), the hiring-process and per-requirement commercial columns, and the backup owner.

Revision ID: 0281_job_revisions
Revises: 0278_commercial_grants

docs/superpowers/specs/2026-11-05-pob-002-requirement-revisions-design.md (DEC-SCOPE-405 R1/R6/R7/R9). Additive: nine nullable `jobs`
columns and one new table; no existing row changes. 0001 builds a fresh database from the current models, which already carry them, so
each is created only when missing (0258's idiom). CHECKS is a frozen copy of the model's JOB_TERMS_CHECKS and JOB_REVISION_CHECKS at this
revision. No backfill: a job's first save after this writes its baseline revision (R3).
"""

import sqlalchemy as sa

from alembic import op

revision = "0281_job_revisions"
down_revision = "0278_commercial_grants"
branch_labels = None
depends_on = None

JOB_CHECKS = {
    "ck_jobs_payment_trigger": "payment_trigger IS NULL OR payment_trigger IN ('on_joining', 'days_after_joining', 'on_invoice')",
    "ck_jobs_payment_days": "(payment_trigger IS NOT DISTINCT FROM 'days_after_joining') = (payment_days IS NOT NULL) AND (payment_days IS NULL OR payment_days BETWEEN 1 AND 365)",
    "ck_jobs_expected_tat_days": "expected_tat_days IS NULL OR expected_tat_days BETWEEN 1 AND 365",
}
REVISION_CHECKS = {"ck_job_revisions_revision": "revision >= 1"}
CHECKS = {**JOB_CHECKS, **REVISION_CHECKS}
FOREIGN_KEYS = {"fk_jobs_decision_maker_contact": ("decision_maker_contact_id", "company_contacts", "RESTRICT"),
                "fk_jobs_backup_owner": ("backup_owner_user_id", "users", None)}  # fmt: skip


def _columns() -> list[sa.Column]:
    return [
        sa.Column("interview_rounds", sa.JSON(), nullable=True),
        sa.Column("screening_steps", sa.JSON(), nullable=True),
        sa.Column("decision_maker_contact_id", sa.Uuid(), nullable=True),
        sa.Column("expected_tat_days", sa.Integer(), nullable=True),
        sa.Column("payment_trigger", sa.String(20), nullable=True),
        sa.Column("payment_days", sa.Integer(), nullable=True),
        sa.Column("payment_terms", sa.String(2000), nullable=True),
        sa.Column("replacement_terms", sa.String(2000), nullable=True),
        sa.Column("backup_owner_user_id", sa.Uuid(), nullable=True),
    ]


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if offline else {c["name"] for c in inspector.get_columns("jobs")}
    added = set()
    for column in _columns():
        if column.name not in existing:
            op.add_column("jobs", column)
            added.add(column.name)
    for name, (column, table, ondelete) in FOREIGN_KEYS.items():
        if offline or column in added:
            op.create_foreign_key(name, "jobs", table, [column], ["id"], ondelete=ondelete)
    checks = set() if offline else {c["name"] for c in inspector.get_check_constraints("jobs")}
    for name, sql in JOB_CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, "jobs", sql)
    if offline or "job_revisions" not in inspector.get_table_names():
        op.create_table(
            "job_revisions",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("snapshot", sa.JSON(), nullable=False),
            sa.Column("changed_fields", sa.JSON(), nullable=False),
            sa.Column("reason", sa.String(500), nullable=True),
            sa.Column("author_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("job_id", "revision", name="uq_job_revisions_revision"),
            *(sa.CheckConstraint(sql, name=name) for name, sql in REVISION_CHECKS.items()),
        )


def downgrade() -> None:
    """Revisions are history: the downgrade refuses while any exist rather than dropping them silently."""
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM job_revisions LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0281: requirement revisions exist (pob-002)")
    op.drop_table("job_revisions")
    for name in JOB_CHECKS:
        op.execute(f"ALTER TABLE jobs DROP CONSTRAINT IF EXISTS {name}")
    for column in reversed(_columns()):
        op.execute(f"ALTER TABLE jobs DROP COLUMN IF EXISTS {column.name}")  # drops its foreign key too
