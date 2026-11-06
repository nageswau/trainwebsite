"""hrc-034 (DEC-SCOPE-416 I1/I3): the `portal_events` table (ids only) and the `reports.recruitment_insights.view` grant.

Revision ID: 0294_portal_events
Revises: 0292_screening_sessions

docs/superpowers/specs/2026-11-06-hrc-034-recruitment-insights-design.md. Existing data is untouched. Guarded: 0001 builds a fresh database from today's models, so
the table can already exist. ROLES is a frozen copy of the new `rbac.DEFAULT_GRANTS` holders at this revision.
"""

import sqlalchemy as sa

from alembic import op

revision = "0294_portal_events"
down_revision = "0292_screening_sessions"
branch_labels = None
depends_on = None

RESOURCE = "reports.recruitment_insights"
ROLES = ("hr_manager", "partner", "placement_manager")


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("portal_events"):
        op.create_table(
            "portal_events",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("kind", sa.String(12), nullable=False),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("day", sa.Date(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("kind IN ('job_view', 'apply_start', 'apply_submit')", name="ck_portal_events_kind"),
            sa.UniqueConstraint("user_id", "job_id", "kind", "day", name="uq_portal_events_once"),
        )
        op.create_index("ix_portal_events_day", "portal_events", ["day", "kind"])
    for role in ROLES:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, 'view') ON CONFLICT DO NOTHING").bindparams(role=role, resource=RESOURCE))


def downgrade() -> None:
    for table in ("user_permission_overrides", "role_permissions"):
        op.execute(sa.text(f"DELETE FROM {table} WHERE resource = :resource").bindparams(resource=RESOURCE))
    op.drop_table("portal_events")
