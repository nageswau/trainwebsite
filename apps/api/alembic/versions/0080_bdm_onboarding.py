"""bdm-018 -- school onboarding handover: bdm_onboarding_requests and bdm_organizations.school_id.

Revision ID: 0080_bdm_onboarding
Revises: 0079_bdm_mous

docs/superpowers/specs/2026-10-06-bdm-018-school-onboarding-handover-design.md §3 (DEC-SCOPE-079). Additive: one new table and one
nullable column with a unique constraint; no existing row read or written. 0001 builds a fresh database from the current models, which
already carry both, so each is created only when missing. CHECKS must equal app.models.BDM_ONBOARDING_CHECKS
(test_bdm_018_migration). downgrade() refuses while any request or link exists: a handover is never dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0080_bdm_onboarding"
down_revision = "0079_bdm_mous"
branch_labels = None
depends_on = None

REQUESTS = "bdm_onboarding_requests"
ORGS = "bdm_organizations"
LINK_UNIQUE = "uq_bdm_organizations_school"
CHECKS = {
    "ck_bdm_onboarding_requests_kind": "kind IN ('school')",
    "ck_bdm_onboarding_requests_status": "status IN ('pending', 'completed', 'rejected')",
    "ck_bdm_onboarding_requests_resolution": "resolution IS NULL OR resolution IN ('created', 'linked')",
    "ck_bdm_onboarding_requests_resolved": "(status = 'pending') = (resolved_at IS NULL)",
    "ck_bdm_onboarding_requests_completed": "status <> 'completed' OR (school_id IS NOT NULL AND resolution IS NOT NULL)",
    "ck_bdm_onboarding_requests_rejected": "status <> 'rejected' OR reject_reason IS NOT NULL",
}


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def upgrade() -> None:
    inspector = _inspector()
    uuid = postgresql.UUID(as_uuid=True)
    if inspector is None or "school_id" not in {c["name"] for c in inspector.get_columns(ORGS)}:
        op.add_column(ORGS, sa.Column("school_id", uuid, sa.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=True))
        op.create_unique_constraint(LINK_UNIQUE, ORGS, ["school_id"])
    if inspector is None or REQUESTS not in inspector.get_table_names():
        op.create_table(
            REQUESTS,
            sa.Column("id", uuid, primary_key=True),
            sa.Column("organization_id", uuid, sa.ForeignKey("bdm_organizations.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("kind", sa.String(20), nullable=False, server_default="school"),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("note", sa.String(1000), nullable=True),
            sa.Column("requested_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("resolved_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolution", sa.String(20), nullable=True),
            sa.Column("school_id", uuid, sa.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("reject_reason", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
        )
        op.create_index("uq_bdm_onboarding_requests_pending", REQUESTS, ["organization_id"], unique=True, postgresql_where=sa.text("status = 'pending'"))
        op.create_index("ix_bdm_onboarding_requests_status", REQUESTS, ["status", "created_at"])


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        if bind.execute(sa.text(f"SELECT 1 FROM {REQUESTS} LIMIT 1")).first() or bind.execute(sa.text(f"SELECT 1 FROM {ORGS} WHERE school_id IS NOT NULL LIMIT 1")).first():
            raise RuntimeError("Cannot downgrade 0080_bdm_onboarding: onboarding data exists. Clear it deliberately first.")
    op.drop_table(REQUESTS)
    op.drop_constraint(LINK_UNIQUE, ORGS, type_="unique")
    op.drop_column(ORGS, "school_id")
