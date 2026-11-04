"""hrc-001 -- the default `candidates.compensation.view` grants (Q-03): recruiters and placement managers.

Revision ID: 0250_compensation_grant
Revises: 0249_it_training_progress

docs/superpowers/specs/2026-11-04-hrc-001-access-control-hardening-design.md (DEC-SCOPE-371 H2). Seed only, no schema change: SEED is a
frozen copy of the new `rbac.DEFAULT_GRANTS` key at this revision. A row that is already there is left alone; no existing row changes.
The downgrade removes the resource's grants and overrides (the key leaves the catalogue with it); other resources are untouched.
"""

import sqlalchemy as sa

from alembic import op

revision = "0250_compensation_grant"
down_revision = "0249_it_training_progress"
branch_labels = None
depends_on = None

SEED = (("placement_team", "candidates.compensation", "view"), ("placement_manager", "candidates.compensation", "view"))


def upgrade() -> None:
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    op.execute("DELETE FROM user_permission_overrides WHERE resource = 'candidates.compensation'")
    op.execute("DELETE FROM role_permissions WHERE resource = 'candidates.compensation'")
