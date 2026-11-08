"""pob-017 -- the per-requirement sourcing plan: `job_sourcing_plans`, `job_sourcing_channels`, `job_sourcing_searches` and
`job_applications.submitted_source_id`.

Revision ID: 0310_sourcing_plans
Revises: 0309_candidate_sourcing

docs/superpowers/specs/2026-11-08-pob-017-sourcing-plan-design.md (DEC-SCOPE-429). Additive. 0001 builds a fresh database from the current models,
which already carry all of this, so each step runs only when missing. PLAN_CHECKS is a frozen copy of `models.JOB_SOURCING_PLAN_CHECKS`. S6: an
application that already reached a submitted status gets its candidate's current source (the best evidence there is); no other row changes. The
downgrade drops what the upgrade added.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0310_sourcing_plans"
down_revision = "0309_candidate_sourcing"
branch_labels = None
depends_on = None

PLAN_CHECKS = {
    "ck_job_sourcing_plans_targets": (
        "(target_found IS NULL OR target_found BETWEEN 0 AND 10000) AND (target_screened IS NULL OR target_screened BETWEEN 0 AND 10000) AND "
        "(target_submitted IS NULL OR target_submitted BETWEEN 0 AND 10000)"
    ),
    "ck_job_sourcing_plans_profile": "target_profile IS NULL OR char_length(target_profile) <= 2000",
}
SUBMITTED = ("profile_shared", "interview", "selected", "joined")
UUID = postgresql.UUID(as_uuid=True)
BACKFILL = (
    "UPDATE job_applications a SET submitted_source_id = c.source_id FROM candidates c WHERE c.id = a.candidate_id AND a.submitted_source_id IS NULL AND "
    f"(a.status IN ({', '.join(repr(s) for s in SUBMITTED)}) OR EXISTS (SELECT 1 FROM job_application_status_history h WHERE h.application_id = a.id "
    f"AND h.to_status IN ({', '.join(repr(s) for s in SUBMITTED)})) OR EXISTS (SELECT 1 FROM profile_share_items i WHERE i.application_id = a.id))"
)


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    if offline or "submitted_source_id" not in {c["name"] for c in inspector.get_columns("job_applications")}:
        op.add_column("job_applications", sa.Column("submitted_source_id", UUID, sa.ForeignKey("rec_candidate_sources.id", ondelete="RESTRICT"), nullable=True))
    op.execute(BACKFILL)
    tables = set() if offline else set(inspector.get_table_names())
    if "job_sourcing_plans" not in tables:
        op.create_table(
            "job_sourcing_plans",
            sa.Column("job_id", UUID, sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("target_profile", sa.Text(), nullable=True),
            sa.Column("boolean_strings", sa.JSON(), nullable=False),
            sa.Column("target_found", sa.Integer(), nullable=True),
            sa.Column("target_screened", sa.Integer(), nullable=True),
            sa.Column("target_submitted", sa.Integer(), nullable=True),
            sa.Column("deadline", sa.Date(), nullable=True),
            sa.Column("source_owner_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in PLAN_CHECKS.items()),
        )
    if "job_sourcing_channels" not in tables:
        op.create_table(
            "job_sourcing_channels",
            sa.Column("job_id", UUID, sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("source_id", UUID, sa.ForeignKey("rec_candidate_sources.id", ondelete="RESTRICT"), primary_key=True),
        )
    if "job_sourcing_searches" not in tables:
        op.create_table(
            "job_sourcing_searches",
            sa.Column("job_id", UUID, sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("saved_search_id", UUID, sa.ForeignKey("saved_candidate_searches.id", ondelete="CASCADE"), primary_key=True),
        )
        op.create_index("ix_job_sourcing_searches_search", "job_sourcing_searches", ["saved_search_id"])


def downgrade() -> None:
    op.drop_table("job_sourcing_searches")
    op.drop_table("job_sourcing_channels")
    op.drop_table("job_sourcing_plans")
    op.drop_column("job_applications", "submitted_source_id")
