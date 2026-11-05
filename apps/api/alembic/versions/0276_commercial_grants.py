"""pob-001 -- the default `commercials.client.view` / `.edit` grants (Q-01): recruiters, placement managers and BDMs keep today's access.

Revision ID: 0276_commercial_grants
Revises: 0273_candidate_privacy

docs/superpowers/specs/2026-11-05-pob-001-commercial-permissions-design.md (DEC-SCOPE-401 C3). Seed only, no schema change: SEED is a
frozen copy of the new `rbac.DEFAULT_GRANTS` keys at this revision. A row that is already there is left alone; no existing row changes.
The vendor and candidate-contact keys have no default holder, so nothing is seeded for them. The downgrade removes the three new resources'
grants and overrides (the keys leave the catalogue with it); other resources are untouched.
"""

import sqlalchemy as sa

from alembic import op

revision = "0276_commercial_grants"
down_revision = "0273_candidate_privacy"
branch_labels = None
depends_on = None

SEED = (
    *((role, "commercials.client", action) for role in ("placement_team", "placement_manager") for action in ("view", "edit")),
    ("bdm", "commercials.client", "view"),  # the assigned BDM reads the contract (rec-030 R10), never writes it
)
RESOURCES = ("commercials.client", "commercials.vendor", "candidates.contact")


def upgrade() -> None:
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    for table in ("user_permission_overrides", "role_permissions"):
        op.execute(sa.text(f"DELETE FROM {table} WHERE resource IN :resources").bindparams(sa.bindparam("resources", RESOURCES, expanding=True)))
