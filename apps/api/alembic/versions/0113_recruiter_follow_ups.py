"""rec-024 -- recruiter_follow_ups: follow-ups on a company (and optionally a contact, requirement or application).

Revision ID: 0113_recruiter_follow_ups
Revises: 0112_company_pipeline

docs/superpowers/specs/2026-10-08-rec-024-recruiter-follow-ups-design.md §2 (DEC-SCOPE-127). A new table only; no existing row changes.
0001 builds a fresh database from the current models, which already carry this table, so it is created only when missing (0110's idiom).
CHECKS repeats app.models.RECRUITER_FOLLOW_UP_CHECKS (test_rec_024_migration). downgrade() refuses while any follow-up exists: entered data
is never dropped silently.

Re-chained 2026-10-08 on merging `main` @ `8345c1fc`: drafted as `0112_recruiter_follow_ups` on `0111_university_pipeline`, but rec-005
(`0112_company_pipeline`, DEC-SCOPE-127) merged first, so this is `0113` (DEC-SCOPE-128, API §12AV, RBAC §2.54). A database stamped at the
draft is re-stamped with `alembic stamp --purge 0111_university_pipeline`, then `upgrade head` (the table step is guarded).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0113_recruiter_follow_ups"
down_revision = "0112_company_pipeline"
branch_labels = None
depends_on = None

TABLE = "recruiter_follow_ups"
UUID = postgresql.UUID(as_uuid=True)
REASONS = ("new_requirement", "jd", "profile_feedback", "interview_feedback", "offer_status", "joining_confirmation", "new_openings",
           "contract_mou", "payment_commercial")
CHECKS = {  # must equal app.models.RECRUITER_FOLLOW_UP_CHECKS (test_rec_024_migration)
    "ck_recruiter_follow_ups_reason": f"reason IN ({', '.join(repr(r) for r in REASONS)})",
    "ck_recruiter_follow_ups_status": "status IN ('open', 'done', 'cancelled')",
    "ck_recruiter_follow_ups_state": (
        "(status = 'done') = (completed_at IS NOT NULL) AND (completed_at IS NULL) = (completed_by_user_id IS NULL) "
        "AND (status = 'cancelled') = (cancelled_at IS NOT NULL) AND (cancelled_at IS NULL) = (cancel_reason IS NULL)"
    ),
}
INDEXES = {"ix_recruiter_follow_ups_company": ["company_id", "status", "due_at"], "ix_recruiter_follow_ups_contact": ["contact_id"]}
OPEN_DUE = "ix_recruiter_follow_ups_open_due"


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    when = sa.DateTime(timezone=True)

    def fk(target: str):
        return sa.ForeignKey(target, ondelete="RESTRICT")

    op.create_table(
        TABLE,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, fk("companies.id"), nullable=False),
        sa.Column("contact_id", UUID, fk("company_contacts.id"), nullable=True),
        sa.Column("job_id", UUID, fk("jobs.id"), nullable=True),
        sa.Column("application_id", UUID, fk("job_applications.id"), nullable=True),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("due_at", when, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'open'")),
        sa.Column("outcome", sa.String(500), nullable=True),
        sa.Column("completed_at", when, nullable=True),
        sa.Column("completed_by_user_id", UUID, fk("users.id"), nullable=True),
        sa.Column("cancelled_at", when, nullable=True),
        sa.Column("cancel_reason", sa.String(500), nullable=True),
        sa.Column("created_by_user_id", UUID, fk("users.id"), nullable=False),
        sa.Column("created_at", when, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", when, server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    for name, columns in INDEXES.items():
        op.create_index(name, TABLE, columns)
    op.create_index(OPEN_DUE, TABLE, ["due_at"], postgresql_where=sa.text("status = 'open'"))


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0113_recruiter_follow_ups: recruiter follow-ups exist. Clear them deliberately first.")
    op.drop_table(TABLE)
