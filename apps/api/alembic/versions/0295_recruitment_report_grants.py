"""hrc-033 -- the default `reports.recruitment.view` / `.download` grants: the five operational recruitment dashboards.

Revision ID: 0295_recruitment_report_grants
Revises: 0294_portal_events

docs/superpowers/specs/2026-11-06-hrc-033-operational-recruitment-dashboards-design.md (DEC-SCOPE-415 D7). Seed only, no schema change: SEED is a
frozen copy of the new `rbac.DEFAULT_GRANTS` keys at this revision. A row that is already there is left alone; no existing row changes. The
downgrade removes the new resource's grants and overrides (its keys leave the catalogue with it); other resources are untouched.
"""

import sqlalchemy as sa

from alembic import op

revision = "0295_recruitment_report_grants"
down_revision = "0294_portal_events"
branch_labels = None
depends_on = None

RESOURCE = "reports.recruitment"
SEED = tuple(
    (role, RESOURCE, action)
    for role in ("placement_team", "placement_manager", "hr_manager", "placement_officer", "it_admin", "partner")
    for action in ("view", "download")
)


def upgrade() -> None:
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    for table in ("user_permission_overrides", "role_permissions"):
        op.execute(sa.text(f"DELETE FROM {table} WHERE resource = :resource").bindparams(resource=RESOURCE))
